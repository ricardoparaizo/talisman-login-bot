"""
Talisman Online - Bot de auto-retry de login
=============================================

O que este script faz:
    Fica observando a janela do jogo (processo client.exe), reconhece em qual
    etapa do login voce esta (conta/senha, escolha de servidor, fila, escolha
    de personagem) e avanca sozinho: digita conta/senha (se voce configurou
    um perfil com `setup_perfil.py`), clica em "Ok"/"Enter Game" nas telas
    certas, e refaz tudo automaticamente sempre que o cliente cair de volta
    pra tela inicial (por exemplo depois do popup "Connection interrupted.")
    -- que era o trabalho manual repetitivo que motivou esse bot.

    Na tela de fila ("Queue to Login") o bot NUNCA clica em nada (nem no
    "Cancel" dela) -- ele so espera e registra no log. Clicar em Cancel ali
    te tiraria da fila, o que seria o oposto do que voce quer.

Modo de entrada (input_mode no config.json):
    - "background" (padrao): manda clique/digitacao DIRETO pra janela do
      jogo via mensagens do Windows, sem mover o cursor real e sem exigir
      foco na janela. Voce pode continuar usando o mouse/teclado
      normalmente em outros programas enquanto o bot roda. A janela do jogo
      só não pode estar minimizada. Veja win_input.py para detalhes e
      limitacoes dessa tecnica.
    - "foreground": modo antigo, baseado em pyautogui -- move o cursor real
      e exige que a janela do jogo esteja em primeiro plano (voce nao pode
      usar o PC pra outra coisa nesse meio tempo). Use isso so se algum
      elemento especifico nao reagir no modo "background".

Sobre resolucao de tela:
    O jogo permite escolher a resolucao nas opcoes de video (800x600 até
    1920x1080). Os templates em templates/ foram capturados numa janela de
    ~1024x768 (a mais usada). O bot calcula o tamanho real da janela/area do
    jogo e ajusta a escala dos templates automaticamente pra bater com a
    resolucao atual.

O que este script NAO faz:
    Nao joga por voce, nao automatiza nada dentro do jogo (movimento, combate,
    farm, etc). E so um "auto-clicker" de tela de login/fila/personagem.

Sobre ser "leve" e nao levantar suspeita de antivirus:
    Este script usa so bibliotecas Python comuns e amplamente conhecidas
    (pyautogui, opencv, numpy, keyring, pywin32, psutil) -- a mesma tecnica
    usada por ferramentas de RPA/acessibilidade (ex: Sikuli, AutoHotkey).
    Ele NAO instala hooks de teclado globais, NAO injeta codigo no processo
    do jogo (so manda mensagens de janela padrao do Windows, a mesma API que
    qualquer programa usa pra desenhar botoes/dialogos), e NAO le memoria de
    outro processo. Se quiser um .exe (pra nao precisar de Python instalado
    pra RODAR o bot), veja `build_exe.bat` -- ele gera o .exe DE FORMA LOCAL
    na sua propria maquina, a partir deste codigo fonte, o que evita o
    principal motivo de falso-positivo (baixar um .exe pronto de alguem, sem
    saber a procedencia). Se o Windows Defender ou outro antivirus ainda
    assim reclamar, e um falso positivo comum em qualquer automacao de UI --
    o codigo e python puro e legivel, pode ser inspecionado linha a linha
    antes de liberar/whitelistar a pasta.

IMPORTANTE (leia antes de usar):
    1. Isso roda no SEU computador Windows, controlando o jogo de verdade.
    2. A janela do jogo NAO pode estar minimizada (pode estar atras de
       outras janelas). No modo "background" voce pode usar o resto do PC
       normalmente; no modo "foreground" nao.
    3. Automatizar login pode nao ser oficialmente suportado pela publisher
       do jogo. O risco (ban, etc.) e seu; use com bom senso (os atrasos
       aleatorios entre acoes ja ajudam a nao "martelar" o servidor).
    4. Para PARAR: crie um arquivo "PARAR.txt" nesta pasta, ou aperte Ctrl+C
       no terminal.

Interface grafica (recomendado):
    Rodar "python bot.py" (ou dar duplo clique no .exe) sem nenhum argumento
    abre uma interface grafica simples (gui.py) onde voce cadastra contas
    (cada uma com seu servidor/personagem) e clica Iniciar/Parar. E la que
    voce escolhe qual conta usar.

Como usar via linha de comando / sem interface (avancado):
    1. pip install -r requirements.txt
    2. python bot.py --setup       (cadastra/edita um perfil, por texto)
    3. python bot.py --nogui       (roda o loop direto, sem abrir janela)

Como usar via .exe (sem precisar de Python instalado pra RODAR -- so pra
gerar o .exe na primeira vez):
    1. build_exe.bat  (gera dist\\TalismanLoginBot\\TalismanLoginBot.exe)
    2. TalismanLoginBot.exe   (abre a interface grafica)
"""

import json
import logging
import random
import sys
import threading
import time
from pathlib import Path

from paths import BASE_DIR, RESOURCE_DIR, USER_DATA_DIR, ensure_user_data_dir
import profiles

