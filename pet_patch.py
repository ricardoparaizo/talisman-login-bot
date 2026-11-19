"""
Pet patch: evita o crash do client quando alguem spama pet perto de um
teleporte (mesma ideia do "Pet crash fix lite" do RaaskiBot).

O que acontece no jogo:
    Quando um jogador sai da visao (teleportou, mudou de mapa...), o client
    chama `CGSSceneMgrClt::Event_CreatureLeaveView(id, adiar)` pro pet dele
    (log do proprio client: "CGSSceneMgrClt::召唤兽 离开视野" = "o pet saiu da
    visao"). Com adiar=1 o pet nao some na hora: vai pra uma lista de remocao
    atrasada, com timer. Quem invoca/desinvoca pet sem parar na frente do
    teleporte enche essa lista, e a remocao atrasada acaba mexendo em objetos
    que ja foram destruidos -- o client cai.

O patch:
    Troca UM byte no codigo do jogo: o `push 1` (adiar) dessa chamada vira
    `push 0`, e o pet do jogador que saiu da visao e removido na hora, sem
    passar pela lista atrasada.

        0x9CFB0A  8b8f a8100000   mov ecx, [edi+0x10a8]   ; id do pet do jogador
        0x9CFB10  83c4 08         add esp, 8
        0x9CFB13  6a 01           push 1                  ; <- vira push 0
        0x9CFB15  51              push ecx
        0x9CFB16  8bcd            mov ecx, ebp            ; CGSSceneMgrClt
        0x9CFB18  e8 13050000     call 0x9D0030           ; Event_CreatureLeaveView

    Achado lendo o RaaskiBot.exe (so como mapa: padrao de bytes, o byte
    trocado e o valor 1 -> 0) e conferido direto no client.exe. Nao usa nada
    do codigo dele.

    O patch fica no jogo ate ele fechar (igual ao Raaski): nao e desfeito ao
    fechar o bot. Antes de escrever, os 19 bytes em volta sao conferidos --
    se o client for de outra versao, nada e alterado.
"""

import ctypes
import logging
import threading

import cliente_lua

log = logging.getLogger("talisman-bot")

ADDR_TRECHO = 0x009CFB0A
ADDR_BYTE = 0x009CFB14   # operando do push (1 = adiar, 0 = remover na hora)
ORIGINAL = bytes.fromhex("8b8fa810000083c4086a01518bcde813050000")
APLICADO = ORIGINAL[:10] + b"\x00" + ORIGINAL[11:]
assert ADDR_TRECHO + 10 == ADDR_BYTE

_k32 = cliente_lua._k32
_ACESSO = (cliente_lua.PROCESS_VM_OPERATION | cliente_lua.PROCESS_VM_READ
           | cliente_lua.PROCESS_VM_WRITE | cliente_lua.PROCESS_QUERY_INFORMATION)

# pids ja resolvidos (aplicado, ja estava aplicado ou versao diferente) --
# nao precisam ser conferidos de novo enquanto o jogo estiver aberto.
_resolvidos = {}
_lock = threading.Lock()


def _ler(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    lidos = ctypes.c_size_t()
    if not _k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(lidos)):
        return None
    return buf.raw[: lidos.value]


def aplicar(pid):
    """Aplica o patch no client de `pid`. Retorna:
    "aplicado" (acabou de aplicar), "ja" (ja estava aplicado, pelo bot ou por
    outro programa), "versao" (codigo diferente: nada foi alterado) ou
    "erro" (sem acesso / jogo ainda abrindo -- vale tentar de novo depois)."""
    h = _k32.OpenProcess(_ACESSO, False, pid)
    if not h:
        log.debug("Pet patch: sem acesso ao jogo (pid %d).", pid)
        return "erro"
    try:
        atual = _ler(h, ADDR_TRECHO, len(ORIGINAL))
        if atual is None or len(atual) != len(ORIGINAL):
            return "erro"
        if atual == APLICADO:
            return "ja"
        if atual != ORIGINAL:
            return "versao"
        try:
            cliente_lua._trocar_codigo(pid, h, ADDR_BYTE, b"\x00")
        except cliente_lua.ErroCliente as exc:
            log.debug("Pet patch: falhou no pid %d: %s", pid, exc)
            return "erro"
        return "aplicado" if _ler(h, ADDR_TRECHO, len(APLICADO)) == APLICADO else "erro"
    finally:
        _k32.CloseHandle(h)


def garantir(pids, abertos=None):
    """Aplica em cada pid de `pids` (jogos com personagem logado) ainda nao
    resolvido e esquece os jogos que fecharam (`abertos` = todos os
    client.exe abertos; padrao = `pids`). Barato (le 19 bytes por jogo
    novo) -- pode rodar a cada deteccao."""
    abertos = pids if abertos is None else abertos
    with _lock:
        for pid in list(_resolvidos):
            if pid not in abertos:
                del _resolvidos[pid]
        novos = [p for p in pids if p not in _resolvidos]
    for pid in novos:
        r = aplicar(pid)
        if r == "erro":
            continue  # tenta de novo na proxima volta
        with _lock:
            _resolvidos[pid] = r
        if r == "aplicado":
            log.info("Pet patch aplicado no jogo (pid %d): pet de quem teleporta some na hora.", pid)
        elif r == "ja":
            log.info("Pet patch: o jogo (pid %d) ja estava protegido.", pid)
        else:
            log.warning("Pet patch: versao diferente do client.exe (pid %d) -- nao alterei nada.", pid)
