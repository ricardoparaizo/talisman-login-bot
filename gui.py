"""
Interface grafica do bot, feita com CustomTkinter (biblioteca pura em
Python, MIT, sem dependencias pesadas -- so um wrapper sobre o Tkinter que
ja vem com o Python, entao continua simples/baixo risco pro antivirus).

Visual: cartoes roxo-escuros flutuando sobre um gradiente roxo
suave, com roxo/violeta como unico destaque e botoes em pilula. As cores
vivem no skin.py; aqui ficam so o layout e o comportamento.

Sobre o fundo: CustomTkinter desenha tudo opaco, entao nao da pra ter
transparencia/desfoque de verdade (as APIs do Windows pra isso --
pywinstyles "acrylic"/"mica", DwmEnableBlurBehindWindow -- ja foram
tentadas e nao funcionaram). O gradiente fica numa imagem gerada pelo Pillow
(skin.canvas_image), atras de tudo, e aparece no respiro em volta dos dois
cartoes. Ela e redesenhada quando a janela muda de tamanho.

Layout em barra lateral + painel de detalhes:

    - Barra lateral (esquerda): nome do app no topo e a lista de contas
      cadastradas, cada uma num cartaozinho, com uma
      caixinha de selecao por conta (pra multi-login) e duplo clique na
      linha pra iniciar so aquela conta na hora. Editar uma conta ja
      cadastrada so acontece pelo botao direito -> "Editar".
    - Painel de detalhes (direita): formulario unico da conta -- login,
      senha, servidor, nick e a pasta onde o jogo esta instalado. Fica
      sempre pronto pra cadastrar uma conta nova; so muda pra mostrar os
      dados de uma conta existente quando voce entra no modo edicao.
    - Log: por baixo de tudo, com cores por nivel (erro/aviso/info).

Rodar "python bot.py" (ou dar duplo clique no .exe) sem nenhum argumento
abre esta tela.
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import bot
import profiles
import skin
from paths import RESOURCE_DIR, USER_DATA_DIR

APP_NAME = "Bot Login - Talisman Online"
APP_VERSION = "v1.0"
APP_AUTHOR = "TheSimitarBeast"
APP_URL = "https://github.com/ricardoparaizo/talisman-login-bot"

NEW_ACCOUNT_HINT = (
    "Preencha os campos abaixo para adicionar uma conta ao bot. Seus dados ficam salvos apenas "
    "localmente na pasta Documentos do seu computador."
)

# Os icones viajam dentro do .exe (RESOURCE_DIR); rodando pelo codigo,
# RESOURCE_DIR e a propria pasta do projeto, entao serve pros dois casos.
ICON_ICO = RESOURCE_DIR / "icon.ico"
ICON_PNG = RESOURCE_DIR / "icon.png"

KNOWN_SERVERS = [
    "White Horse [NEW]",
    "Tiger Fish (WW)",
    "Sky Ice (GSM&BI)",
    "All Stars",
    "Light in the Darkness",
]

# ---------------------------------------------------------------- paleta ----
# As cores vivem no skin.py. Os apelidos abaixo existem pra o resto deste
# arquivo continuar lendo do mesmo jeito de antes -- so o que eles APONTAM
# mudou.
BG = skin.BG_APP           # fundo do conteudo
BG_SIDEBAR = skin.BG_SIDEBAR
SURFACE = skin.BG_PANEL    # painel do log
SURFACE_ALT = skin.BG_SUNKEN   # campos de texto (afundados)
SURFACE_HOVER = skin.BG_ROW_HOVER
ROW_HOVER = skin.BG_ROW_HOVER
ROW_SELECTED = skin.BG_ROW_SEL
BORDER = skin.EDGE
BORDER_STRONG = skin.EDGE_STRONG
BORDER_FOCUS = skin.ACCENT_BRIGHT   # campo em foco ganha o roxo de destaque

WHITE = skin.TEXT
TEXT = skin.TEXT
TEXT_SECOND = skin.TEXT_SOFT
TEXT_MUTED = skin.TEXT_MUTED
TEXT_DIM = skin.TEXT_DIM

DOT_IDLE = skin.TEXT_DIM   # bolinha "parado"
DOT_RUNNING = skin.OK      # bolinha "rodando"

DANGER = skin.DANGER       # acao destrutiva + erro no log
WARNING = skin.WARNING     # aviso no log
LABEL = skin.TEXT_MUTED    # rotulos de campo e titulos de secao

FONT_FAMILY = skin.FONT
FONT_MONO_FAMILY = skin.FONT_MONO


# Espaco em volta dos dois cartoes (MARGEM) e entre eles (VAO) -- e por
# onde o gradiente do fundo aparece, entao nao da pra ser muito apertado.
MARGEM = 34
VAO = 28


def _font(size, weight="normal", family=FONT_FAMILY, slant="roman", underline=False):
    return ctk.CTkFont(family=family, size=size, weight=weight, slant=slant, underline=underline)


def _tracked(text):
    """Espacamento entre letras -- ver skin.tracked()."""
    return skin.tracked(text)


class QueueLogHandler(logging.Handler):
    """Manda cada linha de log pra uma Queue, pra thread da interface poder
    ler e mostrar na tela sem travar (Tkinter/CTk so pode ser tocado pela
    thread principal)."""

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put((record.levelname, self.format(record)))


# --------------------------------------------------------------- botoes ----
# Tres pesos, sempre os mesmos, pra a tela ter hierarquia em vez de uma
# fileira de botoes todos gritando igual. `bg`/`hover_bg`/`color` continuam
# aceitos por compatibilidade com quem chama (a versao anterior, em Canvas,
# precisava saber o fundo ao redor pra nao deixar um retangulo destoando) --
# o CTkButton nao precisa mais disso, entao esses parametros sao ignorados.


def primary_button(master, text, command, width=120, bg=None):
    """Acao principal: pilula branca com texto escuro. So uma por area da
    tela -- num tema escuro, branco e o que mais chama atencao."""
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=36,
        corner_radius=skin.RADIUS_PILL, fg_color=skin.BTN_PRIMARY,
        hover_color=skin.BTN_PRIMARY_HOVER, text_color=skin.BTN_PRIMARY_TEXT,
        font=_font(12, "bold"), border_width=0,
    )


def ghost_button(master, text, command, width=120, height=36, bg=None):
    """Acao secundaria: pilula escura com contorno sutil."""
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height,
        corner_radius=skin.RADIUS_PILL, fg_color=skin.BTN_BG,
        hover_color=skin.BTN_HOVER, text_color=TEXT,
        border_width=1, border_color=BORDER_STRONG, font=_font(11),
    )


def text_button(master, text, command, width=90, height=24, color=None, hover_bg=None, bg=None):
    """Acao terciaria: so texto, com um leve realce em pilula no hover."""
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height,
        corner_radius=skin.RADIUS_PILL, fg_color="transparent",
        hover_color=skin.BG_ROW_HOVER, text_color=color or TEXT_MUTED,
        font=_font(10), border_width=0,
    )


def hairline(master, color=None, bg=None):
    """Separador em dois tons -- ver skin.Divider."""
    return skin.Divider(master, bg=bg or SURFACE)


def load_app_image(size):
    """Carrega o icone do app pra mostrar DENTRO da janela, no tamanho
    pedido. Se o arquivo nao estiver do lado do programa (ou o Pillow
    faltar), retorna None -- a interface continua funcionando sem a
    imagem, so sem o simbolo."""
    try:
        from PIL import Image

        if not ICON_PNG.exists():
            return None
        img = Image.open(ICON_PNG)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    except Exception:  # noqa: BLE001 - detalhe visual, nunca deve impedir o app de abrir
        return None


class AccountRow(ctk.CTkFrame):
    """Uma linha da lista de contas, na barra lateral: barra indicadora de
    selecao + caixinha (multi-login) + nome/servidor/personagem + bolinha
    de status. Duplo clique inicia so aquela conta na hora; botao direito
    abre o menu (editar/remover/iniciar-parar). Um clique simples na linha
    nao faz nada de proposito -- editar uma conta so acontece pelo menu de
    botao direito.

    Nao existe conceito de "conta ativa" aqui: quem decide quais contas
    logam e o usuario, marcando a caixinha (ou Iniciar todas) de cada vez --
    de proposito, pra nao ter uma conta "padrao" implicita rodando sem voce
    escolher."""

    def __init__(self, master, app, account, server, character, is_running):
        super().__init__(
            master, fg_color=skin.BG_CARD, corner_radius=skin.RADIUS_MD,
            border_width=1, border_color=skin.EDGE,
        )
        self.app = app
        self.account = account
        self.selected = False
        self.hovered = False
        # Conta rodando vira o "cartao roxo" -- o destaque da tela. A linha
        # e recriada a cada mudanca de estado (_refresh_profile_list), entao
        # basta decidir isso aqui.
        self.running = is_running
        self.grid_columnconfigure(2, weight=1)

        # A caixinha e o liga/desliga da conta: marcar JA inicia o login,
        # desmarcar para. Ela nasce refletindo o estado real (marcada se a
        # conta ja estiver rodando).
        #
        # Cuidado: o `command` do CTkCheckBox so dispara em clique de
        # verdade (toggle) -- marcar por codigo com set()/select() nao
        # chama nada. E por isso que da pra sincronizar a caixinha com o
        # estado real sem entrar em loop de "marcou -> inicia -> marcou".
        self.check_var = tk.BooleanVar(value=is_running)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.check_var,
            command=self._on_toggle,
            width=18,
            checkbox_width=15,
            checkbox_height=15,
            corner_radius=4,
            border_width=1,
            # no cartao roxo (rodando), a caixinha marcada fica branca --
            # roxo sobre roxo sumiria
            fg_color=skin.BTN_PRIMARY if is_running else skin.ACCENT,
            hover_color=skin.BTN_PRIMARY_HOVER if is_running else skin.ACCENT_BRIGHT,
            checkmark_color=skin.CARD_ACTIVE if is_running else skin.TEXT,
            border_color=skin.TEXT_SOFT if is_running else skin.ACCENT_SOFT,
        )
        self.checkbox.grid(row=0, column=1, rowspan=2, padx=(14, 10), pady=10)

        self.name_label = ctk.CTkLabel(
            self, text=account, font=_font(13, "bold"), text_color=TEXT, anchor="w", height=20
        )
        self.name_label.grid(row=0, column=2, sticky="we", padx=(0, 8), pady=(10, 0))

        subtitle = " · ".join(part for part in (server, character) if part) or "sem servidor/personagem"
        self.subtitle_label = ctk.CTkLabel(
            self, text=subtitle, font=_font(10), text_color=TEXT_MUTED, anchor="w", height=16
        )
        self.subtitle_label.grid(row=1, column=2, columnspan=2, sticky="we", padx=(0, 12), pady=(0, 10))

        # Pilula de status ("● rodando" / "● parado"), como o "Analyzing"
        # dos cards da referencia: bolinha colorida + texto discreto, no
        # canto de cima -- assim o subtitulo embaixo tem a largura toda.
        self.status_pill = ctk.CTkFrame(self, corner_radius=skin.RADIUS_PILL, height=22)
        self.status_pill.grid(row=0, column=3, sticky="e", padx=(0, 10), pady=(9, 0))
        self.status_dot = ctk.CTkLabel(
            self.status_pill, text="●", font=_font(9), width=8, height=20,
            text_color=DOT_RUNNING if is_running else DOT_IDLE,
        )
        self.status_dot.pack(side="left", padx=(9, 4))
        self.status_text = ctk.CTkLabel(
            self.status_pill, text="rodando" if is_running else "parado",
            font=_font(10), height=20, text_color=TEXT if is_running else TEXT_MUTED,
        )
        self.status_text.pack(side="left", padx=(0, 10))

        # Sem clique simples aqui de proposito: a UNICA forma de abrir uma
        # conta pra edicao e o botao direito -> "Editar" (ver
        # App._show_row_menu / App._start_edit). Um clique simples na linha
        # nao deve mudar o formulario.
        for widget in (
            self, self.name_label, self.subtitle_label,
            self.status_pill, self.status_dot, self.status_text,
        ):
            widget.bind("<Double-Button-1>", self._on_double_click)
            widget.bind("<Button-3>", self._on_right_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

        self._apply_style()

    def _on_toggle(self):
        self.app._on_account_toggled(self.account, bool(self.check_var.get()))

    def _on_right_click(self, event):
        self.app._show_row_menu(self.account, event)

    def _on_double_click(self, _event=None):
        self.app._quick_start_account(self.account)

    def _on_enter(self, _event=None):
        self.hovered = True
        self._apply_style()

    def _on_leave(self, _event=None):
        self.hovered = False
        self._apply_style()

    def set_selected(self, selected):
        """A linha aberta no formulario ganha um fundo um pouco mais claro
        e um contorno mais visivel."""
        self.selected = selected
        self._apply_style()

    def _apply_style(self):
        if self.running:
            fundo = skin.CARD_ACTIVE_HOVER if self.hovered else skin.CARD_ACTIVE
            borda = skin.CARD_ACTIVE_EDGE
            pilula = skin.PILL_ON_ACTIVE
            subtitulo = skin.TEXT_SOFT
        else:
            if self.selected:
                fundo, borda = skin.BG_ROW_SEL, skin.EDGE_STRONG
            elif self.hovered:
                fundo, borda = skin.BG_ROW_HOVER, skin.EDGE_STRONG
            else:
                fundo, borda = skin.BG_CARD, skin.EDGE
            pilula = skin.PILL_BG
            subtitulo = TEXT_MUTED
        # O CTkFrame repassa a cor nova pros filhos "transparent" sozinho.
        self.configure(fg_color=fundo, border_color=borda)
        self.status_pill.configure(fg_color=pilula)
        self.subtitle_label.configure(text_color=subtitulo)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title(APP_NAME)
        self.geometry("1160x760")
        self.minsize(980, 640)
        self.configure(fg_color=BG)
        self._set_window_icon()

        # Fundo em gradiente: ocupa a janela inteira, por baixo de tudo (por
        # isso e criado antes de qualquer outro widget). So aparece de
        # verdade no respiro ao redor da barra lateral/area principal --
        # ver _paint_canvas.
        self._backdrop_label = tk.Label(self, bd=0, highlightthickness=0, bg=BG)
        self._backdrop_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._canvas_size = None
        self._canvas_job = None

        self.log_queue = queue.Queue()
        # contas que terminaram; preenchida pelas threads dos bots e
        # esvaziada pela thread da interface (veja _bot_thread_target)
        self.finished_queue = queue.Queue()
        # Uma conta por entrada: {"thread": Thread, "stop_event": Event}.
        # Permite rodar VARIAS contas ao mesmo tempo, cada uma na sua propria
        # thread/janela do jogo (bot.py cuida de travar cada uma na sua
        # copia do client.exe).
        self.running = {}
        self.account_rows = {}       # account -> AccountRow
        # conta carregada no formulario pra edicao (e destacada na lista).
        # None = formulario esta no modo padrao "adicionar conta". So muda
        # quando o usuario entra no modo edicao explicitamente (botao
        # direito -> Editar).
        self.editing_account = None

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main_area()
        self._attach_log_handler()
        self._refresh_profile_list()
        self._load_launcher_path()
        self._poll_log_queue()
        self._try_dark_titlebar()
        self.bind("<Configure>", self._on_window_configure, add="+")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self):
        """Icone da janela (barra de titulo, Alt+Tab e barra de tarefas).
        No Windows o .ico e o formato certo; em outros sistemas caimos pro
        .png via iconphoto. Se nada der certo, segue sem icone -- e so
        aparencia, nao pode impedir o app de abrir."""
        try:
            if ICON_ICO.exists():
                self.iconbitmap(default=str(ICON_ICO))
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            if ICON_PNG.exists():
                self._icon_photo = tk.PhotoImage(file=str(ICON_PNG))
                self.iconphoto(True, self._icon_photo)
        except Exception:  # noqa: BLE001
            pass

    def _try_dark_titlebar(self):
        """Tenta deixar a barra de titulo da janela escura tambem (Windows
        10/11). Se nao der, so ignora -- e um detalhe visual, nao afeta o
        funcionamento."""
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
            )
            # Windows 11: pinta a barra de titulo com a mesma cor do fundo,
            # pra ela "sumir" e a janela parecer uma peca so. No Windows 10
            # isso nao existe e a chamada so falha em silencio.
            DWMWA_CAPTION_COLOR = 35
            cor = ctypes.c_int(skin.colorref(skin.BG_APP))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(cor), ctypes.sizeof(cor)
            )
        except Exception:  # noqa: BLE001 - so um detalhe visual, nunca deve travar a UI
            pass

    def _on_window_configure(self, event):
        # <Configure> chega de todo widget filho tambem; so interessa a
        # janela. Espera o redimensionamento "assentar" antes de redesenhar
        # -- gerar a imagem a cada pixel arrastado travaria a tela.
        if event.widget is not self:
            return
        if self._canvas_job is not None:
            self.after_cancel(self._canvas_job)
        self._canvas_job = self.after(120, self._paint_canvas)

    def _paint_canvas(self):
        """Desenha o gradiente do fundo (skin.canvas_image) no tamanho atual da
        janela. Se falhar (Pillow faltando, etc.), fica so a cor solida --
        e detalhe visual, nunca pode travar o app."""
        self._canvas_job = None
        try:
            from PIL import ImageTk

            self.update_idletasks()
            tamanho = (self.winfo_width(), self.winfo_height())
            if tamanho == self._canvas_size or min(tamanho) <= 1:
                return
            # O cartao arredondado de cada painel, um pouco maior que a area
            # de conteudo (que e reta) -- ver skin.canvas_image.
            I = skin.CARD_INSET
            cartoes = [
                (w.winfo_x() - I, w.winfo_y() - I,
                 w.winfo_x() + w.winfo_width() + I, w.winfo_y() + w.winfo_height() + I)
                for w in (self._sidebar_card, self._main_card)
            ]
            img = skin.canvas_image(*tamanho, cards=cartoes)
            if img is None:
                return
            # a referencia precisa ser guardada num atributo -- sem isso o
            # Python coleta o PhotoImage e a imagem some da tela sozinha.
            self._backdrop_photo = ImageTk.PhotoImage(img)
            self._backdrop_label.configure(image=self._backdrop_photo)
            self._canvas_size = tamanho
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------ barra lateral

    def _build_sidebar(self):
        # Respiro em volta -- e o que deixa o gradiente do fundo (backdrop_label)
        # visivel, dando o ar de "cartao flutuando".
        I = skin.CARD_INSET
        sidebar = ctk.CTkFrame(
            self, width=292, fg_color=BG_SIDEBAR, bg_color=BG_SIDEBAR, corner_radius=0,
        )
        # Area de CONTEUDO do cartao, reta e encaixada pra dentro: o cartao
        # arredondado em si e desenhado no fundo (ver _paint_canvas).
        sidebar.grid(row=1, column=0, sticky="ns", padx=(MARGEM + I, VAO // 2 + I), pady=MARGEM + I)
        self._sidebar_card = sidebar
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(3, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        # -- cabecalho: icone + nome do app, credito discreto embaixo --
        header = ctk.CTkFrame(sidebar, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=14, pady=(14, 0))
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(anchor="w", fill="x")

        logo = load_app_image(32)
        if logo is not None:
            ctk.CTkLabel(title_row, text="", image=logo).pack(side="left", padx=(0, 12))

        title_text = ctk.CTkFrame(title_row, fg_color="transparent")
        title_text.pack(side="left")
        ctk.CTkLabel(
            title_text, text="Talisman Online", font=_font(15, "bold"), text_color=TEXT,
            anchor="w", height=20,
        ).pack(anchor="w")
        by_row = ctk.CTkFrame(title_text, fg_color="transparent")
        by_row.pack(anchor="w")
        ctk.CTkLabel(by_row, text="Bot Login · by ", font=_font(10), text_color=TEXT_MUTED,
                     height=16).pack(side="left")

        # O nome do autor leva pro repositorio do projeto. Fica sublinhado
        # so no hover, pra nao virar mais um elemento gritando na tela.
        self.author_link = ctk.CTkLabel(
            by_row, text=APP_AUTHOR, font=_font(10), text_color=TEXT_SECOND, cursor="hand2",
            height=16,
        )
        self.author_link.pack(side="left")
        self.author_link.bind("<Button-1>", lambda _e: self._open_project_page())
        self.author_link.bind(
            "<Enter>",
            lambda _e: self.author_link.configure(font=_font(10, underline=True), text_color=WHITE),
        )
        self.author_link.bind(
            "<Leave>",
            lambda _e: self.author_link.configure(font=_font(10), text_color=TEXT_SECOND),
        )

        ctk.CTkLabel(by_row, text=f"  ·  {APP_VERSION}", font=_font(10), text_color=TEXT_MUTED,
                     height=16).pack(side="left")

        hairline(sidebar, bg=BG_SIDEBAR).grid(row=1, column=0, sticky="we", padx=14, pady=(20, 0))

        # -- titulo da secao, contagem em pilula + acao secundaria --
        section = ctk.CTkFrame(sidebar, fg_color="transparent")
        section.grid(row=2, column=0, sticky="we", padx=14, pady=(16, 8))
        section.grid_columnconfigure(2, weight=1)
        self.section_label = ctk.CTkLabel(
            section, text="Contas", font=_font(12, "bold"), text_color=TEXT, anchor="w"
        )
        self.section_label.grid(row=0, column=0, sticky="w")
        self.count_label = ctk.CTkLabel(
            section, text="", font=_font(10), text_color=TEXT_SECOND, fg_color=skin.PILL_BG,
            corner_radius=skin.RADIUS_PILL, height=20, width=26,
        )
        self.count_label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.btn_stop = text_button(section, "parar todas", self._stop_bot, width=76, height=22,
                                    bg=BG_SIDEBAR)
        self.btn_stop.configure(state="disabled")
        self.btn_stop.grid(row=0, column=3, sticky="e")

        # -- lista de contas (scrollable) --
        # Sem caixa em volta: cada conta ja e um cartaozinho, e a lista
        # "flutua" direto no cartao da barra lateral.
        self.account_list_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
            # bem discreta: o CTk nao esconde a barra sozinho quando a lista
            # cabe inteira, entao ela fica quase invisivel parada e so
            # aparece de verdade quando voce passa o mouse/rola.
            scrollbar_button_color=skin.BG_SIDEBAR,
            scrollbar_button_hover_color=skin.SCROLLBAR_HOVER,
        )
        self.account_list_frame.grid(row=3, column=0, sticky="nswe", padx=(6, 0), pady=(0, 8))
        self.account_list_frame.grid_columnconfigure(0, weight=1)

        # -- rodape da barra lateral --
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="we", padx=14, pady=(6, 14))
        self.btn_start = primary_button(footer, "Iniciar todas", self._start_all, width=256,
                                        bg=BG_SIDEBAR)
        self.btn_start.configure(height=40)
        self.btn_start.pack(fill="x")
        ghost_button(footer, "+  Nova conta", self._clear_form, width=256, height=38,
                     bg=BG_SIDEBAR).pack(fill="x", pady=(10, 0))

    # ---------------------------------------------------------- main area

    def _build_main_area(self):
        I = skin.CARD_INSET
        main = ctk.CTkFrame(
            self, fg_color=SURFACE, bg_color=SURFACE, corner_radius=0,
        )
        main.grid(row=1, column=1, sticky="nswe", padx=(VAO // 2 + I, MARGEM + I), pady=MARGEM + I)
        self._main_card = main
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=0)
        main.grid_rowconfigure(4, weight=1)

        self._build_page_header(main)
        self._build_detail_panel(main)
        self._build_log_panel(main)

    def _build_page_header(self, master):
        header = ctk.CTkFrame(master, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=24, pady=(20, 0))
        self.page_title = ctk.CTkLabel(
            header, text="Adicione uma conta", font=_font(20, "bold"), text_color=TEXT, anchor="w"
        )
        self.page_title.pack(anchor="w")
        self.page_sub = ctk.CTkLabel(
            header,
            text=NEW_ACCOUNT_HINT,
            font=_font(11),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self.page_sub.pack(anchor="w", pady=(3, 0))
        # A quebra de linha acompanha a largura do cartao (com um valor fixo
        # o texto era cortado a direita quando o cartao ficava mais estreito).
        # O CTk multiplica o wraplength pela escala do Windows, entao a
        # largura em pixels reais e dividida por ela antes.
        header.bind(
            "<Configure>",
            lambda e: self.page_sub.configure(
                wraplength=max(200, int(e.width / self.page_sub._get_widget_scaling()))
            ),
        )

    def _build_detail_panel(self, master):
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=1, column=0, sticky="we", padx=24, pady=(22, 0))
        wrapper.grid_columnconfigure(0, weight=1)
        self._build_form(wrapper)

    def _update_page_header(self):
        """O cabecalho da direita mostra o contexto atual: a conta em edicao,
        ou 'Adicione uma conta' quando o formulario esta no modo padrao
        (nenhuma conta em edicao)."""
        if not self.editing_account:
            self.page_title.configure(text="Adicione uma conta")
            self.page_sub.configure(text=NEW_ACCOUNT_HINT)
            return

        data = profiles.load_profiles()
        profile = next(
            (p for p in profiles.list_profiles(data) if p.get("account") == self.editing_account), None
        )
        server = (profile or {}).get("server_name", "")
        character = (profile or {}).get("character_name", "")
        self.page_title.configure(text=self.editing_account)
        self.page_sub.configure(
            text=" · ".join(part for part in (server, character) if part) or "sem servidor/personagem definidos"
        )

    def _make_entry(self, master, placeholder="", show=None):
        entry = ctk.CTkEntry(
            master,
            placeholder_text=placeholder,
            placeholder_text_color=TEXT_DIM,
            show=show,
            fg_color=SURFACE_ALT,
            border_color=BORDER_STRONG,
            border_width=1,
            text_color=TEXT,
            font=_font(12),
            corner_radius=skin.RADIUS_MD,
            height=38,
        )
        # anel de foco -- feedback de qual campo esta ativo, sem cor nenhuma
        entry.bind("<FocusIn>", lambda _e: entry.configure(border_color=BORDER_FOCUS))
        entry.bind("<FocusOut>", lambda _e: entry.configure(border_color=BORDER_STRONG))
        return entry

    def _field_label(self, master, text):
        return ctk.CTkLabel(master, text=text, font=_font(11), text_color=LABEL, anchor="w")

    def _build_form(self, tab):
        """Formulario unico da conta: login/senha, servidor/nick e a pasta
        do jogo. Sem abas -- tudo cabe numa tela so."""
        tab.grid_columnconfigure((0, 1), weight=1, uniform="cols")

        self._field_label(tab, "Conta").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.entry_account = self._make_entry(tab, "Login")
        self.entry_account.grid(row=1, column=0, sticky="we", padx=(0, 9))

        self._field_label(tab, "Senha").grid(row=0, column=1, sticky="w", padx=(9, 0), pady=(0, 5))
        self.entry_password = self._make_entry(tab, "Senha da conta", show="*")
        self.entry_password.grid(row=1, column=1, sticky="we", padx=(9, 0))

        self._field_label(tab, "Servidor").grid(row=2, column=0, sticky="w", pady=(16, 5))
        self.combo_server = ctk.CTkComboBox(
            tab,
            values=KNOWN_SERVERS,
            fg_color=SURFACE_ALT,
            border_color=BORDER_STRONG,
            border_width=1,
            button_color=skin.BTN_BG,
            button_hover_color=skin.BTN_HOVER,
            dropdown_fg_color=skin.BG_CARD,
            dropdown_hover_color=skin.ACCENT_DIM,
            dropdown_text_color=TEXT,
            dropdown_font=_font(11),
            text_color=TEXT,
            font=_font(12),
            corner_radius=skin.RADIUS_MD,
            height=38,
        )
        self.combo_server.set("")
        self.combo_server.grid(row=3, column=0, sticky="we", padx=(0, 9))

        self._field_label(tab, "Nick").grid(row=2, column=1, sticky="w", padx=(9, 0), pady=(16, 5))
        self.entry_character = self._make_entry(tab, "")
        self.entry_character.grid(row=3, column=1, sticky="we", padx=(9, 0))

        # ---- pasta do jogo ----
        # Vale pra todas as contas (e uma instalacao so do jogo), mas fica
        # aqui no formulario pra nao precisar de uma aba so pra isso.
        self._field_label(tab, "Pasta do jogo").grid(row=4, column=0, sticky="w", pady=(16, 5))
        pasta_row = ctk.CTkFrame(tab, fg_color="transparent")
        pasta_row.grid(row=5, column=0, columnspan=2, sticky="we")
        pasta_row.grid_columnconfigure(0, weight=1)
        self.entry_launcher_path = self._make_entry(
            pasta_row, "onde o jogo esta instalado (a pasta que tem o game.exe)"
        )
        self.entry_launcher_path.grid(row=0, column=0, sticky="we", padx=(0, 8))
        ghost_button(pasta_row, "Procurar", self._browse_launcher_path, width=100,
                     bg=BG).grid(row=0, column=1)

        hairline(tab, bg=BG).grid(row=7, column=0, columnspan=2, sticky="we", pady=(24, 0))

        buttons = ctk.CTkFrame(tab, fg_color="transparent")
        buttons.grid(row=8, column=0, columnspan=2, sticky="we", pady=(16, 4))
        primary_button(buttons, "Salvar conta", self._save_profile, width=118,
                       bg=BG).pack(side="left")

    def _open_project_page(self):
        """Abre o repositorio do projeto no navegador."""
        try:
            import webbrowser

            webbrowser.open(APP_URL)
        except Exception:  # noqa: BLE001
            messagebox.showinfo("Projeto", APP_URL)

    def _open_data_folder(self):
        """Abre no Explorer a pasta onde as contas ficam salvas (Documentos)
        -- pra voce poder ver com os proprios olhos o perfis.json e o que
        tem dentro dele."""
        try:
            import os
            import subprocess
            import sys

            path = str(USER_DATA_DIR)
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo(
                "Pasta das contas", f"Suas contas ficam em:\n\n{USER_DATA_DIR}\n\n({exc})"
            )

    def _build_log_panel(self, master):
        hairline(master, bg=BG).grid(row=3, column=0, sticky="we", padx=24, pady=(28, 0))

        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=4, column=0, sticky="nswe", padx=24, pady=(20, 16))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(wrapper, fg_color="transparent")
        head.grid(row=0, column=0, sticky="we", pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="Registro", font=_font(12, "bold"), text_color=TEXT, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        text_button(head, "limpar", self._clear_log, width=60, height=22,
                    bg=BG).grid(row=0, column=1, sticky="e")

        self.log_text = ctk.CTkTextbox(
            wrapper,
            fg_color=skin.BG_SUNKEN,
            border_color=skin.EDGE_PANEL,
            border_width=1,
            text_color=TEXT_SECOND,
            corner_radius=skin.RADIUS_LG - 6,
            font=_font(11, family=FONT_MONO_FAMILY),
            wrap="word",
            activate_scrollbars=True,
            scrollbar_button_color=skin.SCROLLBAR_IDLE,
            scrollbar_button_hover_color=skin.SCROLLBAR_HOVER,
        )
        self.log_text.grid(row=1, column=0, sticky="nswe")
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("error", foreground=DANGER)
        self.log_text.tag_config("warning", foreground=WARNING)
        self.log_text.tag_config("info", foreground=TEXT_SECOND)

    def _attach_log_handler(self):
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        bot.log.addHandler(handler)
        bot.log.setLevel(logging.INFO)

    # -------------------------------------------------------- perfis (CRUD)

    def _refresh_profile_list(self):
        for row in self.account_list_frame.winfo_children():
            row.destroy()
        self.account_rows = {}

        data = profiles.load_profiles()
        accounts = profiles.list_profiles(data)

        if accounts:
            self.count_label.configure(text=str(len(accounts)))
            self.count_label.grid()
        else:
            self.count_label.grid_remove()

        if not accounts:
            # criada na hora (e destruida junto com as linhas no proximo
            # refresh) -- assim nao existe widget fixo aqui pra ficar com
            # referencia pendurada depois de destruido.
            ctk.CTkLabel(
                self.account_list_frame,
                text="Nenhuma conta cadastrada.\nClique em '+ Nova conta' pra comecar.",
                font=_font(10),
                text_color=TEXT_DIM,
                justify="left",
                anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=14)
        else:
            for idx, p in enumerate(accounts):
                account = p.get("account", "")
                row = AccountRow(
                    self.account_list_frame,
                    self,
                    account,
                    p.get("server_name", ""),
                    p.get("character_name", ""),
                    is_running=(account in self.running),
                )
                row.grid(row=idx, column=0, sticky="we", pady=(0, 8))
                row.set_selected(account == self.editing_account)
                self.account_rows[account] = row

        self._update_running_state()

    def _show_row_menu(self, account, event):
        """Menu do botao direito em cima de uma conta: editar e remover.
        Essas acoes nao tem botao fixo na tela de proposito -- sao raras
        perto de 'iniciar', e sujariam o formulario.

        Importante: "Editar" (chamando _start_edit) e o UNICO caminho que
        carrega os dados de uma conta no formulario -- clicar na linha
        (simples ou duplo) nunca abre uma conta pra edicao."""
        rodando = account in self.running

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=skin.BG_CARD,
            fg=skin.TEXT_SOFT,
            activebackground=skin.ACCENT_DIM,
            activeforeground=skin.TEXT,
            bd=0,
            relief="flat",
            font=(FONT_FAMILY, 9),
        )
        menu.add_command(
            label="Parar" if rodando else "Iniciar",
            command=lambda: self._on_account_toggled(account, not rodando),
        )
        menu.add_separator()
        menu.add_command(label="Editar", command=lambda: self._start_edit(account))
        menu.add_separator()
        menu.add_command(label="Remover", command=lambda: self._remove_profile(account))
        menu.add_separator()
        menu.add_command(label="Abrir a pasta das minhas contas", command=self._open_data_folder)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_account_toggled(self, account, checked):
        """Chamado quando o usuario clica na caixinha de uma conta. Marcar
        inicia o login dessa conta na hora; desmarcar para ela."""
        if checked:
            if account in self.running:
                return
            data = profiles.load_profiles()
            profile = next(
                (p for p in profiles.list_profiles(data) if p.get("account") == account), None
            )
            if not profile:
                return
            self._start_accounts([profile], confirm_multi=False)
        else:
            info = self.running.get(account)
            if info:
                info["stop_event"].set()
                self._log_direct(f"Parando '{account}'...")

    def _start_all(self):
        """Marca todas as contas e inicia todas de uma vez."""
        data = profiles.load_profiles()
        all_profiles = profiles.list_profiles(data)
        if not all_profiles:
            messagebox.showinfo(
                "Nenhuma conta", "Cadastre pelo menos uma conta antes de iniciar."
            )
            return
        for row in self.account_rows.values():
            row.check_var.set(True)
        self._start_accounts(all_profiles, confirm_multi=False)

    def _selected_for_start(self):
        return [acc for acc, row in self.account_rows.items() if row.check_var.get()]

    def _start_edit(self, account):
        """Entra no modo edicao pra essa conta: carrega os dados dela no
        formulario e destaca a linha correspondente na lista. Esse e o
        UNICO caminho que preenche o formulario com uma conta ja
        cadastrada -- so chamado pelo item 'Editar' do menu de botao
        direito da linha (App._show_row_menu). Clicar na linha (simples ou
        duplo) nunca chama isso."""
        data = profiles.load_profiles()
        profile = next((p for p in profiles.list_profiles(data) if p.get("account") == account), None)
        if not profile:
            return

        self.editing_account = account
        for acc, row in self.account_rows.items():
            row.set_selected(acc == account)

        server = profile.get("server_name", "")
        character = profile.get("character_name", "")
        self._update_page_header()

        self.entry_account.delete(0, "end")
        self.entry_account.insert(0, profile.get("account", ""))
        self.entry_password.delete(0, "end")  # nunca mostramos a senha salva
        self.combo_server.set(server)
        self.entry_character.delete(0, "end")
        self.entry_character.insert(0, character)

    def _clear_form(self):
        """Volta o painel direito pro modo padrao: pronto pra cadastrar uma
        conta nova. Sai do modo edicao (se estiver nele)."""
        self.editing_account = None
        for row in self.account_rows.values():
            row.set_selected(False)
        self._update_page_header()
        self.entry_account.delete(0, "end")
        self.entry_password.delete(0, "end")
        self.combo_server.set("")
        self.entry_character.delete(0, "end")
        self.entry_account.focus_set()

    def _save_profile(self):
        account = self.entry_account.get().strip()
        server_name = self.combo_server.get().strip()
        character_name = self.entry_character.get().strip()
        password = self.entry_password.get()

        if not account:
            messagebox.showwarning("Falta a conta", "Preencha o campo 'Conta' antes de salvar.")
            return

        data = profiles.load_profiles()
        data = profiles.upsert_profile(data, account, server_name, character_name)
        profiles.save_profiles(data)

        if password:
            profiles.set_password(account, password)

        # a pasta do jogo vive no mesmo formulario, entao salva junto
        self._save_launcher_path()

        self._refresh_profile_list()
        # salvar (seja uma conta nova ou uma edicao) encerra o modo edicao e
        # devolve o painel direito pro estado padrao, pronto pra cadastrar a
        # proxima conta.
        self._clear_form()
        self._log_direct(f"Conta '{account}' salva.")

    def _remove_profile(self, account):
        if not messagebox.askyesno("Remover conta", f"Remover a conta '{account}' da lista?"):
            return
        data = profiles.load_profiles()
        data = profiles.remove_profile(data, account)
        profiles.save_profiles(data)
        if account == self.editing_account:
            self._clear_form()
        self._refresh_profile_list()
        self._log_direct(f"Conta '{account}' removida.")

    def _update_running_state(self):
        """Nao existe mais uma barra de status escrita: quem conta o que
        esta rodando e a propria lista de contas (caixinha marcada +
        bolinha branca). Aqui so ligamos/desligamos o "parar todas"."""
        self.btn_stop.configure(state="normal" if self.running else "disabled")

    # ------------------------------------------------------------ launcher

    def _load_launcher_path(self):
        # Vem do perfis.json (arquivo do usuario). Se estiver vazio, tenta o
        # config.json -- caso de quem ja tinha o caminho configurado numa
        # versao anterior, antes de ele mudar de lugar.
        caminho = profiles.get_game_path()
        if not caminho:
            caminho = (bot.load_json(bot.CONFIG_PATH).get("launcher_exe_path") or "").strip()
            if caminho:
                profiles.set_game_path(caminho)
        self.entry_launcher_path.delete(0, "end")
        self.entry_launcher_path.insert(0, caminho)

    def _browse_launcher_path(self):
        path = filedialog.askdirectory(title="Selecione a pasta onde o jogo esta instalado")
        if path:
            self.entry_launcher_path.delete(0, "end")
            self.entry_launcher_path.insert(0, path)
            self._save_launcher_path()

    def _save_launcher_path(self):
        path = self.entry_launcher_path.get().strip()
        if path == profiles.get_game_path():
            return
        profiles.set_game_path(path)
        if path:
            self._log_direct(f"Pasta do jogo salva: {path}")
        else:
            self._log_direct("Pasta do jogo removida -- o bot nao vai mais abrir o jogo sozinho.")

    # ------------------------------------------------------------- bot

    def _quick_start_account(self, account):
        # Duplo clique numa linha inicia SO aquela conta na hora, sem
        # precisar marcar a caixinha e depois clicar em "Iniciar" -- o
        # atalho pra a acao mais comum (logar uma conta especifica).
        data = profiles.load_profiles()
        profile = next((p for p in profiles.list_profiles(data) if p.get("account") == account), None)
        if not profile:
            return
        self._start_accounts([profile], confirm_multi=False)

    def _start_accounts(self, selected_profiles, confirm_multi=True):
        already_running = [p.get("account") for p in selected_profiles if p.get("account") in self.running]
        to_start = [p for p in selected_profiles if p.get("account") not in self.running]

        if already_running:
            self._log_direct(f"Ja esta rodando: {', '.join(already_running)}.")

        if not to_start:
            return

        if confirm_multi and len(to_start) > 1 and not messagebox.askyesno(
            "Logar varias contas ao mesmo tempo",
            f"Vou iniciar {len(to_start)} contas ao mesmo tempo: "
            f"{', '.join(p.get('account') for p in to_start)}.\n\n"
            "Isso so funciona se o jogo permitir varias copias do client.exe abertas "
            "simultaneamente (uma por conta) -- se nao permitir, algumas contas podem "
            "ficar sem conseguir abrir o jogo. Continuar?",
        ):
            return

        if bot.STOP_FILE.exists():
            try:
                bot.STOP_FILE.unlink()
            except OSError:
                pass

        for profile in to_start:
            account = profile.get("account")
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._bot_thread_target, args=(account, profile, stop_event), daemon=True
            )
            self.running[account] = {"thread": thread, "stop_event": stop_event}
            self._log_direct(f"Iniciando '{account}'...")
            thread.start()

        self._refresh_profile_list()

    def _bot_thread_target(self, account, profile, stop_event):
        try:
            b, cfg = bot.build_bot(profile=profile)
            if b is None:
                bot.log.error(
                    "[%s] Nao foi possivel iniciar: faltam templates essenciais "
                    "(veja config.json/templates/).",
                    account,
                )
                return
            bot.run(b, cfg, stop_event=stop_event)
        except Exception:  # noqa: BLE001
            bot.log.exception("[%s] Erro inesperado no bot.", account)
        finally:
            # IMPORTANTE: nao tocar em nada do Tkinter daqui. Esta funcao
            # roda numa thread separada, e o Tkinter so pode ser usado pela
            # thread principal -- chamar self.after() daqui trava a thread
            # (foi exatamente o que aconteceu: a conta parava por dentro,
            # mas a interface nunca ficava sabendo e continuava mostrando
            # "rodando"). So avisamos por fila; quem mexe na tela e o
            # _poll_log_queue, que ja roda na thread certa.
            self.finished_queue.put(account)

    def _on_bot_finished(self, account):
        self.running.pop(account, None)
        self._refresh_profile_list()

    def _stop_bot(self):
        if not self.running:
            return
        for account, info in self.running.items():
            info["stop_event"].set()
        self._log_direct(f"Parando {len(self.running)} conta(s)...")
        self.btn_stop.configure(state="disabled")

    # ------------------------------------------------------------- log

    def _log_direct(self, message):
        bot.log.info(message)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self):
        try:
            while True:
                level, line = self.log_queue.get_nowait()
                self._append_log(level, line)
        except queue.Empty:
            pass

        # contas que terminaram (avisadas pelas threads via fila): tira da
        # lista de rodando e atualiza a tela -- aqui, na thread certa.
        finished = []
        try:
            while True:
                finished.append(self.finished_queue.get_nowait())
        except queue.Empty:
            pass
        for account in finished:
            self._on_bot_finished(account)

        self.after(200, self._poll_log_queue)

    def _append_log(self, level, line):
        tag = None
        if level in ("ERROR", "CRITICAL"):
            tag = "error"
        elif level == "WARNING":
            tag = "warning"
        elif level == "INFO":
            tag = "info"

        self.log_text.configure(state="normal")
        if tag:
            self.log_text.insert("end", line + "\n", tag)
        else:
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------- fechar

    def _on_close(self):
        if self.running:
            contas = ", ".join(self.running.keys())
            if not messagebox.askyesno("Bot rodando", f"Ainda rodando: {contas}. Parar tudo e fechar?"):
                return
            for info in self.running.values():
                info["stop_event"].set()
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
