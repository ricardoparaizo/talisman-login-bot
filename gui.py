"""
Interface grafica do bot, feita com CustomTkinter (biblioteca pura em
Python, MIT, sem dependencias pesadas -- so um wrapper sobre o Tkinter que
ja vem com o Python, entao continua simples/baixo risco pro antivirus).

Visual: MMORPG dos anos 2000, no estilo da propria interface do Talisman
Online -- fundo quase preto, molduras azuis, ciano de acento, rotulos
dourados, cantos retos e botoes com gradiente e relevo. As cores e os
widgets desenhados vivem no skin.py; aqui ficam so o layout e o
comportamento.

Layout em barra lateral + painel de detalhes:

    - Faixa de titulo (topo): nome do app atravessando a janela inteira,
      como a barra de titulo das janelas do jogo.
    - Barra lateral (esquerda): lista de contas cadastradas, com uma
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
# As cores vivem no skin.py, amostradas de prints da interface do proprio
# Talisman Online. Os apelidos abaixo existem pra o resto deste arquivo
# continuar lendo do mesmo jeito de antes -- so o que eles APONTAM mudou.
BG = skin.BG_APP           # fundo do conteudo
BG_SIDEBAR = skin.BG_SIDEBAR
SURFACE = skin.BG_PANEL    # painel do log
SURFACE_ALT = skin.BG_SUNKEN   # campos de texto (afundados)
SURFACE_HOVER = skin.BG_ROW_HOVER
ROW_HOVER = skin.BG_ROW_HOVER
ROW_SELECTED = skin.BG_ROW_SEL
BORDER = skin.EDGE_DARK
BORDER_STRONG = skin.EDGE_LIGHT
BORDER_FOCUS = skin.CYAN   # campo em foco ganha o ciano de acento

WHITE = skin.TEXT
TEXT = skin.TEXT
TEXT_SECOND = skin.TEXT_SOFT
TEXT_MUTED = skin.TEXT_MUTED
TEXT_DIM = skin.TEXT_DIM

DOT_IDLE = "#4d6273"       # bolinha "parado"
DOT_RUNNING = skin.CYAN    # bolinha "rodando" -- ciano = atividade

DANGER = skin.DANGER       # acao destrutiva + erro no log
DANGER_HOVER_BG = "#2a1414"
WARNING = skin.WARNING     # aviso no log
GOLD = skin.GOLD           # rotulos de campo e titulos de secao

FONT_FAMILY = skin.FONT
FONT_MONO_FAMILY = skin.FONT_MONO


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
# fileira de botoes todos gritando igual. Agora todos sao skin.GameButton
# (Canvas com gradiente e bevel) em vez de CTkButton -- a assinatura das
# tres funcoes continua a mesma, entao o resto do arquivo nao mudou.


def primary_button(master, text, command, width=120, bg=None):
    """Acao principal: dourada, como o botao que confirma as caixas de
    dialogo do jogo. So uma por area da tela."""
    return skin.GameButton(
        master, text=text, command=command, variant="primary",
        width=width, height=32, font_size=12, bold=True, bg=bg,
    )


def ghost_button(master, text, command, width=120, height=32, bg=None):
    """Acao secundaria: o azul padrao dos botoes do jogo."""
    return skin.GameButton(
        master, text=text, command=command, variant="normal",
        width=width, height=height, font_size=11, bg=bg,
    )


def text_button(master, text, command, width=90, height=24, color=None, hover_bg=None, bg=None):
    """Acao terciaria: so texto, sem caixa nenhuma. `color`/`hover_bg` sao
    aceitos e ignorados -- a variante 'link' do skin ja define as duas
    cores (apagada parada, ciano no hover)."""
    return skin.GameButton(
        master, text=text, command=command, variant="link",
        width=width, height=height, font_size=10, bg=bg,
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
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.app = app
        self.account = account
        self.selected = False
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
            corner_radius=0,
            border_width=1,
            fg_color=skin.CYAN,
            hover_color=skin.CYAN_SOFT,
            checkmark_color="#06202a",
            border_color=skin.CYAN_SOFT,
        )
        self.checkbox.grid(row=0, column=1, rowspan=2, padx=(12, 9), pady=6)

        name_row = ctk.CTkFrame(self, fg_color="transparent")
        name_row.grid(row=0, column=2, sticky="we", padx=(0, 8), pady=(6, 0))
        self.name_label = ctk.CTkLabel(
            name_row, text=account, font=_font(12, "bold"), text_color=TEXT, anchor="w"
        )
        self.name_label.pack(side="left")

        subtitle = " · ".join(part for part in (server, character) if part) or "sem servidor/personagem"
        self.subtitle_label = ctk.CTkLabel(
            self, text=subtitle, font=_font(10), text_color=TEXT_MUTED, anchor="w"
        )
        self.subtitle_label.grid(row=1, column=2, sticky="we", padx=(0, 8), pady=(0, 6))

        self.status_dot = ctk.CTkLabel(
            self,
            text="●",
            font=_font(11),
            text_color=DOT_RUNNING if is_running else DOT_IDLE,
            width=14,
        )
        self.status_dot.grid(row=0, column=3, rowspan=2, padx=(0, 12))

        # Sem clique simples aqui de proposito: a UNICA forma de abrir uma
        # conta pra edicao e o botao direito -> "Editar" (ver
        # App._show_row_menu / App._start_edit). Um clique simples na linha
        # nao deve mudar o formulario.
        for widget in (self, name_row, self.name_label, self.subtitle_label, self.status_dot):
            widget.bind("<Double-Button-1>", self._on_double_click)
            widget.bind("<Button-3>", self._on_right_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_toggle(self):
        self.app._on_account_toggled(self.account, bool(self.check_var.get()))

    def _on_right_click(self, event):
        self.app._show_row_menu(self.account, event)

    def _on_double_click(self, _event=None):
        self.app._quick_start_account(self.account)

    def _on_enter(self, _event=None):
        if not self.selected:
            self.configure(fg_color=ROW_HOVER)

    def _on_leave(self, _event=None):
        if not self.selected:
            self.configure(fg_color="transparent")

    def set_selected(self, selected):
        """A linha aberta no formulario se distingue so pelo fundo mais
        claro e pelo nome em branco -- sem barrinha de destaque."""
        self.selected = selected
        self.configure(fg_color=ROW_SELECTED if selected else "transparent")
        self.name_label.configure(text_color=WHITE if selected else TEXT)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title(APP_NAME)
        self.geometry("1160x760")
        self.minsize(980, 640)
        self.configure(fg_color=BG)
        self._set_window_icon()

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

        self._build_title_strip()
        self._build_sidebar()
        self._build_main_area()
        self._attach_log_handler()
        self._refresh_profile_list()
        self._load_launcher_path()
        self._poll_log_queue()
        self._try_dark_titlebar()

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
        except Exception:  # noqa: BLE001 - so um detalhe visual, nunca deve travar a UI
            pass

    # ---------------------------------------------------- barra de titulo

    def _build_title_strip(self):
        """A faixa azul com o nome do app, atravessando a janela inteira.

        E o elemento que mais entrega o estilo, e resolve de quebra um
        problema antigo: o nome do app morava na barra lateral, que tem
        largura fixa, e quebrava em duas linhas ("Bot Login - Talisman /
        Online"). Aqui em cima ele tem a janela toda pra caber."""
        strip = skin.TitleStrip(self, APP_NAME.upper(), height=34,
                                subtitle=f"{APP_AUTHOR}  {APP_VERSION}")
        strip.grid(row=0, column=0, columnspan=2, sticky="we")

    # ------------------------------------------------------ barra lateral

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=296, fg_color=BG_SIDEBAR, corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(3, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        # borda direita de 1px, separando da area de conteudo
        edge = ctk.CTkFrame(self, width=1, fg_color=skin.EDGE_PANEL, corner_radius=0)
        edge.grid(row=1, column=0, sticky="nse")

        # -- cabecalho --
        # O nome do app agora vive na faixa de titulo, no topo da janela;
        # aqui sobra so o credito, discreto.
        header = ctk.CTkFrame(sidebar, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=22, pady=(16, 0))
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(anchor="w", fill="x")

        logo = load_app_image(24)
        if logo is not None:
            ctk.CTkLabel(title_row, text="", image=logo).pack(side="left", padx=(0, 8))

        title_text = ctk.CTkFrame(title_row, fg_color="transparent")
        title_text.pack(side="left")
        by_row = ctk.CTkFrame(title_text, fg_color="transparent")
        by_row.pack(anchor="w")
        ctk.CTkLabel(by_row, text="by: ", font=_font(10), text_color=TEXT_MUTED).pack(side="left")

        # O nome do autor leva pro repositorio do projeto. Fica sublinhado
        # so no hover, pra nao virar mais um elemento gritando na tela.
        self.author_link = ctk.CTkLabel(
            by_row, text=APP_AUTHOR, font=_font(10), text_color=TEXT_SECOND, cursor="hand2"
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

        ctk.CTkLabel(by_row, text=f" ({APP_VERSION})", font=_font(10), text_color=TEXT_MUTED).pack(
            side="left"
        )

        hairline(sidebar, bg=BG_SIDEBAR).grid(row=1, column=0, sticky="we", padx=22, pady=(18, 0))

        # -- rotulo da secao + acao secundaria --
        section = ctk.CTkFrame(sidebar, fg_color="transparent")
        section.grid(row=2, column=0, sticky="we", padx=22, pady=(16, 6))
        section.grid_columnconfigure(0, weight=1)
        self.section_label = ctk.CTkLabel(
            section, text=_tracked("CONTAS"), font=_font(9, "bold"), text_color=GOLD, anchor="w"
        )
        self.section_label.grid(row=0, column=0, sticky="w")
        self.btn_stop = text_button(section, "parar todas", self._stop_bot, width=76, height=22,
                                    bg=BG_SIDEBAR)
        self.btn_stop.configure(state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="e")

        # -- lista de contas (scrollable) --
        self.account_list_frame = ctk.CTkScrollableFrame(
            sidebar,
            fg_color=skin.BG_SUNKEN,
            corner_radius=0,
            border_width=1,
            border_color=skin.EDGE_PANEL,
            # bem discreta: o CTk nao esconde a barra sozinho quando a lista
            # cabe inteira, entao ela fica quase invisivel parada e so
            # aparece de verdade quando voce passa o mouse/rola.
            scrollbar_button_color="#1b3646",
            scrollbar_button_hover_color=skin.CYAN_DIM,
        )
        self.account_list_frame.grid(row=3, column=0, sticky="nswe", padx=(14, 8), pady=(0, 8))
        self.account_list_frame.grid_columnconfigure(0, weight=1)

        # -- rodape da barra lateral --
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="we", padx=22, pady=(4, 22))
        self.btn_start = primary_button(footer, "Iniciar todas", self._start_all, width=252,
                                        bg=BG_SIDEBAR)
        self.btn_start.configure(height=38)
        self.btn_start.pack(fill="x")
        ghost_button(footer, "+  Nova conta", self._clear_form, width=252, height=34,
                     bg=BG_SIDEBAR).pack(fill="x", pady=(8, 0))

    # ---------------------------------------------------------- main area

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=1, sticky="nswe")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=0)
        main.grid_rowconfigure(4, weight=1)

        self._build_page_header(main)
        self._build_detail_panel(main)
        self._build_log_panel(main)

    def _build_page_header(self, master):
        header = ctk.CTkFrame(master, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=34, pady=(28, 0))
        self.page_title = ctk.CTkLabel(
            header, text="Adicione uma conta", font=_font(15, "bold"), text_color=skin.CYAN, anchor="w"
        )
        self.page_title.pack(anchor="w")
        self.page_sub = ctk.CTkLabel(
            header,
            text=NEW_ACCOUNT_HINT,
            font=_font(11),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.page_sub.pack(anchor="w", pady=(3, 0))

    def _build_detail_panel(self, master):
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=1, column=0, sticky="we", padx=34, pady=(22, 0))
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
            corner_radius=0,
            height=32,
        )
        # anel de foco -- feedback de qual campo esta ativo, sem cor nenhuma
        entry.bind("<FocusIn>", lambda _e: entry.configure(border_color=BORDER_FOCUS))
        entry.bind("<FocusOut>", lambda _e: entry.configure(border_color=BORDER_STRONG))
        return entry

    def _field_label(self, master, text):
        return ctk.CTkLabel(master, text=text, font=_font(10), text_color=GOLD, anchor="w")

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
            button_color=skin.BTN_BOT,
            button_hover_color=skin.BTN_TOP,
            dropdown_fg_color=skin.BG_PANEL,
            dropdown_hover_color=skin.BTN_BOT,
            dropdown_text_color=TEXT,
            dropdown_font=_font(11),
            text_color=TEXT,
            font=_font(12),
            corner_radius=0,
            height=32,
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
        hairline(master, bg=BG).grid(row=3, column=0, sticky="we", padx=34, pady=(28, 0))

        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.grid(row=4, column=0, sticky="nswe", padx=34, pady=(20, 26))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(wrapper, fg_color="transparent")
        head.grid(row=0, column=0, sticky="we", pady=(0, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text=_tracked("REGISTRO"), font=_font(9, "bold"), text_color=GOLD, anchor="w"
        ).grid(row=0, column=0, sticky="w")
        text_button(head, "limpar", self._clear_log, width=60, height=22,
                    bg=BG).grid(row=0, column=1, sticky="e")

        self.log_text = ctk.CTkTextbox(
            wrapper,
            fg_color=skin.BG_SUNKEN,
            border_color=skin.EDGE_PANEL,
            border_width=1,
            text_color=TEXT_SECOND,
            corner_radius=0,
            font=_font(11, family=FONT_MONO_FAMILY),
            wrap="word",
            activate_scrollbars=True,
            scrollbar_button_color="#1b3646",
            scrollbar_button_hover_color=skin.CYAN_DIM,
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

        self.section_label.configure(
            text=_tracked("CONTAS") + (f"   {len(accounts)}" if accounts else "")
        )

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
                row.grid(row=idx, column=0, sticky="we", pady=1)
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
            bg=skin.BG_PANEL,
            fg=skin.TEXT_SOFT,
            activebackground=skin.BTN_BOT,
            activeforeground=skin.CYAN,
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
