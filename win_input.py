"""
Automacao em SEGUNDO PLANO da janela do jogo (processo client.exe / Talisman
Online).

Por que isso existe:
    O modo "foreground" (baseado em pyautogui) move o CURSOR REAL do mouse e
    exige que a janela do jogo esteja em primeiro plano -- ou seja, voce nao
    pode usar o PC pra mais nada enquanto o bot roda. Este modulo manda
    clique e digitacao DIRETO pra janela do jogo através de mensagens do
    proprio Windows (PostMessage), sem mover o cursor real e sem precisar
    que a janela esteja em foco -- assim voce continua usando o mouse/
    teclado normalmente em outros programas enquanto o bot cuida do login.

Como encontra a janela:
    De preferencia pelo PROCESSO (client.exe, via psutil) -- mais confiavel
    que o titulo da janela, que muda dependendo do servidor selecionado
    ("Talisman Online | Sky Ice (GSM&BI) | ver.6400" etc). Se o psutil nao
    estiver instalado ou o processo nao for encontrado, cai de volta para
    procurar pelo texto do titulo.

Limitacoes (leia antes de confiar 100% nisso):
    - A janela do jogo NAO pode estar minimizada (pode estar atras de outras
      janelas / em outro monitor / area de trabalho, so nao minimizada).
    - Cliques em segundo plano funcionam bem pra jogos que tratam clique via
      mensagens de janela padrao do Windows -- comum em jogos antigos como
      esse (o dialogo de login/servidor e desenhado pelo proprio jogo em
      cima de uma janela Win32 normal, nao overlay DirectInput). Se algum
      elemento especifico nao reagir em segundo plano, mude "input_mode"
      para "foreground" no config.json como alternativa (aí volta a
      precisar da janela em primeiro plano e do mouse livre).
"""

import ctypes
import logging
import time
from pathlib import Path

import numpy as np
import pywintypes
import win32api
import win32con
import win32gui
import win32process
import win32ui

log = logging.getLogger("talisman-bot")

try:
    import psutil
except ImportError:
    psutil = None

PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2

# Chamando PrintWindow direto via ctypes (em vez de win32gui.PrintWindow, que
# nem sempre fica exposto dependendo da versao do pywin32). Define os tipos
# explicitamente (c_void_p pros handles) pra evitar truncamento em Windows
# 64-bit, onde handles podem ser maiores que um int de 32 bits.
_PrintWindow = ctypes.windll.user32.PrintWindow
_PrintWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
_PrintWindow.restype = ctypes.c_int

def _window_process_name(hwnd):
    if psutil is None:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name()
    except Exception:  # noqa: BLE001
        return None


def is_process_running(process_name):
    """Verifica se existe algum processo com esse nome (ex: 'client.exe')
    rodando. Retorna None se o psutil nao estiver disponivel (nesse caso o
    bot nao consegue checar isso e deve assumir o pior caso do lado de fora)."""
    if psutil is None or not process_name:
        return None
    name = process_name.lower()
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() == name:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def list_pids(process_name):
    """Lista os PIDs de TODOS os processos com esse nome (ex: 'client.exe').
    Usado pra logar varias contas ao mesmo tempo: cada uma abre a sua propria
    copia do jogo, e precisamos distinguir qual pid e de qual conta. Retorna
    None se o psutil nao estiver disponivel."""
    if psutil is None or not process_name:
        return None
    name = process_name.lower()
    pids = []
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() == name:
                pids.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def pid_exe_path(pid):
    """Devolve o caminho completo do executavel de um pid (ou None se nao
    conseguir -- pid inexistente, sem permissao, ou psutil indisponivel).
    Usado pra confirmar que um processo achado pelo NOME (ex: 'client.exe')
    e de fato o do jogo, e nao outro programa qualquer que por coincidencia
    tenha o mesmo nome de processo -- 'client.exe' e um nome bem generico."""
    if psutil is None or pid is None:
        return None
    try:
        return Path(psutil.Process(pid).exe())
    except Exception:  # noqa: BLE001
        return None


