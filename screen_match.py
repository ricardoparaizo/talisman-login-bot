"""
Reconhecimento de tela com suporte a diferentes resolucoes do jogo.

O Talisman Online deixa escolher a resolucao nas opcoes de video (de 800x600
até 1920x1080 widescreen). Os templates em templates/ foram recortados de
prints numa janela de ~1024x768 (a resolucao mais usada, segundo o
`base_resolution_width/height` em config.json). Se o jogo estiver rodando
numa resolucao diferente, os elementos da interface aparecem maiores ou
menores na tela -- por isso, em vez de procurar so no tamanho original do
template (que so bateria certinho em 1024x768), este modulo:

1. Tenta localizar a janela do jogo pelo titulo e le o tamanho real dela.
2. Calcula um fator de escala comparando esse tamanho com a resolucao base.
3. Redimensiona os templates por esse fator antes de procurar na tela.

Se a janela do jogo nao for encontrada (por exemplo, se o titulo mudar), o
bot cai de volta para o comportamento simples: procura na tela toda, sem
redimensionar (equivalente a assumir escala 1.0 / resolucao base).
"""

import logging

import cv2
import numpy as np

log = logging.getLogger("talisman-bot")

# pyautogui so e necessario no modo "foreground" (screenshot_region_bgr).
# Import tardio (dentro da funcao) pra nao exigir essa dependencia quando o
# bot roda so em modo "background" (janela do jogo via win_input/pywin32).

try:
    import pygetwindow as gw
except ImportError:  # pygetwindow e opcional -- sem ele, so perdemos o
    gw = None        # ajuste automatico de resolucao, o resto funciona igual.


def find_game_window(title_keyword="Talisman"):
    """Localiza a janela do jogo pelo titulo. Retorna (left, top, width, height) ou None."""
    if gw is None:
        return None
    try:
        candidates = [w for w in gw.getAllWindows() if title_keyword.lower() in w.title.lower()]
    except Exception as exc:  # noqa: BLE001
        log.debug("Erro procurando a janela do jogo: %s", exc)
        return None
    for w in candidates:
        try:
            if w.width > 0 and w.height > 0 and not w.isMinimized:
                return (w.left, w.top, w.width, w.height)
        except Exception:  # noqa: BLE001 - alguma janela pode nao suportar isMinimized etc.
            continue
    return None


def compute_scale(window_width, window_height, base_width, base_height):
    """Fator de escala comparando a janela atual com a resolucao em que os
    templates foram capturados. Usa a media entre largura/altura porque as
    duas costumam ficar bem proximas (mesma proporcao de tela)."""
    if not window_width or not window_height or not base_width or not base_height:
        return 1.0
    scale_w = window_width / base_width
    scale_h = window_height / base_height
    return (scale_w + scale_h) / 2


def get_capture_context(base_width, base_height, window_title_keyword):
    """Retorna dict com 'region' (pra tirar o screenshot) e 'scale' (pra
    redimensionar os templates), tentando achar a janela do jogo."""
    rect = find_game_window(window_title_keyword)
    if rect:
        _, _, width, height = rect
        scale = compute_scale(width, height, base_width, base_height)
        return {"region": rect, "scale": scale}
    return {"region": None, "scale": 1.0}


def load_template_bgr(path):
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Nao consegui ler o template de imagem: {path}")
    return img


def scale_template(template_bgr, scale):
    if abs(scale - 1.0) < 0.02:
        return template_bgr
    h, w = template_bgr.shape[:2]
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(template_bgr, (new_w, new_h), interpolation=interp)


def screenshot_region_bgr(region):
    """region = (left, top, width, height) ou None para a tela toda.
    So usado no modo 'foreground' -- por isso importa pyautogui aqui dentro."""
    import pyautogui

    img = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
    arr = np.array(img)  # RGB
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def match_template(screen_bgr, template_bgr, confidence):
    """Procura template_bgr dentro de screen_bgr. Retorna (x, y, w, h)
    relativo ao screen_bgr (ou seja, relativo a 'region'), ou None."""
    th, tw = template_bgr.shape[:2]
    if th == 0 or tw == 0 or th > screen_bgr.shape[0] or tw > screen_bgr.shape[1]:
        return None
    result = cv2.matchTemplate(screen_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= confidence:
        return (max_loc[0], max_loc[1], tw, th)
    return None
