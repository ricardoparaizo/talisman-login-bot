"""
Entrar na cave sozinho, tentando de novo ate conseguir.

Como o jogo entra numa cave:
    O link verde "Enter <cave>" do NPC so chama, no Lua da interface do
    jogo, `uiPost("RequestIntoEctype:...?id=N")` -- N e o numero da cave.
    Quando ela esta lotada, o servidor responde "Scenario just reached
    maximum amount limit. Please try later again." e nada acontece. Por isso
    o jeito manual e ficar clicando no NPC e no link varias vezes.

    O servidor so aceita esse pedido de quem CONVERSOU com o NPC da cave
    (abriu o dialogo dele). Sem isso, ignora em silencio -- nem a mensagem de
    "lotado" aparece. E o personagem precisa estar perto do NPC.

O que o bot faz:
    1. Conversa com o NPC da cave sozinho (a mesma funcao que o guia do
       proprio jogo usa pra interagir com um NPC). Se o NPC nao estiver perto,
       pede pro usuario clicar nele e espera o dialogo abrir.
    2. Liga o envio por quadro (cliente_lua._Repetidor): de dentro do laco
       principal do jogo, 1 pedido a cada 200 ms, com espacamento exato.
    3. Acompanha o mapa do personagem e desliga quando mudar (entrou), se o
       personagem morrer, se passar do tempo limite ou se mandar parar.

Numero de cada cave:
    Ficam em CAVES. Se o jogo ganhar uma cave nova, o numero dela aparece no
    link "RequestIntoEctype:...?id=N" do dialogo do NPC (da pra ler da
    memoria do jogo depois de abrir o dialogo) -- e so acrescentar aqui, com
    o id do NPC em NPC_DAS_CAVES.
"""

import json
import logging
import time

import cliente_lua
from paths import USER_DATA_DIR, ensure_user_data_dir

log = logging.getLogger("talisman-bot")

# (sigla, nome, numero da cave).
# Os numeros vieram dos dialogos de NPC carregados na memoria do jogo
# (link "RequestIntoEctype:...?id=N"), com o nome traduzido pelo proprio
# jogo (uiLanString) -- nao sao chute. SSC tambem foi testado ao vivo.
CAVES = [
    ("LC", "Lotus Cave", 6),
    ("BV", "Bamboo Valley", 19),
    ("SC", "Snake Cave", 2),
    ("RC", "Rattan Cave", 5),
    ("TC", "Tide Cave", 7),
    ("HH", "Happiness Hall", 3),
    ("ECC", "Ease Cloud Cave", 20),
    ("MW", "Murk Woods", 22),
    ("LW", "Laurel Wonderland", 10),
    ("DS", "Dark Stone Area", 23),
    ("FP", "Fantasy Palace", 4),
    ("BC", "Bewitcher Cave", 8),
    ("SSS", "Seven Stars Stage", 13),
    ("SSC", "Spider Catacomb", 15),
    ("SFC", "Silver Fox Cave", 16),
    ("CWC", "Chill Wind Cave", 18),
    # PRS: link do NPC "Lotus Treasure Light" (entrada da Peacock River,
    # confirmado pelo usuario); o jogo nao traduz o nome desse link.
    ("PRS", "Peacock River Sorrow Cave", 34),
    # PL: link do NPC "Silver Bearded Slaver" (entrada da Pirate Lair, aberto
    # pelo usuario); o jogo nao traduz o nome desse link.
    ("PL", "Pirate Lair", 30),
    ("WP", "West Palace", 44),
    ("MMC", "Meteorolite Mountain", 73),
    ("SP", "Saturn Palace", 74),
    ("PCP", "Purple Cloud Palace", 45),
    ("DR", "Devil Realm", 33),
]

# Numero da cave -> id (na tabela do jogo) do NPC que da entrada nela. E o
# numero da chave de texto do link do dialogo dele ("npctalk4848_02_19" ->
# 4848). Confirmado ao vivo com a Spider Catacomb (Spider Catacomb Child).
NPC_DAS_CAVES = {
    2: 165, 3: 278, 4: 4334, 5: 404, 6: 3129, 7: 3324, 8: 4484, 10: 4669,
    13: 4777, 15: 4848, 16: 4938, 18: 5146, 19: 41, 20: 5543, 22: 5677, 23: 5694,
    30: 6511, 33: 11096, 34: 8066, 44: 8848, 45: 1742, 73: 1927, 74: 1927,
}