CONFIG_PATH = RESOURCE_DIR / "config.json"
STOP_FILE = BASE_DIR / "PARAR.txt"

# O log fica junto das contas, na pasta do usuario (Documentos), e nao na
# pasta do bot: ele cita nomes de conta, entao nao deve viajar junto quando
# alguem compartilha o bot.
ensure_user_data_dir()
LOG_PATH = USER_DATA_DIR / "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger("talisman-bot")

# PIDs de client.exe ja "adotados" por algum Bot desta sessao -- usado
# quando varias contas rodam ao mesmo tempo, pra garantir que cada uma so
# olha/clica na SUA propria janela do jogo, mesmo que existam varias copias
# do client.exe abertas simultaneamente (uma por conta). Protegido por um
# lock porque cada conta roda numa thread separada.
_claimed_client_pids = set()
_claimed_pids_lock = threading.Lock()

# O LAUNCHER (diferente do client.exe do jogo em si) so aceita UMA instancia
# aberta por vez -- abrir um segundo enquanto o primeiro ainda esta de pe da
# erro. Esse lock garante que, ao logar varias contas ao mesmo tempo, cada
# uma espera a VEZ dela pra abrir o launcher: so abre o proprio launcher
# depois que o launcher da conta anterior ja tiver fechado (o que acontece
# logo depois de clicar em "Enter Game", quando ele entrega a vez pro
# client.exe). Da pra abrir varios client.exe (jogo) ao mesmo tempo sem
# problema -- a restricao e so no launcher.
_launcher_open_lock = threading.Lock()

def _release_claimed_pid(pid):
    if pid is None:
        return
    with _claimed_pids_lock:
        _claimed_client_pids.discard(pid)


class _AccountLoggerAdapter(logging.LoggerAdapter):
    """Prefixa cada linha de log com o nome da conta. Importante quando
    varias contas estao rodando (e logando) ao mesmo tempo -- sem isso, no
    log ficaria impossivel saber qual bot disse o que."""

    def process(self, msg, kwargs):
        account = self.extra.get("account")
        if account:
            return f"[{account}] {msg}", kwargs
        return msg, kwargs


def load_json(path):
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    """Le o config.json que veio junto com o programa e, por cima dele,
    aplica um config.json que esteja NA MESMA PASTA do .exe (se existir).

    Isso existe porque, no .exe empacotado, o config.json original viaja
    dentro do proprio executavel -- mudar qualquer ajuste exigiria gerar o
    .exe de novo. Com essa sobreposicao, da pra colocar um config.json ao
    lado do TalismanLoginBot.exe contendo SO as chaves que voce quer mudar
    (ex: {"clear_field_presses": 0}) e testar na hora, sem recompilar."""
    cfg = load_json(CONFIG_PATH)
    override_path = BASE_DIR / "config.json"
    try:
        mesmo_arquivo = override_path.resolve() == CONFIG_PATH.resolve()
    except OSError:
        mesmo_arquivo = False
    if not mesmo_arquivo and override_path.exists():
        try:
            override = load_json(override_path)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Ignorei o config.json ao lado do .exe (nao consegui ler): %s", exc)
            return cfg
        if isinstance(override, dict) and override:
            cfg.update(override)
            log.info(
                "Ajustes do config.json ao lado do .exe aplicados: %s",
                ", ".join(sorted(k for k in override if not k.startswith("_"))),
            )
    return cfg


def random_delay(cfg):
    if cfg.get("randomize_delay", True):
        low, high = cfg.get("random_delay_range", [1.5, 4.0])
        time.sleep(random.uniform(low, high))
    else:
        time.sleep(cfg.get("check_interval_seconds", 2.0))


