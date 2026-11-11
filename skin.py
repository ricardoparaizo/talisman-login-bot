"""
Pele visual do bot no estilo Apple TV (tvOS), seguindo o design system da
Apple (Human Interface Guidelines): cores de sistema do modo escuro,
hierarquia de rotulos, escala tipografica e "materiais" de vidro.

Por que existe um modulo so pra isso:
    O gui.py cuida do que a tela FAZ (cadastrar conta, iniciar, mostrar
    log). Este arquivo cuida de como ela PARECE. Separado, da pra mexer no
    visual inteiro sem arriscar a logica -- e da pra voltar atras trocando
    um import (o tema roxo anterior esta em skin_roxo.py).

O vocabulario visual deste tema:
    - Fundo: arte colorida e bem desfocada (como a capa do conteudo que o
      Apple TV mostra borrada atras da interface). E uma imagem gerada (ver
      canvas_image / GRADIENT_BLOBS).
    - Paineis de VIDRO ("Liquid Glass"): cada painel tem a cor do fundo que
      esta atras dele misturada com o cinza de material da Apple -- parece
      que a arte atravessa o vidro --, uma borda de luz (reflexo forte no
      alto, sumindo pra baixo) e uma sombra suave que faz o painel flutuar.
    - Destaque = BRANCO: o botao principal e uma capsula branca com texto
      preto (como o "Play"), e a conta selecionada ganha contorno branco --
      o "foco" do tvOS.
    - Cor so pra estado, com as cores de sistema: systemGreen pra online,
      systemBlue pro que esta rodando.

Sobre o vidro: o CustomTkinter desenha tudo opaco (blur de verdade do
Windows -- Acrylic/Mica -- ja foi tentado e nao funciona com ele). Por isso
o vidro e SIMULADO: a tinta de cada painel e calculada aqui, uma vez, a
partir da propria arte do fundo, e os cartoes/campos/textos derivam dela.
"""

import tkinter as tk

# ------------------------------------------------- design system Apple ---

# Cores de sistema do modo escuro (HIG -> Color -> System colors, dark).
SYSTEM_BLUE = "#0a84ff"
SYSTEM_GREEN = "#30d158"
SYSTEM_RED = "#ff453a"
SYSTEM_ORANGE = "#ff9f0a"
SYSTEM_GRAY = "#8e8e93"
SYSTEM_GRAY2 = "#636366"
SYSTEM_GRAY3 = "#48484a"
SYSTEM_GRAY4 = "#3a3a3c"
SYSTEM_GRAY5 = "#2c2c2e"
SYSTEM_GRAY6 = "#1c1c1e"

# Escala tipografica (HIG -> Typography, tamanhos do macOS, que e o que
# cabe num app de desktop; o tvOS usa a mesma hierarquia, so maior).
TYPE = {
    "large_title": 26,
    "title1": 22,
    "title2": 17,
    "title3": 15,
    "headline": 13,     # negrito
    "body": 13,
    "callout": 12,
    "subheadline": 11,
    "footnote": 10,
    "caption": 10,
}

# Segoe UI Variable e o mais perto da SF Pro (fonte da Apple) que o Windows
# tem: "Display" nos titulos, "Text" no resto. Sem ela (Windows 10), o Tk
# usa a fonte padrao sozinho.
FONT = "Segoe UI Variable Text"
FONT_TITLE = "Segoe UI Variable Display"
FONT_MONO = "Consolas"


def rgb(hexa):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


def _hex(cor):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in cor)


def mix(a, b, t):
    """Cor `a` com `t` (0-1) de `b` por cima -- e assim que uma camada
    translucida (ex: branco a 8%) fica sobre uma cor solida."""
    ca, cb = rgb(a), rgb(b)
    return _hex(ca[i] * (1 - t) + cb[i] * t for i in range(3))


# ------------------------------------------------------------- fundo ----

# Arte do fundo: manchas de cor (centro x, centro y, raio, cor, intensidade),
# em fracao da janela, bem desfocadas. Escura o bastante pro texto branco
# continuar legivel, colorida o bastante pro vidro "pegar" a cor.
GRADIENT_BASE = "#030305"
GRADIENT_BLOBS = [
    (0.05, -0.05, 0.75, "#132a55", 0.70),  # azul escuro, canto de cima a esquerda
    (0.85, -0.05, 0.60, "#24123a", 0.55),  # violeta escuro, canto de cima a direita
    (1.00, 0.95, 0.60, "#082427", 0.45),   # petroleo bem escuro, canto de baixo
]

# Material de vidro: o quanto do fundo "atravessa" o painel, o cinza de
# material por cima, e um leve clareamento (o vidro reflete um pouco de luz).
GLASS_MIX = 0.38
GLASS_MATERIAL = "#15161b"
GLASS_LIFT = 7