INTERVALO_MS = 200  # 1 pedido a cada 200 ms (~4,5-5 por segundo)


def npc_da_cave(numero):
    return NPC_DAS_CAVES.get(numero)


_LUA_NOME = """
local l = uiGetglobal("layWorld.frmSelfEx.lbName")
if not l then return "" end
return l:getText()
"""


# --------------------------------------------------------------- tabela --
def lista_caves():
    """[(sigla, nome, numero)]."""
    return list(CAVES)


# ----------------------------------------------------- usadas por ultimo --
# Siglas das caves em que o usuario clicou "Entrar", da mais recente pra mais
# antiga -- a interface mostra essas primeiro. Fica na pasta do usuario
# (Documentos), junto das contas.
_RECENTES_PATH = USER_DATA_DIR / "caves_recentes.json"
_MAX_RECENTES = 5


def recentes():
    try:
        with open(_RECENTES_PATH, "r", encoding="utf-8") as f:
            dados = json.load(f)
        validas = {s for s, _, _ in CAVES}
        return [s for s in dados if s in validas][:_MAX_RECENTES]
    except (OSError, ValueError, TypeError):
        return []


def marcar_recente(sigla):
    if sigla not in {s for s, _, _ in CAVES}:
        return
    lista = [sigla] + [s for s in recentes() if s != sigla]
    try:
        ensure_user_data_dir()
        with open(_RECENTES_PATH, "w", encoding="utf-8") as f:
            json.dump(lista[:_MAX_RECENTES], f)
    except OSError as exc:  # nao salvar a ordem nunca pode impedir de entrar na cave
        log.debug("Nao consegui salvar as caves recentes: %s", exc)


def rotulo(sigla, nome, numero):
    return f"{sigla} - {nome}"


# ------------------------------------------------------------ clientes --
def nome_do_personagem(pid):
    """Nome do personagem logado nesse client. '' = no jogo mas fora do mundo
    (tela de login/personagem); None = o jogo nao respondeu (minimizado,
    carregando) ou nao deu pra conectar."""
    try:
        c = cliente_lua.obter(pid)
    except cliente_lua.ErroCliente as exc:
        log.debug("Nao consegui conectar no jogo (pid %s): %s", pid, exc)
        return None
    try:
        return c.executar(_LUA_NOME, timeout=1.0).strip()
    except cliente_lua.ErroCliente as exc:
        # NAO descarta a conexao: jogo minimizado so nao responde, e
        # reconectar a cada volta (varrer a memoria toda de novo) pesava o
        # bot inteiro. A conexao so e descartada quando o jogo fecha.
        log.debug("O jogo nao respondeu (pid %s): %s", pid, exc)
        return None


def detectar_online(conhecidos=None):
    """[(pid, nome)] de cada client.exe aberto -- nome como em
    nome_do_personagem ('' fora do mundo, None sem resposta). Tambem esquece
    as conexoes com jogos que fecharam.

    `conhecidos` ({pid: nome}) sao jogos que NAO devem ser consultados agora
    (ex: tentando entrar na cave) -- o nome deles e repetido como esta, pra a
    deteccao nao disputar a conexao com as tentativas."""
    import win_input

    conhecidos = conhecidos or {}
    pids = win_input.list_pids("client.exe") or []
    for pid in cliente_lua.pids_conectados():
        if pid not in pids:
            cliente_lua.descartar(pid)
    return [(pid, conhecidos[pid] if pid in conhecidos else nome_do_personagem(pid)) for pid in pids]


# ------------------------------------------------------- conversa c/ NPC --
_LUA_DIALOGO_ABERTO = """
local d = uiGetglobal("layWorld.frmDialogerEx")
if d and d:getVisible() then return "SIM" end
return "NAO"
"""