def is_pid_alive(pid, expected_name=None):
    """Confere se um pid especifico ainda existe -- e, se `expected_name` for
    informado, se ainda e o MESMO processo esperado (o Windows pode reciclar
    o numero de um pid pra outro processo depois que o original fecha, isso
    evita um falso positivo raro nesse caso)."""
    if psutil is None or pid is None:
        return False
    try:
        if not psutil.pid_exists(pid):
            return False
        if expected_name:
            return psutil.Process(pid).name().lower() == expected_name.lower()
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def find_game_hwnd(title_keyword="Talisman", process_name="client.exe", pid=None):
    """Acha o HWND da janela do jogo.

    Se `pid` for informado, procura SO por uma janela visivel que pertenca
    exatamente a esse processo -- usado quando varias copias do jogo (uma
    por conta) podem estar rodando ao mesmo tempo, pra garantir que cada
    bot so ve/clica na janela da SUA propria conta. Se `pid` for None, cai
    no comportamento antigo (por nome de processo, com fallback pro titulo
    da janela) -- so seguro quando existe uma UNICA instancia rodando."""
    found = {"hwnd": None}

    def _enum_handler(hwnd, _):
        if found["hwnd"] is not None or not win32gui.IsWindowVisible(hwnd):
            return

        if pid is not None:
            try:
                _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            except pywintypes.error:
                return
            matched = wpid == pid
        else:
            matched = False
            if process_name:
                pname = _window_process_name(hwnd)
                if pname and pname.lower() == process_name.lower():
                    matched = True
            if not matched and title_keyword:
                title = win32gui.GetWindowText(hwnd)
                if title_keyword.lower() in title.lower():
                    matched = True

        if matched:
            try:
                left, top, right, bottom = win32gui.GetClientRect(hwnd)
            except pywintypes.error:
                return
            if (right - left) > 0 and (bottom - top) > 0:
                found["hwnd"] = hwnd

    win32gui.EnumWindows(_enum_handler, None)
    return found["hwnd"]


def get_client_size(hwnd):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return (right - left, bottom - top)


def capture_window_bgr(hwnd):
    """Tira um 'print' do conteudo da janela mesmo em segundo plano (mas NAO
    minimizada). Retorna um array BGR (formato OpenCV), ou None se falhar
    (inclusive se a janela fechar/mudar durante a captura -- isso e normal,
    por exemplo quando um clique faz o launcher fechar e abrir o jogo)."""
    try:
        width, height = get_client_size(hwnd)
    except pywintypes.error:
        return None
    if width <= 0 or height <= 0:
        return None

    try:
        # GetDC (nao GetWindowDC) pega o DC so da AREA DE CLIENTE -- do mesmo
        # jeito que get_client_size mede so a area de cliente. Usar GetWindowDC
        # aqui capturaria a janela inteira (incluindo a barra de titulo), que
        # nao bate com o tamanho do bitmap (so client area) e faz a comparacao
        # de imagem nunca dar certo.
        hwnd_dc = win32gui.GetDC(hwnd)
    except pywintypes.error:
        return None

    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)

            # PrintWindow via ctypes direto no user32.dll -- em algumas versoes do
            # pywin32, win32gui.PrintWindow nao fica exposto, mas a funcao do
            # Windows sempre existe. Assim evitamos depender disso.
            # PW_CLIENTONLY (1) + PW_RENDERFULLCONTENT (2): renderiza SO a area
            # de cliente (sem barra de titulo/bordas), do jeito accurate que
            # tambem funciona em segundo plano.
            result = _PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            if result != 1:
                log.debug("PrintWindow retornou %s (janela pode estar minimizada/fechada).", result)
                return None

            bmp_info = bitmap.GetInfo()
            bmp_bits = bitmap.GetBitmapBits(True)
            img = np.frombuffer(bmp_bits, dtype=np.uint8).copy()
            img.shape = (bmp_info["bmHeight"], bmp_info["bmWidth"], 4)
            img_bgr = img[:, :, :3].copy()  # descarta o canal alpha
        finally:
            # Cada limpeza vai no seu proprio try: se a janela do jogo fechou
            # no meio da captura (acontece o tempo todo -- o cliente cai, o
            # launcher fecha), o Windows ja invalidou esses handles sozinho e
            # a liberacao falha. Isso NAO e um erro de verdade, mas se
            # escapar daqui derruba a thread inteira da conta (foi o
            # "win32ui.error: DeleteDC failed" que parou o bot). Cada uma
            # separada tambem garante que uma falha nao impeca as seguintes
            # de rodar, o que vazaria memoria de video a cada ciclo.
            for _liberar in (
                lambda: win32gui.DeleteObject(bitmap.GetHandle()),
                save_dc.DeleteDC,
                mfc_dc.DeleteDC,
            ):
                try:
                    _liberar()
                except (pywintypes.error, win32ui.error) as exc:
                    log.debug("Limpeza da captura falhou (janela fechou no meio?): %s", exc)
    except (pywintypes.error, win32ui.error):
        return None
    finally:
        try:
            win32gui.ReleaseDC(hwnd, hwnd_dc)
        except (pywintypes.error, win32ui.error) as exc:
            log.debug("ReleaseDC falhou (janela fechou no meio?): %s", exc)

    return img_bgr


