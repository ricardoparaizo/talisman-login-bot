"""
Pele visual do bot: cartoes roxo-escuros flutuando sobre um gradiente
roxo suave, com roxo/violeta como unico destaque.

Por que existe um modulo so pra isso:
    O gui.py cuida do que a tela FAZ (cadastrar conta, iniciar, mostrar
    log). Este arquivo cuida de como ela PARECE. Separado, da pra mexer no
    visual inteiro sem arriscar a logica -- e da pra voltar atras trocando
    um import.

O vocabulario visual deste tema (inspirado em painel de "agentes" de IA):
    - Fundo em gradiente: roxo intenso no alto, uma faixa quase preta no
      meio e um brilho claro lavanda subindo de baixo. E uma imagem gerada
      (ver canvas_image / GRADIENT_BLOBS), mostrada em volta dos cartoes.
    - Cartoes roxo-escuros com canto bem arredondado e borda de
      1px discreta -- e o que separa um cartao do fundo, sem sombra.
    - O cartao "ativo" (conta rodando) vira roxo vivo, como o card em destaque
      da referencia; o resto fica neutro.
    - Botoes em pilula. A acao principal e BRANCA com texto escuro (e o
      que mais chama atencao num tema escuro); as secundarias sao pilulas
      escuras com contorno.
    - Status em pilula com bolinha colorida ("● rodando"), verde pra ativo.
    - Rotulos em cinza discreto, sem cor -- a cor fica reservada pro que
      esta acontecendo de verdade.
"""

import tkinter as tk

# ----------------------------------------------------------- paleta ------

# Fundos -- roxo bem escuro, pra conversar com o gradiente roxo
# do fundo (cartao grafite/cinza ficava "sujo" em cima dele).
BG_APP = "#1a0b3d"          # cor de base (barra de titulo e antes do fundo carregar)
BG_PANEL = "#150b2e"        # cartoes grandes (barra lateral, area principal)
BG_SIDEBAR = BG_PANEL
BG_CARD = "#1f1440"         # cartoes pequenos dentro dos grandes (linhas de conta)
BG_SUNKEN = "#0f0822"       # dentro dos campos e do log
BG_ROW_HOVER = "#271a4e"
BG_ROW_SEL = "#2d1f5c"      # conta aberta no formulario

# Roxo/violeta -- o unico destaque do tema.
ACCENT = "#9b6cf0"
ACCENT_BRIGHT = "#c3a6ff"   # hover / foco
ACCENT_DIM = "#352066"      # fundo de menu ativo
ACCENT_SOFT = "#7050c0"     # contorno da caixinha
CARD_ACTIVE = "#5b2fc8"     # cartao "rodando": roxo vivo
CARD_ACTIVE_HOVER = "#6838d6"
CARD_ACTIVE_EDGE = "#9a74f0"
PILL_ON_ACTIVE = "#4524a0"  # pilula de status em cima do cartao roxo

# Botoes
BTN_PRIMARY = "#f7f4fd"     # acao principal: pilula branca
BTN_PRIMARY_HOVER = "#e0d8f2"
BTN_PRIMARY_TEXT = "#160b33"
BTN_BG = "#1f1548"          # pilula escura (secundaria)
BTN_HOVER = "#2a1d5a"

# Status
OK = "#4ade80"              # bolinha "rodando"
DANGER = "#f0717f"          # erro no log
WARNING = "#f2b866"         # aviso no log
PILL_BG = "#251a4e"

# Texto
TEXT = "#f6f3fc"
TEXT_SOFT = "#c4b9dd"
TEXT_MUTED = "#9184b3"
TEXT_DIM = "#5a4d84"
TEXT_DISABLED = "#433870"

# Bordas -- 1px discreta, so pra descolar o cartao do fundo.
EDGE = "#2a1e50"
EDGE_STRONG = "#382a68"     # campos e botoes, um pouco mais visiveis
EDGE_PANEL = "#3a2a72"

# Barra de rolagem
SCROLLBAR_IDLE = "#251a4e"
SCROLLBAR_HOVER = "#382a68"