# Conversa com o NPC sem clique: e a funcao que o guia do proprio jogo usa
# (chamada com um numero so, o id do NPC). Ela procura entre os objetos
# carregados um NPC com esse id e manda ao servidor o mesmo evento
# "interagir" do clique.
#
# CUIDADO -- bug do proprio jogo (derrubou o client em 2026-11-14): a busca
# guarda em cache o ultimo id pesquisado e os objetos achados. Chamando de
# novo com o MESMO id depois que aquele NPC sumiu (o personagem mudou de
# mapa), o jogo usa o cache velho, acha "1 NPC" numa lista vazia e cai
# (0xC000000D, checagem de iterador). Por isso o cache e limpo antes e
# depois: uma busca com um id que nao pode existir (os ids dos NPCs cabem em
# 16 bits) forca uma busca nova e vazia. Com a busca nova, NPC que nao esta
# perto nao e achado e a funcao nao faz nada.
_ID_LIMPA_CACHE = 2147483647
_LUA_FALAR_NPC = (
    "uiUserHelpInteractiveByClassId(%(limpa)d)\n"
    "uiUserHelpInteractiveByClassId(%(npc)d)\n"
    "uiUserHelpInteractiveByClassId(%(limpa)d)\n"
    'return "ok"'
)


def _falar_com_npc(c, stop_event, p, numero):
    """Tenta abrir o dialogo do NPC da cave sozinho. True se abriu."""
    npc = npc_da_cave(numero)
    if not npc:
        return False
    try:
        c.executar(_LUA_FALAR_NPC % {"npc": npc, "limpa": _ID_LIMPA_CACHE}, timeout=3.0)
    except cliente_lua.ErroCliente as exc:
        log.debug("%sCave: nao consegui falar com o NPC %d: %s", p, npc, exc)
        return False
    fim = time.time() + 3.0
    while time.time() < fim and not stop_event.is_set():
        try:
            if c.executar(_LUA_DIALOGO_ABERTO, timeout=2.0) == "SIM":
                log.info("%sCave: conversei com o NPC da cave -- dialogo aberto.", p)
                return True
        except cliente_lua.ErroCliente:
            pass
        stop_event.wait(0.1)
    log.info("%sCave: o NPC da cave nao respondeu (longe demais?).", p)
    return False


def _esperar_conversa_npc(c, stop_event, p, numero, espera_max=120.0):
    """True quando o dialogo do NPC esta aberto (ja estava, o bot abriu, ou o
    usuario clicou). False se o usuario parou ou passou `espera_max` s."""
    try:
        if c.executar(_LUA_DIALOGO_ABERTO, timeout=3.0) == "SIM":
            return True
    except cliente_lua.ErroCliente:
        return True  # nao deu pra conferir: segue
    if _falar_com_npc(c, stop_event, p, numero):
        return True
    log.warning("%sCave: CLIQUE NO NPC DA CAVE uma vez (abra o dialogo dele) -- sem conversar com o "
                "NPC o servidor ignora os pedidos. Comeco assim que o dialogo abrir...", p)
    fim = time.time() + espera_max
    proximo_aviso = time.time() + 15
    while time.time() < fim:
        if stop_event.wait(0.4):
            return False
        try:
            if c.executar(_LUA_DIALOGO_ABERTO, timeout=2.0) == "SIM":
                log.info("%sCave: dialogo do NPC aberto -- comecando.", p)
                return True
        except cliente_lua.ErroCliente:
            continue
        if time.time() >= proximo_aviso:
            log.info("%sCave: ainda esperando voce clicar no NPC da cave...", p)
            proximo_aviso = time.time() + 15
    log.error("%sCave: o dialogo do NPC nao abriu em %.0f s; parando.", p, espera_max)
    return False


# --------------------------------------------------------------- entrar --
# Roda a cada INTERVALO_MS de dentro do laco do jogo (gancho por quadro); o
# proprio trecho confere se pode mandar o pedido.
_LUA_ENVIO = """
pcall(function()
  local w = uiGetglobal("layWorld")
  if not w or (w.getVisible and not w:getVisible()) then return end
  if uiUserIsDead() then return end
  if uiUserGetSceneResID() ~= %(cena)d then return end
  uiPost("RequestIntoEctype:cave?id=%(id)d")
  __bot_q_n = (__bot_q_n or 0) + 1
end)
"""

