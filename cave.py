"""
Entrar na cave sozinho, tentando de novo ate conseguir.

Como o jogo entra numa cave:
    O link verde "Enter <cave>" do NPC so chama, no Lua da interface do
    jogo, `uiPost("RequestIntoEctype:...?id=N")` -- N e o numero da cave.
    Quando ela esta lotada, o servidor responde "Scenario just reached
    maximum amount limit. Please try later again." e nada acontece. Por isso
    o jeito manual e ficar clicando no NPC e no link varias vezes.

O que o bot faz:
    Conecta no client (cliente_lua.py) e repete esse mesmo pedido em
    intervalos curtos, sem precisar do dialogo aberto, ate o mapa do
    personagem mudar (entrou). Para tambem se o personagem morrer, se passar
    do tempo limite, ou se voce mandar parar. O personagem precisa estar
    perto do NPC da cave -- o servidor confere a distancia, igual no clique.

Numero de cada cave:
    Ficam em CAVES. Se o jogo ganhar uma cave nova, o numero dela aparece no
    link "RequestIntoEctype:...?id=N" do dialogo do NPC (da pra ler da
    memoria do jogo depois de abrir o dialogo) -- e so acrescentar aqui.
"""

import json
import logging
import random
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

# Uma volta do loop, numa chamada so: confere o estado do personagem e, se
# ainda estiver no mesmo mapa, manda o pedido de entrar. Confere a camada do
# mundo ANTES de chamar as funcoes do jogo: fora dele (tela de login,
# loading) elas podem nao existir.
#   %(cena)d   = mapa onde o personagem estava ao comecar (-1 na 1a volta:
#                ai a propria volta descobre o mapa e ja manda o pedido)
#   %(id)d     = numero da cave
#   %(rajada)d = quantos pedidos mandar de uma vez nesta volta. Cada volta
#                espera a interface do jogo passar pelo gancho de novo
#                (~0,1s), entao mandar varios por volta e o que multiplica
#                os pedidos por segundo.
_LUA_TENTAR = """
local w = uiGetglobal("layWorld")
if not w or (w.getVisible and not w:getVisible()) then return "FORA" end
if uiUserIsDead() then return "MORTO" end
local c = uiUserGetSceneResID()
if %(cena)d ~= -1 and c ~= %(cena)d then return "ENTROU:" .. tostring(c) end
for i = 1, %(rajada)d do
  uiPost("RequestIntoEctype:cave?id=%(id)d")
end
return "ENVIADO:" .. tostring(c)
"""

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


# --------------------------------------------------------------- entrar --
def entrar(pid, numero, nome_cave, stop_event, intervalo=0.2, limite_minutos=10.0, prefixo="",
           rajada=1):
    """Repete o pedido de entrar na cave `numero` ate entrar, morrer, estourar
    o tempo ou `stop_event`. Manda `rajada` pedidos por volta, com
    `intervalo` segundos de pausa entre as voltas. Retorna True se entrou."""
    rajada = max(1, int(rajada))
    p = f"[{prefixo}] " if prefixo else ""
    try:
        c = cliente_lua.obter(pid)
    except cliente_lua.ErroCliente as exc:
        log.error("%sCave: nao consegui conectar no jogo: %s", p, exc)
        return False

    log.info("%sCave: tentando entrar em %s (n. %d)...", p, nome_cave, numero)
    inicio = time.time()
    tentativas = 0
    carregando_desde = None
    cena_inicial = None
    # A 1a volta ja manda o pedido e descobre o mapa atual ao mesmo tempo.
    codigo = _LUA_TENTAR % {"cena": -1, "id": numero, "rajada": rajada}
    proximo_log = 1

    while not stop_event.is_set():
        if limite_minutos and time.time() - inicio > limite_minutos * 60:
            log.warning("%sCave: desisti depois de %.0f min (%d tentativas).", p, limite_minutos, tentativas)
            return False
        try:
            r = c.executar(codigo, timeout=2.0)
            carregando_desde = None
        except cliente_lua.ErroCliente as exc:
            # Tela de loading para a interface do jogo por alguns segundos --
            # normalmente e justamente a entrada na cave acontecendo.
            if carregando_desde is None:
                carregando_desde = time.time()
                if cena_inicial is None:
                    log.warning("%sCave: o jogo nao responde -- ele nao pode estar minimizado.", p)
                else:
                    log.info("%sCave: o jogo parou de responder (carregando a cave?)...", p)
            elif time.time() - carregando_desde > 60:
                log.error("%sCave: o jogo nao responde ha 1 min, parando: %s", p, exc)
                return False
            stop_event.wait(0.5)
            continue

        if r.startswith("ENTROU"):
            log.info("%sCave: entrou em %s depois de %d tentativas (%.0fs).",
                     p, nome_cave, tentativas, time.time() - inicio)
            return True
        if r == "MORTO":
            log.warning("%sCave: o personagem esta morto, parando.", p)
            return False
        if r == "FORA" and cena_inicial is None:
            log.warning("%sCave: o personagem nao esta no mundo (tela de login/loading).", p)
            return False
        if r.startswith("ENVIADO"):
            tentativas += rajada
            if cena_inicial is None:
                cena_inicial = int(float(r.split(":", 1)[1]))
                codigo = _LUA_TENTAR % {"cena": cena_inicial, "id": numero, "rajada": rajada}
            if tentativas >= proximo_log:
                decorrido = max(0.001, time.time() - inicio)
                log.info("%sCave: %d pedidos em %.0fs (%.1f por segundo), ainda sem vaga...",
                         p, tentativas, decorrido, tentativas / decorrido)
                # 1o pedido, depois a cada ~10s de tentativas no ritmo atual
                proximo_log = tentativas + max(50, int(tentativas / decorrido * 10))
        # "FORA" depois de comecar: entre mapas -- so espera a proxima volta.
        if intervalo > 0:
            stop_event.wait(intervalo * random.uniform(0.85, 1.15))

    log.info("%sCave: parado (%d tentativas).", p, tentativas)
    return False
