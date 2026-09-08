"""
Pele visual do bot: MMORPG dos anos 2000.

Por que existe um modulo so pra isso:
    O gui.py cuida do que a tela FAZ (cadastrar conta, iniciar, mostrar
    log). Este arquivo cuida de como ela PARECE. Separado, da pra mexer no
    visual inteiro sem arriscar a logica -- e da pra voltar atras trocando
    um import.

De onde vem a paleta:
    As cores nao foram inventadas: foram amostradas de prints da interface
    do proprio Talisman Online (painel "Sistema Mestre/Discipulo", lista de
    amigos, janela de ajuda). As constantes marcadas com "#" abaixo sao os
    valores lidos direto do print; as outras foram derivadas delas.

O vocabulario visual daquela epoca, resumido:
    - Canto reto. Nada de border-radius -- isso e linguagem de 2015 pra ca.
    - Borda de 1px em DOIS tons: clara em cima/esquerda, escura embaixo/
      direita (ou o contrario, pra parecer afundado). E so isso que cria a
      sensacao de relevo, sem nenhuma sombra.
    - Gradiente vertical nos botoes, sempre mais claro em cima.
    - Ciano como cor de acento, dourado pro que e importante.
    - Texto pequeno em Tahoma -- era A fonte de interface de jogo no
      Windows XP, e e o que o olho reconhece como "daquela epoca".

Como os gradientes sao feitos:
    Desenhando linha por linha num tk.Canvas. Sem Pillow e sem nenhuma
    imagem em disco -- entao nada disso engorda o .exe, e nenhuma arte do
    jogo precisa viajar junto com o programa.
"""

import tkinter as tk

# ----------------------------------------------------------- paleta ------

# Fundos -- quase preto, com um leve desvio pro roxo. O preto puro (#000)
# nunca aparece na interface do jogo; ela sempre tem essa "sujeira".
BG_APP = "#141319"          # fundo geral da janela
BG_PANEL = "#17161c"        # # fundo dos paineis
BG_SIDEBAR = "#121116"      # barra lateral, um tom abaixo pra separar
BG_SUNKEN = "#0d0c11"       # dentro dos campos e do log (parece afundado)
BG_ROW_HOVER = "#1d1c24"
BG_ROW_SEL = "#16232e"      # linha selecionada: puxa pro azul do acento

# Azul do "chrome" (barra de titulo, molduras)
CHROME_TOP = "#244065"      # # topo do gradiente da barra de titulo
CHROME_BOT = "#141d30"      # base do mesmo gradiente
CHROME_EDGE = "#356a9e"     # # borda azul clara que contorna tudo

# Botoes -- gradiente vertical, mais claro em cima
BTN_TOP = "#3a72a8"         # # (lido #32699f, clareado um tico)
BTN_BOT = "#0d304e"         # #
BTN_EDGE_LIGHT = "#5b9bd0"
BTN_EDGE_DARK = "#08192b"
BTN_TEXT = "#d6ecf8"

# Botao de acao principal -- dourado. Nas caixas de dialogo do jogo, o
# botao que confirma e dourado; o azul e pra acao comum.
GOLD_TOP = "#e8c25a"
GOLD_BOT = "#8a6212"
GOLD_EDGE_LIGHT = "#f5dc9a"
GOLD_EDGE_DARK = "#4d360a"
GOLD_TEXT = "#2a1e05"

# Acentos
CYAN = "#11cdd6"            # # aba ativa / conta rodando
CYAN_DIM = "#1d6184"        # # trilho da barra de rolagem
CYAN_SOFT = "#82b9ce"       # # setas da barra de rolagem
GOLD = "#d4a017"            # # rotulo de campo
YELLOW = "#ffff02"          # # cabecalho de coluna
DANGER = "#e04a4a"          # erro no log / acao destrutiva
WARNING = "#ffd24a"         # aviso no log

# Texto
TEXT = "#dfe6ea"
TEXT_SOFT = "#9fb4c2"
TEXT_MUTED = "#6c7f8c"
TEXT_DIM = "#47555f"
TEXT_DISABLED = "#3d4750"

# Bordas
EDGE_LIGHT = "#3a4d5c"      # aresta iluminada (cima/esquerda)
EDGE_DARK = "#0a0a0e"       # aresta na sombra (baixo/direita)
EDGE_PANEL = "#2f3d46"      # # contorno externo dos paineis

FONT = "Tahoma"             # a fonte de interface de jogo do Windows XP
FONT_MONO = "Consolas"


# ------------------------------------------------------ util de cor ------

def _rgb(hexa):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4))