_LUA_ESTADO = """
local w = uiGetglobal("layWorld")
if not w or (w.getVisible and not w:getVisible()) then return "FORA" end
if uiUserIsDead() then return "MORTO" end
return "EST:" .. tostring(uiUserGetSceneResID()) .. ":" .. tostring(__bot_q_n or 0)
"""


def entrar(pid, numero, nome_cave, stop_event, limite_minutos=10.0, prefixo="", intervalo_ms=INTERVALO_MS):
    """Conversa com o NPC da cave e repete o pedido de entrar (1 a cada
    `intervalo_ms`) ate entrar, morrer, estourar o tempo ou `stop_event`.
    Retorna True se entrou."""
    p = f"[{prefixo}] " if prefixo else ""
    try:
        c = cliente_lua.obter(pid)
        r = c.executar(_LUA_ESTADO, timeout=3.0)
    except cliente_lua.ErroCliente as exc:
        log.error("%sCave: nao consegui falar com o jogo: %s", p, exc)
        return False
    if r == "MORTO":
        log.warning("%sCave: o personagem esta morto.", p)
        return False
    if not r.startswith("EST:"):
        log.warning("%sCave: o personagem nao esta no mundo (tela de login/loading).", p)
        return False
    cena_inicial = int(float(r.split(":")[1]))
    if not _esperar_conversa_npc(c, stop_event, p, numero):
        return False

    envio = _LUA_ENVIO % {"cena": cena_inicial, "id": numero}
    rep = c.repetidor()
    try:
        c.executar("__bot_q_n = 0", timeout=3.0)
        rep.iniciar(envio, intervalo_ms)
    except cliente_lua.ErroCliente as exc:
        log.error("%sCave: nao consegui ligar o envio: %s", p, exc)
        return False
    log.info("%sCave: tentando entrar em %s (n. %d), 1 pedido a cada %d ms...",
             p, nome_cave, numero, intervalo_ms)

    inicio = time.time()
    tentativas = 0
    proximo_log = inicio + 10
    carregando_desde = None
    try:
        while not stop_event.is_set():
            if limite_minutos and time.time() - inicio > limite_minutos * 60:
                log.warning("%sCave: desisti depois de %.0f min (%d pedidos).", p, limite_minutos, tentativas)
                return False
            try:
                rep.renovar()
                if not rep.ligado():
                    log.warning("%sCave: o envio desligou sozinho; religando.", p)
                    rep.iniciar(envio, intervalo_ms)
                if rep.status() != 0:
                    log.error("%sCave: erro no trecho de Lua do envio (status %d).", p, rep.status())
                    return False
                r = c.executar(_LUA_ESTADO, timeout=2.0)
                carregando_desde = None
            except cliente_lua.ErroCliente as exc:
                # Tela de loading para a interface do jogo por alguns segundos
                # -- normalmente e justamente a entrada na cave acontecendo.
                if carregando_desde is None:
                    carregando_desde = time.time()
                    log.info("%sCave: o jogo parou de responder (carregando a cave?)...", p)
                elif time.time() - carregando_desde > 60:
                    log.error("%sCave: o jogo nao responde ha 1 min, parando: %s", p, exc)
                    return False
                stop_event.wait(0.5)
                continue

            if r == "MORTO":
                log.warning("%sCave: o personagem esta morto, parando.", p)
                return False
            if r.startswith("EST:"):
                _, cena_txt, n_txt = r.split(":")
                tentativas = int(float(n_txt))
                if int(float(cena_txt)) != cena_inicial:
                    log.info("%sCave: entrou em %s depois de %d pedidos (%.0fs).",
                             p, nome_cave, tentativas, time.time() - inicio)
                    return True
            if time.time() >= proximo_log:
                decorrido = max(0.001, time.time() - inicio)
                log.info("%sCave: %d pedidos em %.0fs (%.1f por segundo), ainda sem vaga...",
                         p, tentativas, decorrido, tentativas / decorrido)
                proximo_log = time.time() + 10
            stop_event.wait(0.5)
        log.info("%sCave: parado (%d pedidos).", p, tentativas)
        return False
    finally:
        rep.parar()
