"""
Componentes do design system da Apple (Human Interface Guidelines),
desenhados num tk.Canvas com transparencia de verdade.

Por que um canvas e nao widgets prontos:
    Widgets (Tk/CustomTkinter) tem fundo SOLIDO -- nao da pra ter vidro
    translucido com eles. Aqui tudo e desenhado num canvas so: o fundo
    (arte desfocada + paineis de vidro) e uma imagem, e cada componente
    (cartao, botao, chip, toggle...) e uma imagem RGBA com transparencia por
    cima dela -- o Tk mistura o canal alfa direito, entao o fundo aparece
    atraves do vidro. Textos sao itens de texto do proprio canvas, desenhados
    direto sobre o vidro.

    O que precisa de digitacao (campos de texto, registro) continua sendo
    widget do Tk, encaixado no canvas -- com a cor de fundo calculada a partir
    do pixel do fundo bem onde ele fica, pra emenda nao aparecer.

Componentes (nomes do HIG):
    - Button: estilos "white" (capsula branca, o "Play" do Apple TV),
      "blue" (filled, systemBlue), "gray" (filled cinza translucido) e
      "plain" (so texto).
    - SegmentedControl, Toggle (switch), Badge, TextField, PopUpButton,
      cartoes de lista (sidebar list) e menus.

Interacao:
    Em vez de prender eventos item a item, o Kit guarda "areas clicaveis"
    (hotspots) em ordem de desenho e resolve hover/clique/duplo
    clique/botao direito pela area de cima -- assim um toggle dentro de um
    cartao recebe o clique dele, e o cartao o resto.
"""

import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

import skin

SS = 3  # supersampling pros cantos arredondados (o ImageDraw nao faz antisserrilhado)


# ---------------------------------------------------------- imagens -----

def _rgba(cor, alpha=1.0):
    r, g, b = skin.rgb(cor) if isinstance(cor, str) else cor[:3]
    return (r, g, b, int(round(255 * alpha)))