def _lparam(x, y):
    return win32api.MAKELONG(int(x), int(y))


def click_in_window(hwnd, x, y):
    """Clica em (x, y) -- coordenadas relativas ao CLIENT AREA da janela --
    sem mover o cursor real do mouse e sem exigir foco na janela.

    Um clique pode legitimamente fazer a janela fechar sozinha (ex: clicar
    em "Enter Game" no launcher faz ele fechar e abrir o client.exe) --
    entao se o handle da janela ficar invalido NO MEIO do clique (entre o
    "mouse down" e o "mouse up"), isso e esperado, nao um erro real. Por
    isso pegamos pywintypes.error aqui em vez de deixar isso derrubar o bot
    inteiro."""
    lp = _lparam(x, y)
    try:
        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lp)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
        time.sleep(0.05)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
    except pywintypes.error as exc:
        log.debug("Clique nao completou -- a janela provavelmente fechou/mudou durante o clique: %s", exc)


def _key_tap(hwnd, vk_code, delay=0.01):
    try:
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0)
    except pywintypes.error as exc:
        log.debug("Tecla nao enviada -- a janela provavelmente fechou/mudou: %s", exc)
        return False
    time.sleep(delay)
    return True


def clear_field(hwnd, max_presses=32):
    """Limpa o conteudo de um campo usando Backspace + Delete repetidos --
    mais compativel com campos de texto customizados (comuns em jogos
    antigos) do que Ctrl+A, que muitos deles nao implementam.

    max_presses=0 desliga a limpeza por completo (nenhuma tecla enviada)."""
    if max_presses <= 0:
        return
    for _ in range(max_presses):
        if not _key_tap(hwnd, win32con.VK_BACK):
            return
    for _ in range(max_presses):
        if not _key_tap(hwnd, win32con.VK_DELETE):
            return


def type_text(hwnd, text, delay=0.02):
    for ch in text:
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CHAR, ord(ch), 0)
        except pywintypes.error as exc:
            log.debug("Digitacao interrompida -- a janela provavelmente fechou/mudou: %s", exc)
            return
        time.sleep(delay)


