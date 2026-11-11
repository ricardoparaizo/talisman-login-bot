"""
Roda trechos de Lua DENTRO do client.exe do Talisman Online.

Pra que serve:
    A interface do jogo e toda em Lua (5.0). Clicar no link verde "Enter
    <cave>" do NPC, por exemplo, so chama `uiPost("RequestIntoEctype:...?id=N")`
    no Lua do jogo. Rodando Lua la dentro, o bot consegue fazer o mesmo pedido
    quantas vezes quiser, sem clicar em nada -- e consultar o estado do jogo
    (mapa atual, janelas abertas...) sem depender de reconhecimento de tela.

Como funciona (resumo tecnico):
    1. Acha na memoria do jogo o objeto Lua da funcao global `uiGetglobal`
       (uma funcao C que a interface chama o tempo todo, varias vezes por
       frame). Esse objeto guarda o endereco da funcao C que o Lua chama.
    2. Copia pra dentro do jogo um trecho pequeno de codigo de maquina (o
       "gancho") e troca o endereco guardado no objeto pelo do gancho -- uma
       unica escrita de 4 bytes alinhada, que o processador faz de uma vez.
    3. Toda vez que a interface chama `uiGetglobal`, o gancho roda primeiro:
       se o bot deixou um pedido pendente, ele executa o trecho de Lua com
       `lua_dobuffer` (permitido dentro de uma funcao C), guarda o resultado
       em texto, e segue pra funcao original como se nada tivesse acontecido.
    4. Ao parar, o endereco original e devolvido. Se o bot fechar sem
       conseguir desfazer, o gancho continua la so repassando as chamadas --
       o jogo nao cai.

    Os enderecos abaixo valem pra versao do client.exe analisada (build
    "clt275 2.75", ver.6402). Antes de mexer em qualquer coisa, o modulo
    confere byte a byte que o codigo do jogo e o esperado -- se o jogo
    atualizar, ele se recusa a injetar em vez de arriscar derrubar o client.
"""

import ctypes
import ctypes.wintypes as wt
import logging
import struct
import threading
import time

log = logging.getLogger("talisman-bot")

# ----------------------------------------------------------- enderecos ---
# client.exe nao usa ASLR (DllCharacteristics = 0): carrega sempre em 0x400000.
ADDR_UIGETGLOBAL_CFN = 0x00BF8B10   # funcao C registrada como uiGetglobal
ADDR_LUA_GETTOP = 0x00BB9E50        # int lua_gettop(L)
ADDR_LUA_SETTOP = 0x00BB9E60        # void lua_settop(L, idx)
ADDR_LUA_TOSTRING = 0x00BBA380      # const char *lua_tostring(L, idx)
ADDR_LUA_DOBUFFER = 0x00BBBDA0      # int lua_dobuffer(L, buf, size, name)

# Bytes esperados no inicio de cada funcao -- conferidos antes de injetar.
ASSINATURAS = {
    ADDR_UIGETGLOBAL_CFN: bytes.fromhex("568b742408 68eed8ffff".replace(" ", "")),
    ADDR_LUA_GETTOP: bytes.fromhex("8b4c24048b41082b410cc1f804c3"),
    ADDR_LUA_SETTOP: bytes.fromhex("8b4c240885c98b442404"),
    ADDR_LUA_TOSTRING: bytes.fromhex("8b44240885c05657"),
    ADDR_LUA_DOBUFFER: bytes.fromhex("83ec088b4424108b"),
}

# Deslocamentos dentro de um closure C do Lua desse client:
#   +0x00 next | +0x04 tt(6) marked isC(1) nupvalues | +0x08 gclist | +0x0c f
CLOSURE_OFF_F = 0x0C

# ------------------------------------------------- memoria do gancho ----
TAM_BLOCO = 0x2000
OFF_MAGIC = 0x7F0
OFF_FLAG = 0x800      # 0 = livre, 1 = pedido pendente, 2 = executando
OFF_LEN = 0x804
OFF_STATUS = 0x808    # retorno do lua_dobuffer (0 = ok)
OFF_COUNT = 0x80C     # quantos pedidos ja rodaram
OFF_LAST_L = 0x810
OFF_ORIG = 0x814      # endereco original da funcao C (pra desfazer depois)
OFF_NAME = 0x820
OFF_RES = 0x900       # resultado (texto), ate 1023 bytes
TAM_RES = 1024
OFF_BUF = 0xD00       # codigo Lua a executar
TAM_BUF = TAM_BLOCO - OFF_BUF
MAGIC = b"BOTLUA01"