def rounded(w, h, r, fill=None, outline=None, outline_w=1.0, rim=None):
    """Retangulo arredondado RGBA (w x h), com:
      fill     -- cor de preenchimento (r,g,b,a)
      outline  -- contorno de cor solida (r,g,b,a), largura outline_w
      rim      -- borda de luz do vidro: (alfa_no_alto, alfa_embaixo) de
                  branco, sumindo de cima pra baixo (o "Liquid Glass")."""
    w, h = max(1, int(w)), max(1, int(h))
    r = max(0, min(r, w // 2, h // 2))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def mascara(inset=0.0, largura=None):
        m = Image.new("L", (w * SS, h * SS), 0)
        d = ImageDraw.Draw(m)
        caixa = [inset * SS, inset * SS, w * SS - 1 - inset * SS, h * SS - 1 - inset * SS]
        if largura:
            d.rounded_rectangle(caixa, radius=r * SS, outline=255, width=max(1, int(largura * SS)))
        else:
            d.rounded_rectangle(caixa, radius=r * SS, fill=255)
        return m.resize((w, h), Image.LANCZOS)

    if fill is not None and fill[3] > 0:
        camada = Image.new("RGBA", (w, h), fill)
        img = Image.composite(camada, img, mascara())
    if outline is not None and outline[3] > 0:
        m = np.asarray(mascara(largura=outline_w), dtype=np.float32) / 255.0
        camada = np.zeros((h, w, 4), dtype=np.float32)
        camada[..., :3] = outline[:3]
        camada[..., 3] = m * outline[3]
        img = Image.alpha_composite(img, Image.fromarray(camada.astype(np.uint8), "RGBA"))
    if rim is not None:
        topo, base = rim
        m = np.asarray(mascara(largura=1.2), dtype=np.float32) / 255.0
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        alfa = (topo + (base - topo) * np.sqrt(t)) * m * 255
        camada = np.zeros((h, w, 4), dtype=np.float32)
        camada[..., :3] = 255
        camada[..., 3] = alfa
        img = Image.alpha_composite(img, Image.fromarray(camada.clip(0, 255).astype(np.uint8), "RGBA"))
    return img


def circle(d, fill, shadow=False):
    """Circulo RGBA de diametro d (o "botao" do toggle), com sombra leve."""
    m = 4 if shadow else 0
    tam = d + 2 * m
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    if shadow:
        s = Image.new("L", (tam * SS, tam * SS), 0)
        ImageDraw.Draw(s).ellipse([m * SS, (m + 1) * SS, (m + d) * SS, (m + d + 1) * SS], fill=90)
        s = s.resize((tam, tam), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.5))
        img = Image.composite(Image.new("RGBA", (tam, tam), (0, 0, 0, 255)), img, s)
        img.putalpha(s)
    c = Image.new("L", (tam * SS, tam * SS), 0)
    ImageDraw.Draw(c).ellipse([m * SS, m * SS, (m + d) * SS - 1, (m + d) * SS - 1], fill=255)
    c = c.resize((tam, tam), Image.LANCZOS)
    return Image.composite(Image.new("RGBA", (tam, tam), fill), img, c)


# ------------------------------------------------------------- fundo ----

_imagem_fundo = None


def _carregar_imagem_fundo():
    """A imagem de fundo (skin.BACKGROUND_IMAGE), carregada uma vez so. None
    se o arquivo nao existir -- ai o fundo cai pra arte gerada."""
    global _imagem_fundo
    if _imagem_fundo is None:
        try:
            from paths import RESOURCE_DIR

            caminho = RESOURCE_DIR / skin.BACKGROUND_IMAGE
            _imagem_fundo = Image.open(caminho).convert("RGB") if caminho.exists() else False
        except Exception:  # noqa: BLE001
            _imagem_fundo = False
    return _imagem_fundo or None


def _cobrir(img, width, height):
    """Redimensiona `img` pra COBRIR width x height (sem distorcer), cortando
    o que sobrar dos lados -- como um papel de parede "preencher"."""
    escala = max(width / img.width, height / img.height)
    w, h = max(width, round(img.width * escala)), max(height, round(img.height * escala))
    img = img.resize((w, h), Image.LANCZOS)
    x, y = (w - width) // 2, (h - height) // 2
    return img.crop((x, y, x + width, y + height))


def _arte_gerada(width, height):
    escala = 6
    cor = skin._arte(width, height, escala)
    pequeno = Image.fromarray(cor.clip(0, 255).astype(np.uint8), "RGB")
    arte = pequeno.resize((width, height), Image.BICUBIC)
    ruido = np.random.default_rng(7).normal(0, 1.2, (height, width, 1))
    return Image.fromarray((np.asarray(arte, dtype=np.float32) + ruido).clip(0, 255).astype(np.uint8))


def render_background(width, height, panels, radius):
    """Fundo da janela inteira: a imagem de fundo (ou a arte gerada, se a
    imagem faltar) com os paineis de VIDRO de verdade -- o fundo aparece
    atraves deles, desfocado, com uma tinta escura por cima, borda de luz e
    sombra. Retorna uma imagem RGB."""
    foto = _carregar_imagem_fundo()
    arte = _cobrir(foto, width, height) if foto is not None else _arte_gerada(width, height)
    img = arte.convert("RGBA")

    # Sombra suave de todos os paineis (eles "flutuam" sobre a arte).
    sombra = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(sombra)
    for x0, y0, x1, y1 in panels:
        o = skin.GLASS_SHADOW_OFFSET
        d.rounded_rectangle([x0 + 4, y0 + o, x1 - 4, y1 + o], radius=radius, fill=255)
    sombra = sombra.filter(ImageFilter.GaussianBlur(skin.GLASS_SHADOW_BLUR))
    sombra = sombra.point(lambda a: int(a * skin.GLASS_SHADOW_ALPHA))
    img = Image.composite(Image.new("RGBA", (width, height), (0, 0, 0, 255)), img, sombra)

    # O vidro: a arte de tras, desfocada mais um pouco, com a tinta do
    # material por cima -- e um leve reflexo branco.
    desfocada = arte.filter(ImageFilter.GaussianBlur(skin.GLASS_BLUR)).convert("RGBA")
    for x0, y0, x1, y1 in panels:
        w, h = x1 - x0, y1 - y0
        pedaco = desfocada.crop((x0, y0, x1, y1))
        tinta = Image.new("RGBA", (w, h), _rgba(skin.GLASS_MATERIAL, skin.GLASS_ALPHA))
        pedaco = Image.alpha_composite(pedaco, tinta)
        brilho = Image.new("RGBA", (w, h), (255, 255, 255, int(255 * skin.GLASS_WHITE)))
        pedaco = Image.alpha_composite(pedaco, brilho)
        mascara = rounded(w, h, radius, fill=(255, 255, 255, 255)).split()[3]
        img.paste(pedaco, (x0, y0), mascara)
        img.alpha_composite(rounded(w, h, radius, rim=(skin.GLASS_RIM_TOP, skin.GLASS_RIM_BOTTOM)), (x0, y0))
    return img.convert("RGB")


# --------------------------------------------------------------- Kit ----

class Hot:
    """Area clicavel registrada no Kit."""

    def __init__(self, rect, on_click=None, on_double=None, on_right=None, on_hover=None,
                 cursor="hand2", enabled=True):
        self.rect = rect
        self.on_click = on_click
        self.on_double = on_double
        self.on_right = on_right
        self.on_hover = on_hover
        self.cursor = cursor
        self.enabled = enabled

    def contains(self, x, y):
        x0, y0, x1, y1 = self.rect
        return x0 <= x < x1 and y0 <= y < y1


class Kit:
    """Desenha os componentes num canvas e cuida da interacao.

    Tudo que e desenhado leva a tag "fg"; `clear()` apaga e o App desenha de
    novo quando o estado muda. O fundo (tag "bg") e os widgets encaixados
    (tag "embed") ficam de fora."""

    def __init__(self, canvas):
        self.c = canvas
        try:
            self.S = max(1.0, canvas.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self.S = 1.0
        self._fonts = {}
        self._photos = {}
        self.hot = []
        self._hover = None
        self._pressed = None
        self.bg = None  # np.array RGB do fundo atual (pra amostrar cores)
        canvas.bind("<Motion>", self._on_motion, add="+")
        canvas.bind("<Leave>", lambda _e: self._set_hover(None), add="+")
        canvas.bind("<ButtonPress-1>", self._on_press, add="+")
        canvas.bind("<ButtonRelease-1>", self._on_release, add="+")
        canvas.bind("<Double-Button-1>", self._on_double, add="+")
        canvas.bind("<Button-3>", self._on_right, add="+")

    # -- medidas / fontes / imagens --

    def s(self, v):
        """Converte medida de design (px a 100%) pra pixels de tela."""
        return int(round(v * self.S))

    def font(self, size, weight="normal", family=None):
        chave = (size, weight, family)
        if chave not in self._fonts:
            self._fonts[chave] = tkfont.Font(
                family=family or skin.FONT, size=-self.s(size), weight=weight
            )
        return self._fonts[chave]

    def text_width(self, text, size, weight="normal", family=None):
        return self.font(size, weight, family).measure(text)

    def photo(self, chave, gerar):
        """PhotoImage em cache (precisa ficar guardada, senao o Tk apaga)."""
        foto = self._photos.get(chave)
        if foto is None:
            foto = ImageTk.PhotoImage(gerar())
            self._photos[chave] = foto
            if len(self._photos) > 600:  # nao deixa crescer pra sempre
                for k in list(self._photos)[:200]:
                    self._photos.pop(k, None)
        return foto

    def sample(self, x, y):
        """Cor do fundo (hex) no ponto (x, y) -- pra widgets encaixados e
        linhas ficarem da cor exata do vidro onde estao."""
        if self.bg is None:
            return skin.BG_PANEL
        h, w = self.bg.shape[:2]
        x, y = max(0, min(w - 1, int(x))), max(0, min(h - 1, int(y)))
        return skin._hex(self.bg[y, x])

    # -- ciclo de desenho --

    def clear(self):
        self.c.delete("fg")
        self.hot = []
        self._hover = None
        self._pressed = None
        self.c.configure(cursor="")

    def add_hot(self, rect, **kw):
        h = Hot(rect, **kw)
        self.hot.append(h)
        return h

    # -- interacao --

    def _achar(self, x, y):
        for h in reversed(self.hot):
            if h.enabled and h.contains(x, y):
                return h
        return None

    def _set_hover(self, h):
        if h is self._hover:
            return
        antigo, self._hover = self._hover, h
        if antigo is not None and antigo.on_hover:
            antigo.on_hover(False)
        if h is not None and h.on_hover:
            h.on_hover(True)
        self.c.configure(cursor=(h.cursor if h is not None else ""))

    def _on_motion(self, e):
        self._set_hover(self._achar(e.x, e.y))

    def _on_press(self, e):
        self._pressed = self._achar(e.x, e.y)
        if self._pressed is None:
            self.c.focus_set()  # clique no vazio tira o foco dos campos

    def _on_release(self, e):
        h = self._achar(e.x, e.y)
        if h is not None and h is self._pressed and h.on_click:
            h.on_click()
        self._pressed = None

    def _on_double(self, e):
        h = self._achar(e.x, e.y)
        if h is not None and h.on_double:
            h.on_double()

    def _on_right(self, e):
        h = self._achar(e.x, e.y)
        if h is not None and h.on_right:
            h.on_right(e)

    # ------------------------------------------------------- componentes --

    def text(self, x, y, text, size=13, weight="normal", color=None, anchor="nw",
             family=None, width=None, tag="fg"):
        kw = {"width": width} if width else {}
        return self.c.create_text(
            x, y, text=text, fill=color or skin.TEXT, anchor=anchor,
            font=self.font(size, weight, family), tags=(tag,), **kw
        )

    def image(self, x, y, foto, anchor="nw", tag="fg"):
        return self.c.create_image(x, y, image=foto, anchor=anchor, tags=(tag,))

    def divider(self, x0, x1, y):
        cor = skin.mix(self.sample((x0 + x1) / 2, y), "#ffffff", 0.12)
        self.c.create_line(x0, y, x1, y, fill=cor, tags=("fg",))

    # Botao (HIG: Button). Estilos: white, blue, gray, plain.
    _BTN = {
        "white": {"fill": ("#f5f5f7", 1.0), "hover": ("#ffffff", 1.0), "text": "#000000"},
        "blue": {"fill": (skin.SYSTEM_BLUE, 1.0), "hover": ("#2a96ff", 1.0), "text": "#ffffff"},
        "gray": {"fill": ("#ffffff", 0.13), "hover": ("#ffffff", 0.20), "text": "#ffffff"},
    }

    def button(self, x, y, w, h, label, command, style="white", enabled=True, size=13, radius=None):
        s = self.s
        r = radius if radius is not None else h // 2
        if style == "plain":
            cor = skin.SYSTEM_BLUE if enabled else skin.TEXT_DIM
            tid = self.text(x + w / 2, y + h / 2, label, size, "normal", cor, anchor="center")

            def hover(dentro):
                if enabled:
                    self.c.itemconfigure(tid, fill="#5eb1ff" if dentro else cor)

            self.add_hot((x, y, x + w, y + h), on_click=command if enabled else None,
                         on_hover=hover, cursor="hand2" if enabled else "", enabled=enabled)
            return
        est = self._BTN[style]
        alpha_fator = 1.0 if enabled else 0.35

        def gerar(chave):
            cor, a = est[chave]
            rim = (0.35, 0.05) if style == "gray" else None
            return rounded(w, h, r, fill=_rgba(cor, a * alpha_fator), rim=rim)

        normal = self.photo(("btn", style, w, h, r, enabled, "n"), lambda: gerar("fill"))
        hover_ = self.photo(("btn", style, w, h, r, enabled, "h"), lambda: gerar("hover"))
        iid = self.image(x, y, normal)
        cor_texto = est["text"] if enabled else (skin.TEXT_DIM if style != "white" else "#6e6e73")
        self.text(x + w / 2, y + h / 2, label, size, "bold", cor_texto, anchor="center")

        def on_hover(dentro):
            if enabled:
                self.c.itemconfigure(iid, image=hover_ if dentro else normal)

        self.add_hot((x, y, x + w, y + h), on_click=command if enabled else None,
                     on_hover=on_hover, cursor="hand2" if enabled else "", enabled=True)
        _ = s

    # Controle segmentado (HIG: Segmented control).
    def segmented(self, x, y, values, selected, command, size=13):
        s = self.s
        pad, h = s(16), s(32)
        larguras = [self.text_width(v, size, "bold") + 2 * pad for v in values]
        total = sum(larguras) + s(4) * 2
        trilho = self.photo(("seg_track", total, h), lambda: rounded(
            total, h, h // 2, fill=(0, 0, 0, 70), rim=(0.18, 0.04)))
        self.image(x, y, trilho)
        cx = x + s(4)
        for v, lw in zip(values, larguras):
            ativo = v == selected
            ih = h - s(8)
            if ativo:
                foto = self.photo(("seg_sel", lw, ih), lambda lw=lw, ih=ih: rounded(
                    lw, ih, ih // 2, fill=(255, 255, 255, 58), rim=(0.40, 0.10)))
                self.image(cx, y + s(4), foto)
            tid = self.text(cx + lw / 2, y + h / 2, v, size, "bold",
                            "#ffffff" if ativo else skin.TEXT_MUTED, anchor="center")

            def hover(dentro, tid=tid, ativo=ativo):
                if not ativo:
                    self.c.itemconfigure(tid, fill="#ffffff" if dentro else skin.TEXT_MUTED)

            self.add_hot((cx, y, cx + lw, y + h), on_click=(lambda v=v: command(v)),
                         on_hover=hover, cursor="hand2")
            cx += lw
        return total, h

    # Interruptor (HIG: Toggle / switch).
    def toggle(self, x, y, on, command, enabled=True):
        s = self.s
        w, h = s(42), s(25)
        fundo = self.photo(("tog", w, h, on, enabled), lambda: rounded(
            w, h, h // 2,
            fill=_rgba(skin.SYSTEM_GREEN, 1.0 if enabled else 0.4) if on else (255, 255, 255, 46),
        ))
        self.image(x, y, fundo)
        d = h - s(4)
        bola = self.photo(("tog_knob", d), lambda: circle(d, (255, 255, 255, 255), shadow=True))
        m = 4  # margem da sombra (ver circle)
        kx = x + (w - d - s(2) if on else s(2)) - m
        self.image(kx, y + s(2) - m, bola)
        self.add_hot((x - s(4), y - s(4), x + w + s(4), y + h + s(4)),
                     on_click=command if enabled else None, cursor="hand2" if enabled else "")
        return w, h

    # Etiqueta de estado (HIG: badge / "pill").
    def badge(self, right, y, text, fill, color, dot=None, size=11, on_dark=None):
        """Desenha a etiqueta alinhada pela DIREITA em `right`. Retorna a largura."""
        s = self.s
        h = s(22)
        tw = self.text_width(text, size, "bold")
        dot_w = s(14) if dot else 0
        w = tw + dot_w + s(20)
        x = right - w
        foto = self.photo(("badge", w, h, fill), lambda: rounded(w, h, h // 2, fill=fill))
        self.image(x, y, foto)
        tx = x + s(10)
        if dot:
            r = s(3)
            cy = y + h / 2
            self.c.create_oval(tx, cy - r, tx + 2 * r, cy + r, fill=dot, outline="", tags=("fg",))
            tx += dot_w
        self.text(tx, y + h / 2, text, size, "bold", color, anchor="w")
        return w

    # Campo de texto (HIG: Text field). O widget de verdade (tk.Entry) e
    # encaixado pelo App; aqui so o desenho e a cor que ele deve usar.
    def field(self, x, y, w, h, focused=False):
        s = self.s
        base = self.sample(x + w / 2, y + h / 2)
        cor = skin.mix(base, "#000000", 0.38)
        borda = (10, 132, 255, 210) if focused else (255, 255, 255, 30)
        foto = self.photo(("field", w, h, cor, focused), lambda: rounded(
            w, h, s(10), fill=_rgba(cor), outline=borda, outline_w=2.0 if focused else 1.0))
        self.image(x, y, foto)
        return cor

    # Botao de menu (HIG: Pop-up button).
    def popup(self, x, y, w, h, text, on_click, size=13, placeholder=False):
        s = self.s
        normal = self.photo(("popup", w, h, "n"), lambda: rounded(
            w, h, s(10), fill=(255, 255, 255, 26), rim=(0.25, 0.05)))
        hover_ = self.photo(("popup", w, h, "h"), lambda: rounded(
            w, h, s(10), fill=(255, 255, 255, 40), rim=(0.32, 0.06)))
        iid = self.image(x, y, normal)
        self.text(x + s(12), y + h / 2, text, size, "normal",
                  skin.TEXT_MUTED if placeholder else skin.TEXT, anchor="w")
        self.chevron(x + w - s(16), y + h / 2)
        self.add_hot((x, y, x + w, y + h), on_click=on_click,
                     on_hover=lambda d: self.c.itemconfigure(iid, image=hover_ if d else normal))

    def chevron(self, cx, cy, color=None):
        """Setinha pra baixo do pop-up (desenhada com linhas -- o simbolo
        da fonte sai torto no Windows)."""
        s = self.s
        a = s(4)
        self.c.create_line(cx - a, cy - a / 2, cx, cy + a / 2, cx + a, cy - a / 2,
                           fill=color or skin.TEXT_MUTED, width=max(1.5, s(1.8)),
                           capstyle="round", joinstyle="round", tags=("fg",))

    def menu(self, items, x_root, y_root, checked=None):
        """Menu (HIG: Menu). items = [(rotulo, funcao) | None (separador)];
        funcao None = titulo de secao (cinza, nao clicavel)."""
        m = tk.Menu(
            self.c, tearoff=0, bg="#2c2c2e", fg="#f5f5f7", activebackground=skin.SYSTEM_BLUE,
            activeforeground="#ffffff", disabledforeground=skin.SYSTEM_GRAY, bd=0, relief="flat",
            font=self.font(12),
        )
        for item in items:
            if item is None:
                m.add_separator()
                continue
            rotulo, funcao = item
            if funcao is None:
                m.add_command(label=rotulo, state="disabled")
                continue
            prefixo = "✓  " if checked is not None and rotulo == checked else "     "
            m.add_command(label=prefixo + rotulo if checked is not None else rotulo, command=funcao)
        try:
            m.tk_popup(int(x_root), int(y_root))
        finally:
            m.grab_release()

    # Cartao de vidro (HIG: lista da barra lateral). Estados: normal, hover,
    # selected (foco: mais claro e com contorno branco) e active (rodando).
    def card_photos(self, w, h, active=False, selected=False):
        s = self.s
        r = s(14)
        if active:
            base = dict(fill=_rgba("#0a64e0", 0.92), rim=(0.45, 0.12))
            hov = dict(fill=_rgba("#1a72ea", 0.95), rim=(0.5, 0.14))
        else:
            base = dict(fill=(255, 255, 255, 38 if selected else 16), rim=(0.22, 0.04))
            hov = dict(fill=(255, 255, 255, 48 if selected else 27), rim=(0.28, 0.06))
        if selected:
            for d in (base, hov):
                d["outline"] = (255, 255, 255, 245)
                d["outline_w"] = 2.0
        n = self.photo(("card", w, h, active, selected, "n"), lambda: rounded(w, h, r, **base))
        hv = self.photo(("card", w, h, active, selected, "h"), lambda: rounded(w, h, r, **hov))
        return n, hv