def mix(color_a, color_b, t):
    """Cor intermediaria entre duas, com t de 0.0 a 1.0."""
    a, b = _rgb(color_a), _rgb(color_b)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _vgradient(canvas, x0, y0, x1, y1, top, bottom, tag):
    """Gradiente vertical desenhado linha por linha. Um botao de 30px sao
    30 linhas -- barato o suficiente pra redesenhar a cada hover."""
    altura = max(1, y1 - y0)
    for i in range(altura):
        canvas.create_line(
            x0, y0 + i, x1, y0 + i,
            fill=mix(top, bottom, i / max(1, altura - 1)), tags=tag,
        )


def tracked(texto):
    """Espacamento entre letras. O Tk nao tem essa propriedade, entao
    intercalamos um espaco fino (U+2009). Usado nos titulos -- letras
    espacadas em maiuscula sao marca registrada das interfaces da epoca."""
    return " ".join(texto)


# --------------------------------------------------------- widgets -------

class GameButton(tk.Canvas):
    """Botao no estilo da epoca: gradiente vertical, borda de dois tons e o
    texto descendo 1px quando pressionado.

    E um Canvas, e nao um CTkButton, porque gradiente e bevel simplesmente
    nao existem no CustomTkinter -- ele so faz preenchimento chapado com
    canto arredondado, que e exatamente o oposto do que queremos aqui.

    Aceita as mesmas chamadas que o gui.py ja fazia num CTkButton
    (`.configure(state=...)`, `.pack()`, `.grid()`), pra troca sair
    transparente do lado de la."""

    VARIANTS = {
        # nome:    (topo, base, borda clara, borda escura, cor do texto)
        "primary": (GOLD_TOP, GOLD_BOT, GOLD_EDGE_LIGHT, GOLD_EDGE_DARK, GOLD_TEXT),
        "normal":  (BTN_TOP, BTN_BOT, BTN_EDGE_LIGHT, BTN_EDGE_DARK, BTN_TEXT),
        "danger":  ("#b04a4a", "#4a1414", "#d47878", "#280a0a", "#ffdede"),
        "link":    (None, None, None, None, TEXT_SOFT),
    }

    def __init__(self, master, text="", command=None, variant="normal",
                 width=120, height=30, font_size=11, bold=False, bg=None):
        super().__init__(
            master, width=width, height=height,
            highlightthickness=0, bd=0, takefocus=0,
            bg=bg or BG_PANEL, cursor="hand2",
        )
        self._text = text
        self._command = command
        self._variant = variant if variant in self.VARIANTS else "normal"
        self._font = (FONT, font_size, "bold" if bold else "normal")
        self._state = "normal"
        self._hover = False
        self._pressed = False

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -- api que o gui.py usa --------------------------------------------

    def configure(self, **kw):
        """Intercepta `state` e `text` (que num Canvas significariam outra
        coisa) e repassa o resto -- width/height/bg -- pro Canvas."""
        redesenhar = False
        if "state" in kw:
            self._state = kw.pop("state")
            self._sync_cursor()
            redesenhar = True
        if "text" in kw:
            self._text = kw.pop("text")
            redesenhar = True
        if "command" in kw:
            self._command = kw.pop("command")
        if kw:
            super().configure(**kw)
        if redesenhar:
            self._redraw()

    config = configure

    def _sync_cursor(self):
        try:
            super().configure(cursor="" if self._state == "disabled" else "hand2")
        except tk.TclError:
            pass

    # -- eventos ----------------------------------------------------------

    def _on_enter(self, _e=None):
        self._hover = True
        self._redraw()

    def _on_leave(self, _e=None):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _e=None):
        if self._state == "disabled":
            return
        self._pressed = True
        self._redraw()

    def _on_release(self, _e=None):
        estava_pressionado = self._pressed
        self._pressed = False
        self._redraw()
        if estava_pressionado and self._state != "disabled" and self._command:
            self._command()

    # -- desenho ----------------------------------------------------------

    def _redraw(self):
        self.delete("all")
        largura = self.winfo_width() or int(self["width"])
        altura = self.winfo_height() or int(self["height"])
        if largura <= 1 or altura <= 1:
            return

        topo, base, luz, sombra, cor_texto = self.VARIANTS[self._variant]
        desativado = self._state == "disabled"

        if self._variant == "link":
            self._draw_link(largura, altura, desativado)
            return

        if desativado:
            # Cinza dessaturado: a mesma forma, sem nenhuma vida.
            topo, base = "#2a2e33", "#16181b"
            luz, sombra = "#3a4046", "#0a0b0d"
            cor_texto = TEXT_DISABLED
        elif self._hover:
            topo = mix(topo, "#ffffff", 0.18)
            base = mix(base, "#ffffff", 0.12)

        if self._pressed and not desativado:
            topo, base = base, topo      # gradiente invertido = afundado
            luz, sombra = sombra, luz

        _vgradient(self, 0, 0, largura, altura, topo, base, "bg")

        # Bevel: linha clara em cima/esquerda, escura embaixo/direita.
        self.create_line(0, 0, largura, 0, fill=luz)
        self.create_line(0, 0, 0, altura, fill=luz)
        self.create_line(0, altura - 1, largura, altura - 1, fill=sombra)
        self.create_line(largura - 1, 0, largura - 1, altura, fill=sombra)

        deslocamento = 1 if self._pressed and not desativado else 0
        self.create_text(
            largura // 2 + deslocamento, altura // 2 + deslocamento,
            text=self._text, fill=cor_texto, font=self._font,
        )

    def _draw_link(self, largura, altura, desativado):
        """Variante 'link': so texto, sem caixa. Pro que e acao terciaria
        ('limpar', 'parar todas') e nao merece peso de botao."""
        cor = TEXT_DIM if desativado else (CYAN if self._hover else TEXT_MUTED)
        self.create_text(largura // 2, altura // 2, text=self._text, fill=cor,
                         font=self._font)
        if self._hover and not desativado:
            meia = len(self._text) * self._font[1] * 0.28
            y = altura // 2 + self._font[1]
            self.create_line(largura // 2 - meia, y, largura // 2 + meia, y, fill=CYAN)


class TitleStrip(tk.Canvas):
    """A barra de titulo do jogo: gradiente azul, contorno claro e o nome
    em ciano com as letras espacadas. E o elemento que mais entrega o
    estilo -- e o primeiro que a pessoa ve ao abrir."""

    def __init__(self, master, text, height=34, subtitle=""):
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=CHROME_BOT, takefocus=0)
        self._text = text
        self._subtitle = subtitle
        self._h = height
        self.bind("<Configure>", lambda _e: self._redraw())

    def _redraw(self):
        self.delete("all")
        largura = self.winfo_width()
        altura = self._h
        if largura <= 1:
            return
        _vgradient(self, 0, 0, largura, altura, CHROME_TOP, CHROME_BOT, "bg")
        self.create_line(0, 0, largura, 0, fill=CHROME_EDGE)
        self.create_line(0, altura - 1, largura, altura - 1, fill=EDGE_DARK)
        self.create_text(16, altura // 2, anchor="w", text=tracked(self._text),
                         fill=CYAN, font=(FONT, 11, "bold"))
        if self._subtitle:
            self.create_text(largura - 16, altura // 2, anchor="e",
                             text=self._subtitle, fill=TEXT_MUTED, font=(FONT, 9))

    def set_subtitle(self, texto):
        self._subtitle = texto
        self._redraw()