# Manchas de cor do gradiente do fundo: (centro x, centro y, raio, cor,
# intensidade), com x/y/raio em fracao da janela. Aplicadas em ordem, cada
# uma por cima da anterior -- mexa aqui pra mudar o "clima" do fundo.
GRADIENT_BASE = "#12062e"
GRADIENT_BLOBS = [
    (0.10, 0.05, 0.75, "#5a24c8", 0.95),   # roxo intenso, canto de cima
    (0.95, 0.25, 0.60, "#3a1a9a", 0.80),   # roxo-anil, lado direito
    (0.60, 0.55, 0.38, "#09031f", 0.85),   # faixa escura no meio
    (1.00, 1.00, 0.45, "#a347d8", 0.55),   # toque magenta, canto de baixo
    (0.35, 1.15, 0.55, "#e0d2f8", 0.90),   # brilho claro lavanda subindo de baixo
]

# Cantos arredondados
RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 24
RADIUS_PILL = 999           # o CTk limita sozinho a metade da altura

FONT = "Segoe UI"            # fonte de interface padrao do Windows moderno
FONT_MONO = "Consolas"


# ------------------------------------------------------ util de cor ------

def rgb(hexa):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


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


def canvas_image(width, height, cards=()):
    """Gera o fundo: um gradiente roxo suave (manchas de cor bem
    espalhadas, ver GRADIENT_BLOBS) com os cartoes grandes arredondados
    (`cards` = retangulos (x0, y0, x1, y1)) desenhados por cima. Retorna
    uma imagem do Pillow (ou None se o Pillow/numpy faltar -- ai fica so a
    cor solida do fundo e os paineis retos).

    Por que os cartoes sao desenhados aqui e nao pelo CTk: um CTkFrame
    arredondado pinta o lado de fora da curva com uma cor solida (ele nao
    sabe que tem uma imagem atras), o que deixava um "quadrado" escuro em
    volta de cada cartao, tapando o fundo. Desenhando aqui, o canto fica
    em cima do gradiente de verdade."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        return None

    # Calculado numa versao reduzida (gradiente nao tem detalhe nenhum que
    # se perca) e ampliado -- fica instantaneo mesmo em tela cheia.
    escala = 6
    pw, ph = max(2, width // escala), max(2, height // escala)
    v, u = np.mgrid[0:1:ph * 1j, 0:1:pw * 1j]
    aspecto = width / max(1, height)   # manchas redondas, nao esticadas
    cor = np.empty((ph, pw, 3))
    cor[:] = rgb(GRADIENT_BASE)
    for cx, cy, raio, hexa, forca in GRADIENT_BLOBS:
        d2 = (((u - cx) * aspecto) ** 2 + (v - cy) ** 2) / (raio * raio)
        peso = (forca * np.exp(-2.0 * d2))[..., None]
        cor = cor * (1 - peso) + np.array(rgb(hexa)) * peso
    pequeno = Image.fromarray(cor.clip(0, 255).astype(np.uint8), "RGB")
    img = pequeno.resize((width, height), Image.BICUBIC)
    # Um pouco de ruido fino evita "degraus" visiveis no degrade.
    ruido = np.random.default_rng(7).normal(0, 1.2, (height, width, 1))
    img = Image.fromarray((np.asarray(img, dtype=np.float32) + ruido).clip(0, 255).astype(np.uint8))

    if cards:
        # Desenhado em 3x e reduzido -- e o que deixa a curva suave (o
        # ImageDraw sozinho nao faz antisserrilhado).
        ss = 3
        preenchimento = Image.new("L", (width * ss, height * ss), 0)
        contorno = Image.new("L", (width * ss, height * ss), 0)
        fdraw, cdraw = ImageDraw.Draw(preenchimento), ImageDraw.Draw(contorno)
        for x0, y0, x1, y1 in cards:
            caixa = [x0 * ss, y0 * ss, x1 * ss - 1, y1 * ss - 1]
            fdraw.rounded_rectangle(caixa, radius=RADIUS_LG * ss, fill=255)
            cdraw.rounded_rectangle(caixa, radius=RADIUS_LG * ss, outline=255, width=ss)
        tamanho = (width, height)
        preenchimento = preenchimento.resize(tamanho, Image.LANCZOS)
        contorno = contorno.resize(tamanho, Image.LANCZOS)
        img = Image.composite(Image.new("RGB", tamanho, rgb(BG_PANEL)), img, preenchimento)
        img = Image.composite(Image.new("RGB", tamanho, rgb(EDGE_PANEL)), img, contorno)
    return img


# --------------------------------------------------------- widgets -------

class Divider(tk.Frame):
    """Separador de 1px, quase invisivel contra o cartao."""

    def __init__(self, master, bg=None):
        super().__init__(master, height=1, bg=EDGE, highlightthickness=0, bd=0)