# ------------------------------------------------------------- win32 ----
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_EXECUTE_READWRITE = 0x40
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
        ("Protect", wt.DWORD), ("Type", wt.DWORD),
    ]


_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.VirtualAllocEx.restype = ctypes.c_void_p
_k32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
_k32.VirtualFreeEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]


class ErroCliente(Exception):
    """Algo impediu de falar com o client (versao diferente, sem permissao,
    client travado...). A mensagem ja vem pronta pra mostrar no log."""


# ------------------------------------------------------ montador x86 ----
class _Asm:
    """Montador minimo pras poucas instrucoes do gancho, com rotulos pra
    saltos curtos (rel8)."""

    def __init__(self, base):
        self.base = base
        self.code = bytearray()
        self.labels = {}
        self.fixups = []  # (posicao do byte rel8, rotulo)

    def emit(self, *parts):
        for p in parts:
            self.code += p if isinstance(p, (bytes, bytearray)) else bytes(p)

    def label(self, name):
        self.labels[name] = len(self.code)

    def jcc8(self, opcode, name):
        self.emit([opcode, 0])
        self.fixups.append((len(self.code) - 1, name, 1))

    def jcc32(self, opcode, name):
        """Salto condicional longo (0F 8x rel32) -- `opcode` e o da forma curta."""
        self.emit([0x0F, opcode + 0x10, 0, 0, 0, 0])
        self.fixups.append((len(self.code) - 4, name, 4))

    def call_abs(self, addr):
        self.emit(b"\xB8", struct.pack("<I", addr), b"\xFF\xD0")  # mov eax, addr; call eax

    def build(self):
        for pos, name, tam in self.fixups:
            rel = self.labels[name] - (pos + tam)
            if tam == 4:
                struct.pack_into("<i", self.code, pos, rel)
                continue
            if not -128 <= rel <= 127:
                raise ValueError(f"salto curto longe demais: {name}")
            self.code[pos] = rel & 0xFF
        return bytes(self.code)


def montar_gancho(base, orig_fn):
    """Codigo de maquina do gancho, pra ficar em `base` dentro do jogo.

    Equivale a:
        int gancho(lua_State *L) {
            if (FLAG == 1) {
                FLAG = 2;
                int top = lua_gettop(L);
                STATUS = lua_dobuffer(L, BUF, LEN, "=bot");
                RES[0] = 0;
                if (lua_gettop(L) > top) {
                    const char *s = lua_tostring(L, -1);
                    if (s) strncpy(RES, s, 1023);
                }
                lua_settop(L, top);
                COUNT++;
                FLAG = 0;
            }
            return orig_fn(L);   // na verdade um salto, com a pilha intacta
        }
    """
    d = lambda off: struct.pack("<I", base + off)  # noqa: E731
    a = _Asm(base)
    a.emit(b"\x83\x3D", d(OFF_FLAG), b"\x01")             # cmp dword [FLAG], 1
    a.jcc32(0x75, "repassa")                             # jne repassa (longo)
    a.emit(b"\x53\x56\x57")                              # push ebx; push esi; push edi
    a.emit(b"\x8B\x74\x24\x10")                          # mov esi, [esp+0x10]  (L)
    a.emit(b"\x89\x35", d(OFF_LAST_L))                   # mov [LAST_L], esi
    a.emit(b"\xC7\x05", d(OFF_FLAG), struct.pack("<I", 2))  # mov dword [FLAG], 2
    a.emit(b"\x56"); a.call_abs(ADDR_LUA_GETTOP); a.emit(b"\x83\xC4\x04")  # gettop(L)
    a.emit(b"\x89\xC7")                                  # mov edi, eax  (topo antigo)
    a.emit(b"\x68", d(OFF_NAME))                         # push NAME
    a.emit(b"\xFF\x35", d(OFF_LEN))                      # push dword [LEN]
    a.emit(b"\x68", d(OFF_BUF))                          # push BUF
    a.emit(b"\x56")                                      # push esi
    a.call_abs(ADDR_LUA_DOBUFFER); a.emit(b"\x83\xC4\x10")
    a.emit(b"\xA3", d(OFF_STATUS))                       # mov [STATUS], eax
    a.emit(b"\xC6\x05", d(OFF_RES), b"\x00")             # mov byte [RES], 0
    a.emit(b"\x56"); a.call_abs(ADDR_LUA_GETTOP); a.emit(b"\x83\xC4\x04")
    a.emit(b"\x39\xF8")                                  # cmp eax, edi
    a.jcc8(0x7E, "restaura")                             # jle restaura
    a.emit(b"\x6A\xFF\x56")                              # push -1; push esi
    a.call_abs(ADDR_LUA_TOSTRING); a.emit(b"\x83\xC4\x08")
    a.emit(b"\x85\xC0")                                  # test eax, eax
    a.jcc8(0x74, "restaura")                             # jz restaura
    a.emit(b"\xBB", d(OFF_RES))                          # mov ebx, RES
    a.emit(b"\xB9", struct.pack("<I", TAM_RES - 1))      # mov ecx, 1023
    a.label("copia")
    a.emit(b"\x8A\x10\x88\x13\x84\xD2")                  # mov dl,[eax]; mov [ebx],dl; test dl,dl
    a.jcc8(0x74, "restaura")                             # jz restaura
    a.emit(b"\x40\x43\x49")                              # inc eax; inc ebx; dec ecx
    a.jcc8(0x75, "copia")                                # jnz copia
    a.emit(b"\xC6\x03\x00")                              # mov byte [ebx], 0
    a.label("restaura")
    a.emit(b"\x57\x56"); a.call_abs(ADDR_LUA_SETTOP); a.emit(b"\x83\xC4\x08")  # settop(L, top)
    a.emit(b"\xFF\x05", d(OFF_COUNT))                    # inc dword [COUNT]
    a.emit(b"\xC7\x05", d(OFF_FLAG), struct.pack("<I", 0))  # mov dword [FLAG], 0
    a.emit(b"\x5F\x5E\x5B")                              # pop edi; pop esi; pop ebx
    a.label("repassa")
    a.emit(b"\x68", struct.pack("<I", orig_fn), b"\xC3")  # push orig; ret
    code = a.build()
    if len(code) >= OFF_MAGIC:
        raise ValueError("gancho grande demais")
    return code


