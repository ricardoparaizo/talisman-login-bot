"""
Pele visual do bot: vidro fosco (frosted glass) escuro e roxo.

Por que existe um modulo so pra isso:
    O gui.py cuida do que a tela FAZ (cadastrar conta, iniciar, mostrar
    log). Este arquivo cuida de como ela PARECE. Separado, da pra mexer no
    visual inteiro sem arriscar a logica -- e da pra voltar atras trocando
    um import.

O vocabulario visual deste tema:
    - Fundo quase preto com um leve desvio pro roxo, como se a janela
      flutuasse sobre um brilho roxo desfocado atras dela.
    - Cantos arredondados nos elementos "cartao" (caixas, botoes, campos) --
      o oposto da skin retro anterior, que era toda de canto reto e bisel.
      Paineis estruturais grandes (barra lateral, area principal) continuam
      retos, encostados na borda da janela.
    - Um unico acento roxo/violeta pra tudo que precisa chamar atencao
      (botao principal, campo em foco, conta rodando) -- sem misturar
      varias cores de destaque.
    - Sem gradiente/bisel desenhado a mao: os widgets do CustomTkinter ja
      fazem preenchimento chapado com canto arredondado nativamente, que e
      exatamente o visual que queremos agora.
    - O desfoque de verdade nao vem de nenhuma API do Windows -- foram
      tentadas tres (pywinstyles "acrylic"/"mica" e DwmEnableBlurBehindWindow
      direto) e nenhuma mostrou efeito visivel nessa maquina, ou pior,
      estragou a paleta (ver App._apply_frosted_backdrop no gui.py pro
      relato completo). Em vez disso, a barra lateral e a area principal
      "flutuam" como cartoes solidos sobre uma imagem borrada de verdade
      (captura de tela + Pillow), visivel so no respiro ao redor delas.
"""

import tkinter as tk

# ----------------------------------------------------------- paleta ------

# Fundos -- quase preto, com um leve desvio pro roxo.
BG_APP = "#151020"          # fundo geral da janela
BG_PANEL = "#1d1729"        # paineis / superficie "vidro"
BG_SIDEBAR = "#130f1c"      # barra lateral, um tom abaixo pra separar
BG_SUNKEN = "#100c18"       # dentro dos campos e do log
BG_ROW_HOVER = "#251f36"
BG_ROW_SEL = "#2c2344"      # linha selecionada: puxa pro roxo do acento

# Acento roxo/violeta -- a unica cor de destaque do tema.
ACCENT = "#6d4fd1"
ACCENT_BRIGHT = "#8a70e8"   # hover / texto de destaque (labels, titulos)
ACCENT_DIM = "#3d3160"      # fundo de botao/menu ativo, trilho de rolagem
ACCENT_SOFT = "#5c48a0"     # bordas de elementos em estado "ligado"

# Botao secundario -- neutro, quase invisivel contra o painel, so o
# contorno sutil entrega que e clicavel.
BTN_BG = "#251f38"
BTN_HOVER = "#332a4d"

# Acentos de status
DANGER = "#e5677c"          # erro no log
WARNING = "#f0b45c"         # aviso no log

# Texto
TEXT = "#ece7f5"
TEXT_SOFT = "#b6adc9"
TEXT_MUTED = "#867d97"
TEXT_DIM = "#584f6b"
TEXT_DISABLED = "#413a4f"

# Bordas -- bem sutis, quase somem contra o fundo (e o proprio efeito
# "vidro": nada de moldura forte, so uma linha quase imperceptivel).
EDGE = "#2c2438"
EDGE_STRONG = "#3c3350"     # campos e caixas que precisam se destacar um pouco mais
EDGE_PANEL = EDGE

# Barra de rolagem
SCROLLBAR_IDLE = "#2a2340"
SCROLLBAR_HOVER = ACCENT_DIM

# Cantos arredondados -- os valores padrao usados nos widgets "cartao"
# (caixas, botoes, campos). Paineis estruturais grandes ficam com 0.
RADIUS_SM = 8
RADIUS_MD = 10
RADIUS_LG = 14

FONT = "Segoe UI"            # fonte de interface padrao do Windows moderno
FONT_MONO = "Consolas"


# ------------------------------------------------------ util de cor ------

def rgb(hexa):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


def tracked(texto):
    """Espacamento entre letras. O Tk nao tem essa propriedade, entao
    intercalamos um espaco fino (U+2009). Usado nos rotulos em maiuscula
    (titulo, secoes) -- da o ar "discreto" tipico de UI moderna."""
    return " ".join(texto)


# --------------------------------------------------------- widgets -------

class Divider(tk.Frame):
    """Separador de 1px -- a versao "vidro" de um <hr>, quase invisivel
    contra o fundo (de proposito: nada de linha forte nesse tema)."""

    def __init__(self, master, bg=None):
        super().__init__(master, height=1, bg=EDGE, highlightthickness=0, bd=0)