# Retangulos aproximados dos dois paineis na janela padrao (1160x760) --
# so pra calcular a tinta do vidro de cada um (o fundo e suave; a tinta
# quase nao muda quando a janela e redimensionada).
_JANELA_PADRAO = (1160, 760)
_PAINEL_LATERAL = (34, 34, 346, 726)
_PAINEL_PRINCIPAL = (374, 34, 1126, 726)


def _arte(width, height, escala=6):
    """Arte do fundo em baixa resolucao (array float RGB)."""
    import numpy as np

    pw, ph = max(2, width // escala), max(2, height // escala)
    v, u = np.mgrid[0:1:ph * 1j, 0:1:pw * 1j]
    aspecto = width / max(1, height)   # manchas redondas, nao esticadas
    cor = np.empty((ph, pw, 3))
    cor[:] = rgb(GRADIENT_BASE)
    for cx, cy, raio, hexa, forca in GRADIENT_BLOBS:
        d2 = (((u - cx) * aspecto) ** 2 + (v - cy) ** 2) / (raio * raio)
        peso = (forca * np.exp(-2.0 * d2))[..., None]
        cor = cor * (1 - peso) + np.array(rgb(hexa)) * peso
    return cor


def _tinta_vidro(rect, tamanho=_JANELA_PADRAO, padrao="#17181d"):
    """Cor do vidro sobre a regiao `rect` da arte do fundo."""
    try:
        escala = 6
        cor = _arte(*tamanho, escala=escala)
        x0, y0, x1, y1 = (int(c / escala) for c in rect)
        media = cor[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)
        mat = rgb(GLASS_MATERIAL)
        return _hex(media[i] * GLASS_MIX + mat[i] * (1 - GLASS_MIX) + GLASS_LIFT for i in range(3))
    except Exception:  # noqa: BLE001 - sem numpy: um cinza de material fixo
        return padrao


GLASS_SIDEBAR = _tinta_vidro(_PAINEL_LATERAL)
GLASS_MAIN = _tinta_vidro(_PAINEL_PRINCIPAL)

# ----------------------------------------------------------- paleta ------
# Tudo abaixo deriva das tintas do vidro, como camadas translucidas:
# cartoes = vidro + um pouco de branco; campos = vidro + um pouco de preto.

BG_APP = "#000000"          # cor de base (barra de titulo e antes do fundo carregar)
BG_PANEL = GLASS_MAIN       # painel principal (vidro)
BG_SIDEBAR = GLASS_SIDEBAR  # barra lateral (vidro)
BG_CARD = mix(GLASS_SIDEBAR, "#ffffff", 0.06)       # cartoes de conta (vidro sobre vidro)
BG_SUNKEN = mix(GLASS_MAIN, "#000000", 0.45)        # dentro dos campos e do log
BG_ROW_HOVER = mix(GLASS_SIDEBAR, "#ffffff", 0.11)
BG_ROW_SEL = mix(GLASS_SIDEBAR, "#ffffff", 0.11)
BG_ROW_SEL_STRONG = mix(GLASS_SIDEBAR, "#ffffff", 0.17)  # conta selecionada (foco)

# Destaques. ACCENT_BRIGHT e o "foco" (branco): contorno da conta
# selecionada e do campo em foco. ACCENT (systemBlue) fica pras caixinhas.
ACCENT = SYSTEM_BLUE
ACCENT_BRIGHT = "#f5f5f7"
ACCENT_DIM = mix(GLASS_MAIN, "#ffffff", 0.14)   # item ativo em menus e listas
ACCENT_SOFT = SYSTEM_GRAY2                      # contorno da caixinha
CARD_ACTIVE = "#0a64e0"                         # cartao "rodando": systemBlue
CARD_ACTIVE_HOVER = "#1a72ea"
CARD_ACTIVE_EDGE = "#5aa7ff"
PILL_ON_ACTIVE = "#084aa8"

# Abas (Contas / Entrar Cave): capsula de vidro, a selecionada mais clara --
# como a barra de abas do topo do Apple TV.
TAB_BG = mix(GLASS_MAIN, "#000000", 0.30)
TAB_SEL = mix(GLASS_MAIN, "#ffffff", 0.24)
TAB_SEL_HOVER = mix(GLASS_MAIN, "#ffffff", 0.30)
TAB_HOVER = mix(GLASS_MAIN, "#ffffff", 0.08)

# Botoes
BTN_PRIMARY = "#f5f5f7"     # acao principal: capsula branca (como o "Play")
BTN_PRIMARY_HOVER = "#dcdce1"
BTN_PRIMARY_TEXT = "#000000"
BTN_BG = mix(GLASS_MAIN, "#ffffff", 0.10)       # capsula de vidro (secundaria)
BTN_HOVER = mix(GLASS_MAIN, "#ffffff", 0.17)

# Status
OK = SYSTEM_GREEN
DANGER = SYSTEM_RED         # erro no log
WARNING = SYSTEM_ORANGE     # aviso no log
PILL_BG = mix(GLASS_SIDEBAR, "#ffffff", 0.10)

# Chip de estado da conta (lista da esquerda): (fundo, texto, bolinha). O
# chip inteiro e colorido pelo estado, pra bater o olho.
CHIP_ONLINE = (mix(GLASS_SIDEBAR, SYSTEM_GREEN, 0.20), SYSTEM_GREEN, SYSTEM_GREEN)
CHIP_OFFLINE = (mix(GLASS_SIDEBAR, "#ffffff", 0.08), SYSTEM_GRAY, SYSTEM_GRAY2)
CHIP_ATIVO = ("#f5f5f7", "#0a64e0", SYSTEM_GREEN)   # branco no cartao azul
CHIP_NEUTRO = (mix(GLASS_SIDEBAR, "#ffffff", 0.08), SYSTEM_GRAY, SYSTEM_GRAY3)

# Texto -- hierarquia de rotulos da Apple (label / secondary / tertiary /
# quaternary sao branco-azulado com 100/60/30/18% de opacidade sobre o vidro).
TEXT = "#ffffff"
TEXT_SOFT = mix(GLASS_MAIN, "#ebebf5", 0.80)
TEXT_MUTED = mix(GLASS_MAIN, "#ebebf5", 0.60)   # secondaryLabel
TEXT_DIM = mix(GLASS_MAIN, "#ebebf5", 0.30)     # tertiaryLabel
TEXT_DISABLED = mix(GLASS_MAIN, "#ebebf5", 0.18)  # quaternaryLabel

# Bordas -- separadores e contornos finos, como o "separator" da Apple.
EDGE = mix(GLASS_SIDEBAR, "#ffffff", 0.07)
EDGE_STRONG = mix(GLASS_MAIN, "#ffffff", 0.16)  # campos e botoes, um pouco mais visiveis
EDGE_PANEL = mix(GLASS_MAIN, "#ffffff", 0.10)

# Barra de rolagem
SCROLLBAR_IDLE = mix(GLASS_MAIN, "#ffffff", 0.08)
SCROLLBAR_HOVER = mix(GLASS_MAIN, "#ffffff", 0.22)

# Cantos arredondados
RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 24
RADIUS_PILL = 999           # o CTk limita sozinho a metade da altura


# ------------------------------------------------------ util de cor ------

def colorref(hexa):
    """Cor no formato COLORREF do Windows (0x00BBGGRR) -- usado pra pintar
    a barra de titulo nativa da janela com a cor do fundo."""
    r, g, b = rgb(hexa)
    return r | (g << 8) | (b << 16)


def tracked(texto):
    """Espacamento entre letras. O Tk nao tem essa propriedade, entao
    intercalamos um espaco fino (U+2009)."""
    return " ".join(texto)


# ------------------------------------------------------- fundo -----------

# Quanto o cartao desenhado no fundo passa da area de conteudo (o frame do
# CTk, que e retangular) de cada lado. Precisa ser pelo menos ~30% do raio
# pra o canto quadrado do frame ficar inteiro DENTRO da curva do cartao.
CARD_INSET = 10

# Efeito de vidro dos paineis (ver canvas_image).
GLASS_SHADOW_OFFSET = 14     # px pra baixo
GLASS_SHADOW_BLUR = 26       # raio do desfoque da sombra
GLASS_SHADOW_ALPHA = 0.55
GLASS_RIM_TOP = 0.55         # brilho da borda de luz no alto do painel...
GLASS_RIM_BOTTOM = 0.07      # ...sumindo ate isso embaixo
GLASS_SHEEN = 0.06           # leve reflexo branco no terco de cima da borda

# Vidro de verdade (ui_kit.render_background): a arte atras do painel e
# desfocada mais um pouco e recebe a tinta do material por cima.
GLASS_BLUR = 26              # desfoque do fundo atras do vidro
GLASS_ALPHA = 0.55           # opacidade da tinta do material (0 = vidro limpo)
GLASS_WHITE = 0.03           # reflexo branco por cima de tudo

# Imagem de fundo da janela (relativa a pasta do programa). Se faltar, o
# fundo volta pra arte gerada (GRADIENT_BLOBS).
BACKGROUND_IMAGE = "assets/background.jpg"


def canvas_image(width, height, cards=(), cores=None):
    """Gera o fundo: a arte colorida desfocada (ver GRADIENT_BLOBS) com os
    paineis de vidro arredondados (`cards` = retangulos (x0, y0, x1, y1);
    `cores` = a tinta de vidro de cada um, na mesma ordem) desenhados por
    cima. Retorna uma imagem do Pillow (ou None se o Pillow/numpy faltar --
    ai fica so a cor solida do fundo e os paineis retos).

    Cada painel de vidro leva:
      - uma sombra suave embaixo (o painel "flutua" sobre a arte);
      - a tinta do vidro (a cor do fundo atras dele misturada com o
        material -- ver _tinta_vidro), igual a cor do frame do CTk que fica
        por cima, pra a emenda nao aparecer;
      - uma borda de luz: forte no alto, sumindo pra baixo, como o reflexo
        de uma placa de vidro iluminada de cima.

    Por que os paineis sao desenhados aqui e nao pelo CTk: um CTkFrame
    arredondado pinta o lado de fora da curva com uma cor solida (ele nao
    sabe que tem uma imagem atras), o que deixava um "quadrado" escuro em
    volta de cada cartao, tapando o fundo. Desenhando aqui, o canto, a
    sombra e o brilho ficam em cima da arte de verdade."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:  # noqa: BLE001
        return None

    # Calculado numa versao reduzida (a arte nao tem detalhe nenhum que se
    # perca) e ampliado -- fica instantaneo mesmo em tela cheia.
    escala = 6
    cor = _arte(width, height, escala)
    pequeno = Image.fromarray(cor.clip(0, 255).astype(np.uint8), "RGB")
    img = pequeno.resize((width, height), Image.BICUBIC)
    # Um pouco de ruido fino evita "degraus" visiveis no degrade.
    ruido = np.random.default_rng(7).normal(0, 1.2, (height, width, 1))
    img = Image.fromarray((np.asarray(img, dtype=np.float32) + ruido).clip(0, 255).astype(np.uint8))

    if not cards:
        return img

    tamanho = (width, height)
    cores = list(cores or [])
    raio = RADIUS_LG

    # 1) Sombra: todos os paineis juntos, deslocados pra baixo e desfocados.
    sombra = Image.new("L", tamanho, 0)
    sdraw = ImageDraw.Draw(sombra)
    for x0, y0, x1, y1 in cards:
        d = GLASS_SHADOW_OFFSET
        sdraw.rounded_rectangle([x0 + 4, y0 + d, x1 - 4, y1 + d], radius=raio, fill=255)
    sombra = sombra.filter(ImageFilter.GaussianBlur(GLASS_SHADOW_BLUR))
    sombra = sombra.point(lambda a: int(a * GLASS_SHADOW_ALPHA))
    img = Image.composite(Image.new("RGB", tamanho, (0, 0, 0)), img, sombra)

    # 2) Vidro + borda de luz, painel por painel. Desenhado em 3x e
    # reduzido -- e o que deixa a curva suave (o ImageDraw sozinho nao faz
    # antisserrilhado).
    ss = 3
    for i, (x0, y0, x1, y1) in enumerate(cards):
        tinta = cores[i] if i < len(cores) else BG_PANEL
        caixa = [x0 * ss, y0 * ss, x1 * ss - 1, y1 * ss - 1]

        preenchimento = Image.new("L", (width * ss, height * ss), 0)
        ImageDraw.Draw(preenchimento).rounded_rectangle(caixa, radius=raio * ss, fill=255)
        preenchimento = preenchimento.resize(tamanho, Image.LANCZOS)
        img = Image.composite(Image.new("RGB", tamanho, rgb(tinta)), img, preenchimento)

        contorno = Image.new("L", (width * ss, height * ss), 0)
        ImageDraw.Draw(contorno).rounded_rectangle(
            caixa, radius=raio * ss, outline=255, width=int(1.5 * ss)
        )
        contorno = np.asarray(contorno.resize(tamanho, Image.LANCZOS), dtype=np.float32) / 255.0

        # intensidade da borda: forte no alto do painel, sumindo pra baixo
        ys = np.arange(height, dtype=np.float32)[:, None]
        t = np.clip((ys - y0) / max(1.0, (y1 - y0)), 0, 1)
        brilho = GLASS_RIM_TOP + (GLASS_RIM_BOTTOM - GLASS_RIM_TOP) * np.sqrt(t)
        # um reflexo a mais no terco de cima (o "brilho" do vidro)
        brilho = brilho + GLASS_SHEEN * np.clip(1 - t * 3, 0, 1)
        alfa = (contorno * brilho).clip(0, 1)[..., None]
        base = np.asarray(img, dtype=np.float32)
        img = Image.fromarray((base * (1 - alfa) + 255.0 * alfa).clip(0, 255).astype(np.uint8))
    return img


# --------------------------------------------------------- widgets -------

class Divider(tk.Frame):
    """Separador de 1px, quase invisivel contra o cartao."""

    def __init__(self, master, bg=None):
        super().__init__(master, height=1, bg=EDGE, highlightthickness=0, bd=0)