# ------------------------------------------- preenchimento sem teclado ----
# Se os campos de conta/senha forem controles de texto DE VERDADE do Windows
# (classe "Edit" e parecidas), da pra escrever neles com uma unica mensagem
# WM_SETTEXT, SEM enviar nenhuma tecla. Isso importa porque o jogo (ou o
# anti-cheat dele) parece reagir as teclas sinteticas re-injetando teclado
# de verdade no Windows -- o que aparece como "texto aleatorio" na janela
# que voce estiver usando. Sem teclas enviadas, nao ha o que re-injetar.
#
# Se os campos forem desenhados pelo proprio jogo (comum em jogos DirectX),
# nao existe controle "Edit" nenhum ali, WM_SETTEXT nao se aplica, e o bot
# volta sozinho pro jeito antigo (clicar + digitar via WM_CHAR).

_EDIT_CLASSES = {
    "edit", "richedit", "richedit20a", "richedit20w", "richedit50w",
    "textbox", "threadrichedit",
}


def _edit_control_at(hwnd, x, y):
    """Devolve o controle de texto do Windows que esta em (x, y) -- x/y
    relativos a area de cliente de `hwnd`. Devolve None se ali nao houver
    um controle de texto de verdade (campo desenhado pelo jogo, por
    exemplo).

    Cuidado importante: NUNCA devolve o proprio `hwnd`. Mandar WM_SETTEXT
    pra janela principal do jogo trocaria o TITULO dela, nao o campo."""
    try:
        sx, sy = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
        child = win32gui.WindowFromPoint((sx, sy))
    except pywintypes.error:
        return None
    if not child or child == hwnd:
        return None
    try:
        classe = (win32gui.GetClassName(child) or "").lower()
    except pywintypes.error:
        return None
    if classe not in _EDIT_CLASSES:
        return None
    # Tem que pertencer ao MESMO processo do jogo -- se o ponto calhar de
    # cair numa janela de outro programa que esteja por cima, escrever nela
    # seria exatamente o tipo de vazamento que estamos tentando evitar.
    try:
        _, child_pid = win32process.GetWindowThreadProcessId(child)
        _, game_pid = win32process.GetWindowThreadProcessId(hwnd)
    except pywintypes.error:
        return None
    if child_pid != game_pid:
        return None
    return child


def try_set_text_directly(hwnd, x, y, text):
    """Tenta preencher o campo em (x, y) com WM_SETTEXT, sem enviar tecla
    nenhuma. Retorna True so se conseguiu E confirmou que o campo ficou com
    o texto certo -- se nao der pra confirmar, retorna False pro chamador
    usar o jeito antigo (mais vale digitar do que preencher errado)."""
    child = _edit_control_at(hwnd, x, y)
    if child is None:
        return False
    try:
        win32gui.SendMessage(child, win32con.WM_SETTEXT, 0, text)
        conferido = win32gui.GetWindowText(child)
        tamanho = win32gui.SendMessage(child, win32con.WM_GETTEXTLENGTH, 0, 0)
    except pywintypes.error as exc:
        log.debug("WM_SETTEXT falhou no controle de texto: %s", exc)
        return False
    # Campos de senha costumam nao devolver o texto real por seguranca --
    # por isso o tamanho tambem serve como confirmacao.
    return conferido == text or tamanho == len(text)


def type_into_field(hwnd, x, y, text, clear_presses=32, allow_direct=True):
    """Preenche o campo em (x, y) -- coordenadas relativas a area de cliente.

    Tenta primeiro o caminho SEM TECLADO (WM_SETTEXT). So se ele nao servir
    e que cai no jeito antigo: clicar, limpar com Backspace/Delete e digitar
    caractere a caractere. Retorna qual caminho foi usado ("direto" ou
    "teclado"), pra quem chamou poder registrar no log."""
    if allow_direct and try_set_text_directly(hwnd, x, y, text):
        return "direto"
    click_in_window(hwnd, x, y)
    time.sleep(0.15)
    clear_field(hwnd, max_presses=clear_presses)
    type_text(hwnd, text)
    return "teclado"