def _resolve_game_exe(raw):
    """Aceita tanto a PASTA onde o jogo esta instalado quanto o caminho
    completo do game.exe, e devolve o caminho do executavel (ou None se
    nao achar). Deixar o usuario apontar a pasta e mais simples do que
    fazer ele cacar o .exe certo no meio dos arquivos do jogo."""
    raw = (raw or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    if p.is_dir():
        for nome in ("game.exe", "Game.exe", "launcher.exe"):
            candidato = p / nome
            if candidato.is_file():
                return candidato
        # ultimo recurso: algum .exe com "game" no nome dentro da pasta
        for candidato in sorted(p.glob("*.exe")):
            if "game" in candidato.name.lower():
                return candidato
    return None


class Bot:
    def __init__(self, cfg, raw_templates, perfil):
        self.cfg = cfg
        self.raw_templates = raw_templates
        self.perfil = perfil

        self.account = perfil.get("account", "")
        self.log = _AccountLoggerAdapter(log, {"account": self.account or None})

        self.confidence = cfg.get("confidence", 0.85)
        self.jitter = cfg.get("click_offset_jitter_px", 3)
        self.base_w = cfg.get("base_resolution_width", 1024)
        self.base_h = cfg.get("base_resolution_height", 768)
        self.window_title_keyword = cfg.get("window_title_keyword", "Talisman")
        self.process_name = cfg.get("process_name", "client.exe")
        self.max_unknown = cfg.get("max_consecutive_unknown", 40)
        self.mode = cfg.get("input_mode", "background")
        # Se a tela "Connecting to the server, please wait a moment." travar
        # (nao sumir sozinha) por mais que esse tanto de segundos, o bot
        # cancela e deixa o loop normal tentar logar de novo. Veja step().
        self.connecting_timeout_seconds = cfg.get("connecting_timeout_seconds", 20)
        # Se o servidor configurado nao aparecer na lista (ex: esta offline
        # -- ele simplesmente some da lista nesse caso) por mais que esse
        # tanto de segundos, o bot cancela e volta pro login, tentando de
        # novo ate o servidor reaparecer. Sem isso, ele acabaria clicando Ok
        # com QUALQUER servidor que estiver selecionado por padrao na lista.
        self.server_missing_timeout_seconds = cfg.get("server_missing_timeout_seconds", 8)
        # Quantas vezes o bot aperta Backspace/Delete pra limpar um campo
        # antes de digitar. 0 = nao limpa (nenhuma tecla enviada). Isso e
        # ajustavel porque as TECLAS sinteticas sao o que faz o jogo (ou o
        # anti-cheat dele) re-injetar teclado de verdade no Windows, o que
        # aparece como texto aleatorio na janela que voce estiver usando.
        self.clear_field_presses = int(cfg.get("clear_field_presses", 0))
        # Rede de seguranca pro clear_field_presses=0: se o login parar de
        # progredir (fica voltando pra tela de conta/senha sem nunca chegar
        # no servidor), e sinal de que o campo NAO estava vindo vazio e o
        # texto foi grudando. Nesse caso o bot religa a limpeza sozinho.
        self._logins_sem_progresso = 0
        self._limpeza_reativada = False
        # Se True, o bot tenta preencher conta/senha com WM_SETTEXT (uma
        # mensagem so, ZERO teclas). So funciona se os campos forem
        # controles de texto de verdade do Windows; senao ele volta sozinho
        # pro modo de digitar tecla a tecla.
        self.direct_field_fill = bool(cfg.get("direct_field_fill", True))
        # Loga uma unica vez qual dos dois caminhos acabou sendo usado.
        self._fill_method_logged = None
        # A pasta do jogo mora no perfis.json (arquivo do usuario). O
        # config.json so entra como plano B, pra quem esta vindo de uma
        # versao antiga onde o caminho ficava la.
        self.launcher_exe_path = profiles.get_game_path() or (cfg.get("launcher_exe_path") or "").strip()

        # Suporte a varias contas rodando ao mesmo tempo: cada Bot se
        # "trava" num pid especifico de client.exe (target_pid) assim que
        # acha um, e so olha/clica na janela DESSE pid -- nunca em janelas
        # de outras contas. Veja handle_launcher_phase().
        self.target_pid = None
        self._launcher_pid = None
        self._client_pids_before_launch = set()
        self._launcher_path_invalid_logged = False
        self._server_row_selected = False
        self._character_row_selected = False
        # Marca desde quando a tela "Connecting to the server..." apareceu
        # sem interrupcao (None = nao esta nela agora). Veja step().
        self._connecting_since = None
        # Marca desde quando a lista de servidores apareceu SEM o servidor
        # configurado nela (None = ele apareceu, ou ainda nao estamos nessa
        # tela). Veja step().
        self._server_missing_since = None
        # True enquanto esta conta e a "dona" do _launcher_open_lock (ou
        # seja, o launcher.exe dela e o unico que pode estar aberto agora).
        self._holds_launcher_lock = False

        self.attempts = 0
        self.consecutive_unknown = 0
        self.last_state_logged = None
        self.last_scale = None
        self.scaled_templates = {}

        # contexto do ciclo atual (preenchido em refresh_frame)
        self.region = None       # so usado no modo "foreground"
        self.hwnd = None         # so usado no modo "background"
        self.screen_bgr = None

        if self.mode == "background":
            import win_input  # noqa: F401 - so pra falhar rapido se pywin32 nao estiver instalado

            self._win_input = win_input
        else:
            import pyautogui
            from screen_match import get_capture_context, screenshot_region_bgr

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.1
            self._pyautogui = pyautogui
            self._get_capture_context = get_capture_context
            self._screenshot_region_bgr = screenshot_region_bgr

        self.password = profiles.get_password(self.account) if self.account else None
        if self.account and not self.password:
            self.log.warning(
                "A conta '%s' esta sem senha salva -- vou so clicar em Ok, sem digitar nada.",
                self.account,
            )

    # ---------------------------------------------------------------- util

    def has(self, name):
        return name in self.raw_templates

    def release(self):
        """Libera o pid de client.exe que esta conta tinha travado (chamar
        ao parar o bot), pra outra conta poder usa-lo se precisar. Tambem
        libera o _launcher_open_lock se essa conta estiver parando bem no
        meio de abrir o launcher -- senao as outras contas ficariam
        esperando pra sempre a vez de um launcher que nunca vai terminar."""
        _release_claimed_pid(self.target_pid)
        self.target_pid = None
        self._release_launcher_lock()

    def _release_launcher_lock(self):
        if self._holds_launcher_lock:
            self._holds_launcher_lock = False
            try:
                _launcher_open_lock.release()
            except RuntimeError:
                pass

    def ensure_scaled(self, scale):
        from screen_match import scale_template

        if self.last_scale is not None and abs(scale - self.last_scale) < 0.02:
            return
        self.log.debug("Escala dos templates ajustada para %.3f.", scale)
        self.scaled_templates = {
            name: scale_template(img, scale) for name, img in self.raw_templates.items()
        }
        self.last_scale = scale

    def refresh_frame(self):
        from screen_match import compute_scale

        if self.mode == "background":
            wi = self._win_input
            if self.target_pid is None:
                self.screen_bgr = None
                return
            if self.hwnd is None or not wi.win32gui.IsWindow(self.hwnd):
                self.hwnd = wi.find_game_hwnd(pid=self.target_pid)
                if self.hwnd is not None:
                    # Log bem visivel (INFO, nao debug) de EXATAMENTE qual
                    # janela o bot vai clicar/digitar a partir de agora.
                    # Se um dia o bot digitar em outro lugar por engano,
                    # essa linha no bot.log mostra na hora qual janela ele
                    # ACHAVA que era o jogo, o que ajuda a achar a causa.
                    try:
                        titulo = wi.win32gui.GetWindowText(self.hwnd)
                    except Exception:  # noqa: BLE001
                        titulo = "?"
                    exe_path = wi.pid_exe_path(self.target_pid)
                    self.log.info(
                        "Conectado a janela do jogo: titulo='%s' pid=%s processo='%s'.",
                        titulo, self.target_pid, exe_path or "?",
                    )
            if self.hwnd is None:
                self.screen_bgr = None
                return
            width, height = wi.get_client_size(self.hwnd)
            scale = compute_scale(width, height, self.base_w, self.base_h)
            self.ensure_scaled(scale)
            self.screen_bgr = wi.capture_window_bgr(self.hwnd)
        else:
            ctx = self._get_capture_context(self.base_w, self.base_h, self.window_title_keyword)
            self.region = ctx["region"]
            self.ensure_scaled(ctx["scale"])
            self.screen_bgr = self._screenshot_region_bgr(self.region)

    def find(self, name):
        from screen_match import match_template

        if name not in self.scaled_templates or self.screen_bgr is None:
            return None
        return match_template(self.screen_bgr, self.scaled_templates[name], self.confidence)

    def click(self, name, label=None):
        box = self.find(name)
        if not box:
            return False
        x, y, w, h = box
        cx, cy = x + w // 2, y + h // 2
        self.attempts += 1
        self.log.info("Clicando em %s.", label or name)

        if self.mode == "background":
            dx = random.randint(-self.jitter, self.jitter)
            dy = random.randint(-self.jitter, self.jitter)
            self._win_input.click_in_window(self.hwnd, cx + dx, cy + dy)
        else:
            left = self.region[0] if self.region else 0
            top = self.region[1] if self.region else 0
            dx = random.randint(-self.jitter, self.jitter)
            dy = random.randint(-self.jitter, self.jitter)
            self._pyautogui.moveTo(left + cx + dx, top + cy + dy, duration=random.uniform(0.15, 0.35))
            self._pyautogui.click()

        self.consecutive_unknown = 0
        self.last_state_logged = None
        return True

    def _presses_de_limpeza(self):
        """Quantas teclas de limpeza usar agora. Normalmente e o valor do
        config (0 por padrao = nenhuma tecla). Vira 32 se a rede de
        seguranca tiver detectado que o login nao progride sem limpar."""
        if self._limpeza_reativada:
            return 32
        return self.clear_field_presses

    def _marcar_progresso_de_login(self):
        """Chamar quando o login claramente deu certo (chegamos na tela de
        servidor/personagem/fila ou no jogo)."""
        self._logins_sem_progresso = 0

    def _contar_tentativa_de_login(self):
        """Chamar toda vez que preenchemos conta/senha. Se isso acontecer
        varias vezes seguidas sem o login nunca progredir, provavelmente o
        campo nao estava vazio e o texto grudou -- entao religa a limpeza
        por teclado, mesmo ela sendo a suspeita da digitacao aleatoria: um
        bot que nao loga nao serve pra nada."""
        if self._limpeza_reativada or self._presses_de_limpeza() > 0:
            return
        self._logins_sem_progresso += 1
        if self._logins_sem_progresso >= 4:
            self._limpeza_reativada = True
            self.log.warning(
                "O login nao progrediu em %d tentativas seguidas sem limpar os campos "
                "-- religando a limpeza por teclado (Backspace/Delete). Se a digitacao "
                "aleatoria em outras janelas voltar junto, e essa limpeza a causa.",
                self._logins_sem_progresso,
            )

    def type_into(self, name, text):
        box = self.find(name)
        if not box:
            return False
        x, y, w, h = box
        cx, cy = x + w // 2, y + h // 2

        if self.mode == "background":
            metodo = self._win_input.type_into_field(
                self.hwnd, cx, cy, text,
                clear_presses=self._presses_de_limpeza(),
                allow_direct=self.direct_field_fill,
            )
            if metodo != self._fill_method_logged:
                self._fill_method_logged = metodo
                if metodo == "direto":
                    self.log.info(
                        "Campos preenchidos direto na janela (WM_SETTEXT), sem enviar "
                        "nenhuma tecla."
                    )
                else:
                    self.log.info(
                        "Campos preenchidos digitando tecla a tecla (os campos do jogo "
                        "nao sao controles de texto do Windows). Teclas de limpeza por "
                        "campo: %d.",
                        self.clear_field_presses,
                    )
        else:
            left = self.region[0] if self.region else 0
            top = self.region[1] if self.region else 0
            self._pyautogui.moveTo(left + cx, top + cy, duration=0.2)
            self._pyautogui.click()
            self._pyautogui.hotkey("ctrl", "a")
            self._pyautogui.press("delete")
            self._pyautogui.typewrite(text, interval=0.03)
        return True

    def note_state(self, name, message=None):
        if self.last_state_logged != name:
            self.log.info(message or f"Tela: {name}")
            self.last_state_logged = name
        self.consecutive_unknown = 0

    # ------------------------------------------------------------ launcher

    def _game_root_dir(self):
        """Pasta onde o jogo esta instalado, deduzida do launcher_exe_path
        configurado. None se nao tiver como saber (sem launcher configurado
        ou caminho invalido)."""
        launcher_path = _resolve_game_exe(self.launcher_exe_path)
        if launcher_path is None:
            return None
        try:
            return launcher_path.resolve().parent
        except OSError:
            return None

    def _is_real_game_process(self, pid):
        """Confere (melhor esforco) que esse pid E DE FATO um client.exe
        dentro da pasta do jogo configurada -- 'client.exe' e um nome de
        processo bem generico, usado por varios programas diferentes alem
        do jogo (ex: clientes de VPN, launchers de outros jogos, etc). Sem
        essa checagem, se outro programa com esse mesmo nome estiver rodando
        no PC, o bot pode acabar "adotando" a janela DELE por engano e
        mandando clique/digitacao (inclusive a senha da conta) pra ela --
        e isso aparece pro usuario como "o bot digitou coisas aleatorias em
        outra janela".

        Se o caminho do executavel nao puder ser verificado (sem permissao,
        processo protegido, ou sem launcher_exe_path configurado pra
        comparar), deixa passar -- e melhor arriscar um falso positivo raro
        do que travar o bot todo por conta de uma checagem que nao consegue
        se provar. NAO da pra usar o titulo da janela como plano B aqui: a
        janela do jogo se chama literalmente 'Game' (nao contem "Talisman"),
        entao uma checagem por titulo rejeitaria a janela CERTA."""
        game_root = self._game_root_dir()
        if game_root is None:
            return True
        exe_path = self._win_input.pid_exe_path(pid)
        if exe_path is None:
            return True
        try:
            exe_path.resolve().relative_to(game_root)
            self.log.debug("Pid %d confirmado pelo caminho do executavel: %s", pid, exe_path)
            return True
        except ValueError:
            self.log.warning(
                "Ignorei um processo 'client.exe' (pid %d, em '%s') que NAO "
                "esta dentro da pasta do jogo configurada ('%s') -- deve ser "
                "outro programa com o mesmo nome, nao o jogo. Vou continuar "
                "procurando o client.exe certo.",
                pid, exe_path, game_root,
            )
            return False

    def _try_claim_pid(self, pid):
        """Tenta 'adotar' um pid de client.exe como sendo o desta conta.
        Retorna False se outra conta desta sessao ja adotou esse pid antes
        (protege contra duas contas travarem na mesma janela do jogo), ou se
        o processo nao parece ser de fato o jogo (veja _is_real_game_process)."""
        if not self._is_real_game_process(pid):
            return False
        with _claimed_pids_lock:
            if pid in _claimed_client_pids:
                return False
            _claimed_client_pids.add(pid)
        self.target_pid = pid
        self.hwnd = None
        self.log.info("Jogo encontrado.")
        self.log.debug("Conta vinculada ao client.exe de pid %d.", pid)
        return True

    def handle_launcher_phase(self):
        """Garante que exista um client.exe rodando PARA ESTA CONTA e que o
        bot esteja travado (target_pid) exatamente nessa instancia -- mesmo
        que outras contas tenham suas proprias copias do jogo abertas ao
        mesmo tempo. Se um launcher_exe_path foi configurado, cuida tambem
        de abrir o launcher e clicar 'Genesis' -> 'Enter Game'. Retorna True
        se ainda esta cuidando disso (o resto do step() deve ser pulado
        nesse ciclo), ou False se ja ha um client.exe travado pra essa conta
        (segue o fluxo normal de login).

        Quando varias contas iniciam ao mesmo tempo, cada uma so abre o
        PROPRIO launcher depois que o launcher da conta anterior ja tiver
        fechado (_launcher_open_lock) -- o launcher (diferente do jogo em
        si) so aceita uma instancia aberta por vez."""
        if self.mode != "background":
            return False

        wi = self._win_input

        if self.target_pid is not None:
            if wi.is_pid_alive(self.target_pid, self.process_name):
                return False
            self.log.warning("O jogo fechou.")
            self.release()
            self._launcher_pid = None
            self._client_pids_before_launch = set()

        if not self.launcher_exe_path:
            # Sem launcher configurado: tenta adotar um client.exe que ja
            # esteja aberto e que nenhuma outra conta desta sessao tenha
            # adotado ainda. Isso funciona bem com uma conta por vez; pra
            # logar varias contas ao mesmo tempo SEM configurar o launcher,
            # nao ha como saber com certeza qual client.exe e de qual conta
            # -- configure o "Caminho do game.exe" pra isso funcionar direito.
            pids = wi.list_pids(self.process_name)
            if pids is None:
                self.note_state(
                    "sem_psutil",
                    "Nao consegui ver os programas abertos (falta o psutil).",
                )
                return False
            for pid in pids:
                if self._try_claim_pid(pid):
                    return False
            return False  # nenhum client.exe livre ainda -- refresh_frame vai avisar

        launcher_path = _resolve_game_exe(self.launcher_exe_path)
        launcher_name = launcher_path.name if launcher_path else "game.exe"

        if launcher_path is None:
            if not self._launcher_path_invalid_logged:
                self.note_state(
                    "launcher_caminho_invalido",
                    f"Nao achei o game.exe em: {self.launcher_exe_path}",
                )
                self._launcher_path_invalid_logged = True
            return True
        self._launcher_path_invalid_logged = False

        if self._launcher_pid is None:
            # So uma conta por vez pode ter um launcher.exe aberto -- se
            # outra conta ja esta com a vez, so espera (sem tentar abrir
            # nada ainda). Assim que essa outra conta terminar (launcher
            # dela fechar), o lock libera e a proxima da fila pega a vez.
            if not self._holds_launcher_lock:
                if not _launcher_open_lock.acquire(blocking=False):
                    self.note_state(
                        "aguardando_launcher_livre",
                        "Aguardando o launcher de outra conta terminar...",
                    )
                    return True
                self._holds_launcher_lock = True

            # Ainda nao pedimos pro launcher abrir nessa rodada. Guarda quais
            # client.exe ja existem ANTES de abrir, pra depois conseguir
            # identificar com certeza qual pid e NOVO (e portanto, desta
            # conta) -- mesmo que outras contas abram copias do jogo ao
            # mesmo tempo.
            existing = wi.list_pids(self.process_name)
            self._client_pids_before_launch = set(existing) if existing else set()
            try:
                import subprocess

                proc = subprocess.Popen([str(launcher_path)], cwd=str(launcher_path.parent))
                self._launcher_pid = proc.pid
                self.log.info("Abrindo o jogo...")
                self.log.debug("Launcher %s aberto com pid %d.", launcher_path, proc.pid)
            except Exception as exc:  # noqa: BLE001
                self.log.error("Nao consegui abrir o jogo: %s", exc)
                # Nao conseguiu nem abrir -- libera a vez pra proxima conta
                # em vez de segurar o lock esperando um launcher que nunca
                # vai existir.
                self._release_launcher_lock()
            return True

        # Ja pedimos pro launcher abrir. Antes de mais nada, confere se um
        # client.exe NOVO (que nao existia antes e que nenhuma outra conta
        # ja adotou) apareceu -- pode acontecer mesmo antes de a gente clicar
        # em qualquer coisa no launcher, se ele pular telas sozinho.
        current = wi.list_pids(self.process_name)
        current = set(current) if current else set()
        for pid in current - self._client_pids_before_launch:
            if self._try_claim_pid(pid):
                self._launcher_pid = None
                self._client_pids_before_launch = set()
                # O client.exe ja apareceu, entao o launcher ja cumpriu o
                # papel dele -- libera a vez pra proxima conta abrir o dela.
                self._release_launcher_lock()
                return False

        if not wi.is_pid_alive(self._launcher_pid):
            # O launcher fechou (normalmente porque ja abriu o client.exe,
            # logo depois de "Enter Game") -- a partir daqui a proxima conta
            # da fila ja pode abrir o proprio launcher, mesmo que o pid novo
            # do client.exe desta conta ainda nao tenha aparecido.
            self._release_launcher_lock()
            self.note_state("launcher_fechou_aguardando_client", "Carregando o jogo...")
            return True

        launcher_hwnd = wi.find_game_hwnd(pid=self._launcher_pid)
        if launcher_hwnd is None:
            self.note_state("launcher_sem_janela", "Esperando a janela do jogo...")
            return True

        frame = wi.capture_window_bgr(launcher_hwnd)
        if frame is None:
            return True

        from screen_match import match_template

        if "launcher_genesis_button" in self.raw_templates:
            box = match_template(frame, self.raw_templates["launcher_genesis_button"], self.confidence)
            if box:
                x, y, w, h = box
                self.attempts += 1
                self.log.info("Clicando em Genesis.")
                wi.click_in_window(launcher_hwnd, x + w // 2, y + h // 2)
                return True

        if "launcher_enter_game_button" in self.raw_templates:
            box = match_template(frame, self.raw_templates["launcher_enter_game_button"], self.confidence)
            if box:
                x, y, w, h = box
                self.attempts += 1
                self.log.info("Clicando em Enter Game.")
                wi.click_in_window(launcher_hwnd, x + w // 2, y + h // 2)
                return True

        self.note_state("launcher_desconhecido", "Nao reconheci a tela do launcher.")
        return True

    # --------------------------------------------------------------- loop

    def step(self):
        """Roda uma iteracao do loop principal. Retorna True se deve parar (sucesso)."""
        if self.handle_launcher_phase():
            return False

        self.refresh_frame()

        if self.screen_bgr is None:
            self.consecutive_unknown += 1
            if self.consecutive_unknown % 10 == 1:
                self.log.warning("Nao achei a janela do jogo -- ela nao pode estar minimizada.")
            return False

        # 0) sucesso?
        if self.has("success_indicator") and self.find("success_indicator"):
            self.log.info("Logado!")
            return True

        # 1) popups de erro/retry tem prioridade sobre qualquer outra tela
        if self.click("retry_button", label="Tentar novamente"):
            self._server_row_selected = False
            self._character_row_selected = False
            self._server_missing_since = None
            return False
        if self.click("ok_button", label="Ok"):
            # Depois de um erro (ex: "Connection interrupted"), o fluxo comeca
            # de novo do zero -- entao a selecao de servidor/personagem
            # tambem precisa ser refeita quando chegarmos la de novo.
            self._server_row_selected = False
            self._character_row_selected = False
            self._server_missing_since = None
            return False

        # 2) "Connecting to the server, please wait a moment." -- as vezes
        # essa tela trava e nao sai sozinha. Se ficar visivel sem interrupcao
        # por mais que connecting_timeout_seconds, clica em Cancel e deixa o
        # loop normal (login/servidor/personagem) tentar de novo a partir da
        # tela que aparecer em seguida.
        if self.find("connecting_dialog"):
            self.note_state("connecting_dialog", "Conectando ao servidor...")
            if self._connecting_since is None:
                self._connecting_since = time.time()
            elif time.time() - self._connecting_since >= self.connecting_timeout_seconds:
                if self.click("connecting_cancel_button", label="Cancelar (travado conectando)"):
                    self.log.warning(
                        "Tela 'Conectando ao servidor' travada ha mais de %ds -- "
                        "cancelei pra tentar logar de novo.",
                        self.connecting_timeout_seconds,
                    )
                    self._connecting_since = None
                    self._server_row_selected = False
                    self._character_row_selected = False
                    self._server_missing_since = None
            return False
        self._connecting_since = None

        # 3) tela de conta/senha
        if self.find("login_dialog"):
            self.note_state("login_dialog", "Tela de login.")
            if self.account and self.password:
                typed_account = self.type_into("account_field", self.account)
                typed_password = self.type_into("password_field", self.password)
                if typed_account or typed_password:
                    self.log.info("Conta e senha digitadas.")
                    self._contar_tentativa_de_login()
                    time.sleep(0.3)
            if self.click("login_ok_button", label="Ok"):
                return False
            return False

        # 4) tela de escolha de servidor
        if self.find("server_list_title"):
            self.note_state("server_list_title", "Escolhendo o servidor.")
            # Chegar aqui prova que a conta/senha foram aceitas.
            self._marcar_progresso_de_login()
            server_name = self.perfil.get("server_name")
            # Clica no servidor certo SO UMA VEZ -- depois disso o nome dele
            # continua na tela (selecionado) e ficaria clicando pra sempre
            # sem nunca chegar no botao Ok, se a gente nao controlasse isso.
            if server_name and self.has("server_row_template") and not self._server_row_selected:
                if self.click("server_row_template", label=f"{server_name}"):
                    self._server_row_selected = True
                    self._server_missing_since = None
                    return False
                # O servidor configurado nao apareceu na lista -- pode estar
                # so demorando a carregar, ou pode estar OFFLINE (nesse caso
                # ele simplesmente some da lista). NAO clica em Ok aqui: sem
                # o servidor certo selecionado, "Ok" entraria em QUALQUER
                # servidor que estiver marcado por padrao na lista, que e
                # exatamente o bug reportado. Da um tempo curto pra lista
                # carregar antes de desistir e voltar pro login.
                if self._server_missing_since is None:
                    self._server_missing_since = time.time()
                elif time.time() - self._server_missing_since >= self.server_missing_timeout_seconds:
                    if self.click("server_cancel_button", label="Cancelar (servidor nao apareceu)"):
                        self.log.warning(
                            "Servidor '%s' nao apareceu na lista (pode estar offline) -- "
                            "voltando pro login pra tentar de novo.",
                            server_name,
                        )
                    self._server_missing_since = None
                    self._server_row_selected = False
                return False
            self._server_missing_since = None
            if self.click("server_ok_button", label="Ok"):
                return False
            return False

        # 5) tela de escolha de personagem
        if self.find("character_select_title"):
            self.note_state("character_select_title", "Escolhendo o personagem.")
            self._marcar_progresso_de_login()
            character_name = self.perfil.get("character_name")
            # Mesma logica do servidor: seleciona o personagem certo (pode
            # estar na caixa da esquerda OU da direita -- o template acha em
            # qualquer posicao) SO UMA VEZ, depois clica em Enter Game.
            if character_name and self.has("character_row_template") and not self._character_row_selected:
                if self.click("character_row_template", label=f"{character_name}"):
                    self._character_row_selected = True
                    return False
            if self.click("enter_game_button", label="Enter Game"):
                return False
            return False

        # 6) fila -- so observa, NUNCA clica (nem no Cancel dela)
        if self.find("queue_dialog_title"):
            self.note_state("queue_dialog_title", "Na fila. Aguardando.")
            self._marcar_progresso_de_login()
            return False

        # 7) nada reconhecido
        self.consecutive_unknown += 1
        self.last_state_logged = None
        if self.consecutive_unknown >= self.max_unknown:
            self.log.warning("Nao reconheci nenhuma tela nas ultimas %d checagens. Pausando 30s.",
                             self.consecutive_unknown)
            time.sleep(30)
            self.consecutive_unknown = 0
        return False


def load_raw_templates(cfg):
    from screen_match import load_template_bgr

    raw = {}
    for name, rel_path in cfg.get("templates", {}).items():
        full_path = RESOURCE_DIR / rel_path
        if not full_path.exists():
            log.debug("Template '%s' nao encontrado em %s (ignorando por enquanto).", name, full_path)
            continue
        try:
            raw[name] = load_template_bgr(full_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Nao consegui carregar o template '%s': %s", name, exc)
    return raw


def build_bot(profile=None):
    """Monta um Bot pronto pra usar (le config.json + templates + perfil).
    Retorna (bot, cfg) ou (None, cfg) se faltar template essencial."""
    cfg = load_config()
    raw_templates = load_raw_templates(cfg)

    if not raw_templates:
        log.error(
            "Nenhum template encontrado na pasta templates/. Confira o config.json "
            "e o README.md antes de rodar."
        )
        return None, cfg

    if "success_indicator" not in raw_templates:
        log.warning(
            "Template 'success_indicator' ainda nao configurado -- o bot funciona, "
            "mas nao vai saber avisar/parar sozinho quando voce ja estiver dentro "
            "do jogo. Veja o README.md."
        )

    if profile is None:
        # So acontece rodando sem interface (--nogui/--headless) e sem um
        # perfil explicito: usa o primeiro cadastrado, ja que nao ha usuario
        # ali na hora pra escolher.
        profile = profiles.get_default_profile()
        if not profile:
            log.warning(
                "Nenhum perfil cadastrado ainda (conta/servidor/personagem). O bot "
                "roda mesmo assim, mas so vai clicar em Ok sem digitar nada nem "
                "escolher servidor/personagem ativamente. Cadastre um perfil na "
                "interface grafica, ou rode 'python bot.py --setup'."
            )

    return Bot(cfg, raw_templates, profile), cfg


def run(bot, cfg, stop_event=None):
    """Roda o loop principal ate: sucesso, PARAR.txt, stop_event, ou Ctrl+C."""
    bot.log.info("Bot iniciado.")

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                bot.log.info("Parando...")
                break

            if STOP_FILE.exists():
                bot.log.info("PARAR.txt encontrado. Parando...")
                break

            if bot.step():
                break

            random_delay(cfg)

    except KeyboardInterrupt:
        bot.log.info("Interrompido.")
    finally:
        # Libera o pid de client.exe que essa conta tinha travado, pra outra
        # conta poder usar (ou pra essa mesma conta poder pegar um novo, se
        # o bot for iniciado de novo depois).
        bot.release()

    bot.log.info("Bot parado.")


def main():
    bot, cfg = build_bot()
    if bot is None:
        return
    run(bot, cfg)


def _run():
    argv = sys.argv[1:]
    if "--setup" in argv:
        # Configuracao de perfil por texto (sem abrir a interface grafica).
        import setup_perfil

        setup_perfil.main()
    elif "--nogui" in argv or "--headless" in argv:
        main()
    else:
        # Padrao: abre a interface grafica (cadastro de contas + Iniciar/Parar).
        import gui

        gui.main()


def _show_fatal_error(exc_text):
    """Mostra um erro fatal (que aconteceu antes/fora da interface grafica
    normal, ex: config.json invalido) numa caixinha de dialogo -- assim nao
    precisamos manter uma janela de terminal/console aberta so pra dar
    tempo de ler o erro. Se nem o Tkinter conseguir abrir, cai pra
    print+pausar no console como ultimo recurso."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Talisman Online - Login Bot",
            "O bot encontrou um erro e precisou parar:\n\n"
            + exc_text[-1500:]
            + f"\n\nOs detalhes completos foram salvos em:\n{LOG_PATH}",
        )
        root.destroy()
    except Exception:  # noqa: BLE001 - ultimo recurso mesmo
        print(exc_text)
        try:
            input("\nPressione Enter para fechar esta janela...")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    try:
        _run()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - queremos capturar QUALQUER erro aqui
        import traceback

        tb_text = traceback.format_exc()
        try:
            log.error("Erro fatal: %s", tb_text)
        except Exception:  # noqa: BLE001
            pass
        _show_fatal_error(tb_text)