# Todo trecho roda dentro de um pcall: erro de Lua nunca escapa pro jogo, e
# volta pro bot como texto ("ERR:..."). "OK:" + valor quando der certo.
_EMBRULHO = (
    "local __ok, __r = pcall(function()\n%s\nend)\n"
    "if not __ok then return 'ERR:' .. tostring(__r) end\n"
    "if __r == nil then return 'OK:' end\n"
    "return 'OK:' .. tostring(__r)\n"
)


class ClienteLua:
    """Conexao com UM client.exe (um pid). Use como:

        with ClienteLua(pid) as c:
            c.executar('uiPost("RequestIntoEctype:cave?id=15")')
    """

    def __init__(self, pid):
        self.pid = pid
        self.h = None
        self.bloco = None
        self.closure = None
        self.orig_fn = None
        # Um pedido por vez: o gancho la dentro tem um unico "balcao" (FLAG/
        # BUF/RES). Sem isso, duas threads do bot (a interface lendo o nome
        # do personagem e a cave mandando pedidos) pisariam uma na outra.
        self._lock = threading.Lock()
        # Trechos de Lua pra rodar antes de desconectar, desfazendo o que o
        # bot tiver mudado na interface do jogo (ex: o modo "Aprender").
        self.limpezas = {}

    # ---------------------------------------------------- memoria crua
    def _ler(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        if not _k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)):
            return None
        return buf.raw[: n.value]

    def _u32(self, addr):
        d = self._ler(addr, 4)
        if d is None or len(d) != 4:
            raise ErroCliente(f"nao consegui ler a memoria do jogo em {addr:#x}")
        return struct.unpack("<I", d)[0]

    def _escrever(self, addr, data):
        n = ctypes.c_size_t()
        ok = _k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n))
        if not ok or n.value != len(data):
            raise ErroCliente(f"nao consegui escrever na memoria do jogo em {addr:#x}")

    def _regioes(self):
        addr, mbi = 0x10000, _MBI()
        while addr < 0x7FFF0000 and _k32.VirtualQueryEx(
            self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
        ):
            base = mbi.BaseAddress or 0
            if (mbi.State == MEM_COMMIT and mbi.Protect
                    and not mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)):
                yield base, mbi.RegionSize
            addr = base + mbi.RegionSize

    def _buscar(self, padrao, limite=64):
        achados = []
        for base, size in self._regioes():
            off = 0
            while off < size:
                pedaco = min(size - off, 16 << 20)
                dados = self._ler(base + off, pedaco)
                if dados:
                    i = dados.find(padrao)
                    while i != -1:
                        achados.append(base + off + i)
                        if len(achados) >= limite:
                            return achados
                        i = dados.find(padrao, i + 1)
                off += pedaco
        return achados

    # ---------------------------------------------------- etapas
    def _conferir_versao(self):
        for addr, esperado in ASSINATURAS.items():
            real = self._ler(addr, len(esperado))
            if real != esperado:
                raise ErroCliente(
                    "a versao do client.exe e diferente da que o bot conhece "
                    f"(codigo diferente em {addr:#x}) -- nao vou injetar nada."
                )

    def _achar_closure(self, nome="uiGetglobal"):
        """Objeto closure C da funcao global `nome`: string Lua do nome ->
        entrada da tabela de globais -> valor (tipo funcao)."""
        nb = nome.encode()
        for a in self._buscar(nb + b"\x00", 64):
            hdr = self._ler(a - 16, 16)
            # TString: tt=4 no byte 4, tamanho em +12
            if not hdr or hdr[4] != 4 or struct.unpack_from("<I", hdr, 12)[0] != len(nb):
                continue
            ts = a - 16
            # O nome e citado por milhares de funcoes Lua (constantes); a
            # entrada da tabela de globais pode vir bem depois das primeiras.
            for ref in self._buscar(struct.pack("<I", ts), 50000):
                d = self._ler(ref - 8, 32)
                if not d or len(d) != 32:
                    continue
                ktt, _, kval, _, vtt, _, vval, _ = struct.unpack("<8I", d)
                if ktt == 4 and kval == ts and vtt == 6:
                    cab = self._ler(vval, 16)
                    # closure C: tt=6, isC=1
                    if cab and cab[4] == 6 and cab[6] == 1:
                        return vval
        return None

    def conectar(self):
        acesso = PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION
        self.h = _k32.OpenProcess(acesso, False, self.pid)
        if not self.h:
            raise ErroCliente(
                f"sem permissao pra acessar o jogo (pid {self.pid}). Se o jogo roda como "
                "administrador, o bot tambem precisa rodar como administrador."
            )
        self._conferir_versao()

        self.closure = self._achar_closure()
        if self.closure is None:
            raise ErroCliente("nao achei a interface Lua do jogo (ainda carregando?)")
        atual = self._u32(self.closure + CLOSURE_OFF_F)

        if atual == ADDR_UIGETGLOBAL_CFN:
            self._instalar()
        elif self._ler(atual + OFF_MAGIC, len(MAGIC)) == MAGIC:
            # Gancho de uma execucao anterior do bot (que fechou sem
            # desfazer) -- reaproveita em vez de empilhar outro.
            self.bloco = atual
            self.orig_fn = self._u32(self.bloco + OFF_ORIG)
            if self.orig_fn != ADDR_UIGETGLOBAL_CFN:
                raise ErroCliente("gancho antigo do bot com dados estranhos -- reinicie o jogo")
            self._escrever(self.bloco + OFF_FLAG, struct.pack("<I", 0))
            log.info("Reaproveitando a conexao deixada no jogo por uma execucao anterior.")
        else:
            raise ErroCliente(
                "outro programa ja mexeu nesse ponto do jogo (outro bot aberto?) -- "
                "nao vou mexer pra nao derrubar o client."
            )
        return self

    def _instalar(self):
        bloco = _k32.VirtualAllocEx(self.h, None, TAM_BLOCO, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
        if not bloco:
            raise ErroCliente("nao consegui reservar memoria dentro do jogo")
        if bloco > 0xFFFFF000:
            _k32.VirtualFreeEx(self.h, ctypes.c_void_p(bloco), 0, MEM_RELEASE)
            raise ErroCliente("memoria reservada fora do alcance do jogo (32 bits)")
        self.bloco = bloco
        self.orig_fn = ADDR_UIGETGLOBAL_CFN
        codigo = montar_gancho(bloco, self.orig_fn)
        dados = bytearray(OFF_BUF)
        dados[: len(codigo)] = codigo
        dados[OFF_MAGIC:OFF_MAGIC + len(MAGIC)] = MAGIC
        struct.pack_into("<I", dados, OFF_ORIG, self.orig_fn)
        dados[OFF_NAME:OFF_NAME + 5] = b"=bot\x00"
        self._escrever(bloco, bytes(dados))
        # So agora, com tudo pronto la dentro, desvia a funcao (4 bytes alinhados).
        self._escrever(self.closure + CLOSURE_OFF_F, struct.pack("<I", bloco))
        log.info("Conectado ao jogo (pid %d).", self.pid)

    def desconectar(self):
        """Devolve o endereco original. A memoria do gancho NAO e liberada de
        proposito: se o jogo estiver no meio de uma chamada passando por ela,
        liberar agora derrubaria o client. Sao 8 KB, somem quando o jogo fecha."""
        if self.h is None:
            return
        for nome, codigo in list(self.limpezas.items()):
            try:
                self.executar(codigo, timeout=1.0)
            except ErroCliente as exc:
                log.debug("Limpeza '%s' nao rodou: %s", nome, exc)
        self.limpezas.clear()
        try:
            if self.closure and self.bloco and self._u32(self.closure + CLOSURE_OFF_F) == self.bloco:
                self._escrever(self.closure + CLOSURE_OFF_F, struct.pack("<I", self.orig_fn))
                log.info("Desconectado do jogo (pid %d).", self.pid)
        except ErroCliente as exc:
            log.debug("Nao consegui desfazer a conexao (o jogo fechou?): %s", exc)
        finally:
            _k32.CloseHandle(self.h)
            self.h = None

    def __enter__(self):
        return self.conectar()

    def __exit__(self, *_):
        self.desconectar()

    # ---------------------------------------------------- uso
    def executar(self, codigo_lua, timeout=2.0):
        """Roda `codigo_lua` dentro do jogo (como corpo de uma funcao: use
        `return` pra devolver algo). Retorna o valor devolvido, como texto.
        Levanta ErroCliente se der erro de Lua ou se o jogo nao rodar a tempo
        (tela de loading, por exemplo, para a interface por alguns segundos)."""
        if self.bloco is None or self.h is None:
            raise ErroCliente("nao conectado ao jogo")
        fonte = (_EMBRULHO % codigo_lua).encode("latin1")
        if len(fonte) >= TAM_BUF:
            raise ErroCliente("trecho de Lua grande demais")
        with self._lock:
            return self._executar_travado(fonte, timeout)

    def _executar_travado(self, fonte, timeout):
        # Espera um pedido anterior (que tenha estourado o tempo) terminar.
        fim = time.time() + timeout
        while self._u32(self.bloco + OFF_FLAG) != 0:
            if time.time() > fim:
                raise ErroCliente("o jogo ainda esta rodando o pedido anterior")
            time.sleep(0.01)

        self._escrever(self.bloco + OFF_BUF, fonte + b"\x00")
        self._escrever(self.bloco + OFF_LEN, struct.pack("<I", len(fonte)))
        self._escrever(self.bloco + OFF_FLAG, struct.pack("<I", 1))  # por ultimo

        fim = time.time() + timeout
        while True:
            flag = self._u32(self.bloco + OFF_FLAG)
            if flag == 0:
                break
            if time.time() > fim:
                if flag == 1:
                    # Nem comecou: cancela pra nao rodar atrasado depois.
                    self._escrever(self.bloco + OFF_FLAG, struct.pack("<I", 0))
                    raise ErroCliente(
                        f"o jogo nao rodou o pedido em {timeout:.0f}s (carregando, minimizado ou travado?)"
                    )
                raise ErroCliente("o jogo comecou o pedido mas nao terminou a tempo")
            time.sleep(0.005)

        status = self._u32(self.bloco + OFF_STATUS)
        res = (self._ler(self.bloco + OFF_RES, TAM_RES) or b"").split(b"\x00", 1)[0].decode("latin1")
        if status != 0:
            raise ErroCliente(f"erro de sintaxe no Lua enviado (status {status})")
        if res.startswith("ERR:"):
            raise ErroCliente(f"erro de Lua: {res[4:]}")
        return res[3:] if res.startswith("OK:") else res


# ------------------------------------------- conexoes compartilhadas ----
# Uma conexao por client.exe, reaproveitada por quem precisar (interface e
# cave). Quem fecha tudo e a interface, ao sair (desconectar_todos).
_conexoes = {}
_conexoes_lock = threading.Lock()


def obter(pid):
    """Conexao (ja conectada) com o client de `pid`, criando se preciso."""
    with _conexoes_lock:
        c = _conexoes.get(pid)
        if c is not None and c.h is not None:
            return c
        c = ClienteLua(pid)
        c.conectar()
        _conexoes[pid] = c
        return c


def pids_conectados():
    with _conexoes_lock:
        return list(_conexoes)


def descartar(pid):
    """Esquece (e desfaz, se der) a conexao com `pid` -- usar quando ela
    falhar, pra proxima tentativa conectar do zero."""
    with _conexoes_lock:
        c = _conexoes.pop(pid, None)
    if c is not None:
        c.desconectar()


def desconectar_todos():
    with _conexoes_lock:
        conexoes = list(_conexoes.values())
        _conexoes.clear()
    for c in conexoes:
        c.desconectar()