class Divider(tk.Frame):
    """Separador de 2px em dois tons -- a versao 2000s de um <hr>. Uma
    linha escura com uma clara logo abaixo passa a impressao de um sulco
    cavado no painel."""

    def __init__(self, master, bg=BG_PANEL):
        super().__init__(master, height=2, bg=bg)
        tk.Frame(self, height=1, bg=EDGE_DARK).pack(fill="x")
        tk.Frame(self, height=1, bg=EDGE_LIGHT).pack(fill="x")


class SunkenBox(tk.Frame):
    """Moldura que parece AFUNDADA na tela -- borda escura em cima/esquerda
    e clara embaixo/direita, o inverso do botao. E o que envolve listas,
    campos e o log na interface do jogo.

    O conteudo vai dentro de `.body`, nao dentro do proprio widget."""

    def __init__(self, master, bg=BG_SUNKEN, outer=BG_PANEL):
        super().__init__(master, bg=EDGE_DARK, bd=0, highlightthickness=0)
        meio = tk.Frame(self, bg=EDGE_LIGHT, bd=0, highlightthickness=0)
        meio.pack(fill="both", expand=True, padx=(1, 0), pady=(1, 0))
        self.body = tk.Frame(meio, bg=bg, bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=(0, 1), pady=(0, 1))


class RaisedBox(tk.Frame):
    """O oposto do SunkenBox: parece SALTAR da tela. Usado nos paineis que
    agrupam conteudo (a moldura externa da janela, os blocos de secao)."""

    def __init__(self, master, bg=BG_PANEL):
        super().__init__(master, bg=EDGE_LIGHT, bd=0, highlightthickness=0)
        meio = tk.Frame(self, bg=EDGE_DARK, bd=0, highlightthickness=0)
        meio.pack(fill="both", expand=True, padx=(1, 0), pady=(1, 0))
        self.body = tk.Frame(meio, bg=bg, bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=(0, 1), pady=(0, 1))
