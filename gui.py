"""
Interface grafica do bot, no estilo Apple TV / design system da Apple (HIG).

Tudo e desenhado num tk.Canvas pelo ui_kit.py: o fundo (arte desfocada com
paineis de vidro de verdade) e uma imagem, e os componentes por cima sao
imagens com transparencia + textos do canvas -- por isso o vidro e
translucido de fato. Os campos de digitacao e o registro sao widgets do Tk
encaixados no canvas, com a cor do vidro exatamente onde ficam. As cores e
parametros do vidro vivem no skin.py.

Layout:
    - Barra lateral (esquerda): nome do app e a lista de contas (cartoes de
      vidro). Clique simples SELECIONA a conta; o interruptor de cada cartao
      liga/desliga o login dela; duplo clique inicia o login na hora; botao
      direito abre o menu (iniciar/parar, editar, remover). Embaixo, "Iniciar
      Login" (da conta selecionada) e "+ Nova conta".
    - Area principal (direita), com abas (controle segmentado):
        Contas       -- formulario da conta (login, senha, servidor, nick) e
                        a pasta do jogo.
        Entrar Cave  -- entra na cave escolhida com a conta selecionada,
                        repetindo o pedido ate conseguir (ver cave.py).
      Embaixo das duas, o registro (log).

A versao anterior (CustomTkinter, vidro simulado) esta em gui_ctk.py.
"""

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import bot
import profiles
import skin
import ui_kit
from paths import RESOURCE_DIR, USER_DATA_DIR

APP_NAME = "Bot Login - Talisman Online"
APP_VERSION = "v1.1"
APP_AUTHOR = "TheSimitarBeast"
APP_URL = "https://github.com/ricardoparaizo/talisman-login-bot"

NEW_ACCOUNT_HINT = (
    "Preencha os campos abaixo para adicionar uma conta ao bot. Seus dados ficam salvos apenas "
    "localmente na pasta Documentos do seu computador."
)
CAVE_HINT = (
    "Selecione uma conta online na lista da esquerda, escolha a cave e clique em Entrar. Com o "
    "personagem perto do NPC da cave, o bot repete o pedido de entrar ate conseguir. O jogo nao "
    "pode estar minimizado."
)

ICON_ICO = RESOURCE_DIR / "icon.ico"
ICON_PNG = RESOURCE_DIR / "icon.png"

KNOWN_SERVERS = [
    "White Horse [NEW]",
    "Tiger Fish (WW)",
    "Sky Ice (GSM&BI)",
    "All Stars",
    "Light in the Darkness",
]

# Rotulo -> (pausa entre voltas em segundos, pedidos por volta). A interface
# do jogo passa pelo gancho ~3x por segundo (medido), entao o que mais
# acelera e mandar varios pedidos por volta.
CAVE_VELOCIDADES = [
    ("Maximo (~30 por segundo)", 0.0, 10),
    ("Muito rapido (~15 por segundo)", 0.0, 5),
    ("Rapido (~6 por segundo)", 0.0, 2),
    ("Normal (~3 por segundo)", 0.0, 1),
]

TABS = ["Contas", "Entrar Cave"]


class QueueLogHandler(logging.Handler):
    """Manda cada linha de log pra uma Queue, pra thread da interface poder
    ler e mostrar na tela sem travar (o Tk so pode ser tocado pela thread
    principal)."""

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put((record.levelname, self.format(record)))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=skin.BG_APP)
        self._set_window_icon()

        self.canvas = tk.Canvas(self, bg=skin.BG_APP, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.kit = ui_kit.Kit(self.canvas)
        s = self.kit.s
        self.geometry(f"{s(1160)}x{s(760)}")
        self.minsize(s(980), s(640))

        self.log_queue = queue.Queue()
        # contas que terminaram; preenchida pelas threads dos bots e
        # esvaziada pela thread da interface (veja _bot_thread_target)
        self.finished_queue = queue.Queue()
        # Uma conta por entrada: {"thread": Thread, "stop_event": Event}.
        # Permite rodar VARIAS contas ao mesmo tempo, cada uma na sua propria
        # thread/janela do jogo (bot.py cuida de travar cada uma na sua
        # copia do client.exe).
        self.running = {}
        # conta carregada no formulario pra edicao (None = modo "adicionar").
        self.editing_account = None
        # Uma selecao so, valendo pras duas abas: e a conta que o "Iniciar
        # Login" e o "Entrar" (cave) usam.
        self.selected_account = None
        self.tab = "Contas"
        self.list_offset = 0   # rolagem da lista de contas (em linhas)

        # -- cave --
        # pid -> {"thread", "stop_event", "tipo": "entrar", "cave": sigla, "account": conta}
        self.cave_runs = {}
        self.cave_queue = queue.Queue()
        # [(pid, nick)] da ultima deteccao (nick '' = fora do mundo, None =
        # sem resposta); None = ainda nao detectou
        self.cave_online = None
        self._cave_detecting = False
        import cave

        self._caves = {cave.rotulo(*c): c for c in cave.lista_caves()}
        # Abre ja na ultima cave usada (ou na primeira da lista).
        ultimas = cave.recentes()
        self.cave_choice = next(
            (r for r, c in self._caves.items() if ultimas and c[0] == ultimas[0]),
            next(iter(self._caves)),
        )
        self.speed_choice = CAVE_VELOCIDADES[0][0]

        # -- desenho --
        self._bg_size = None
        self._bg_photo = None
        self._layout_job = None
        self._focused = None   # campo de texto em foco (anel azul)
        self._list_area = None  # retangulo da lista de contas (pra rolagem)
        self._list_overflow = False

        self._build_embeds()
        self._attach_log_handler()
        self._load_launcher_path()

        self.bind("<Configure>", self._on_configure, add="+")
        self.canvas.bind("<MouseWheel>", self._on_wheel, add="+")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(20, self._relayout)
        self._poll_log_queue()
        self._try_dark_titlebar()
        # Deteccao de quem esta online: comeca logo ao abrir o bot e segue
        # periodica -- a lista mostra online/offline o tempo todo.
        self.after(300, self._cave_detect_tick)

    # ------------------------------------------------------------ janela

    def _set_window_icon(self):
        """Icone da janela (barra de titulo, Alt+Tab e barra de tarefas). Se
        nada der certo, segue sem icone -- e so aparencia."""
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
        """Barra de titulo escura (Windows 10/11), da cor do fundo. Se nao
        der, so ignora -- e um detalhe visual."""
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            cor = ctypes.c_int(skin.colorref(skin.BG_APP))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cor), ctypes.sizeof(cor))
        except Exception:  # noqa: BLE001
            pass

    def _on_configure(self, event):
        # So interessa a janela. Espera o redimensionamento "assentar" antes
        # de redesenhar o fundo -- gerar a imagem a cada pixel travaria.
        if event.widget is not self:
            return
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(90, self._relayout)

    def _panels(self):
        s = self.kit.s
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        M, gap, sw = s(26), s(18), s(300)
        return (M, M, M + sw, H - M), (M + sw + gap, M, W - M, H - M)

    def _relayout(self):
        """Redesenha o fundo (so quando o tamanho muda) e a interface."""
        self._layout_job = None
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        if W <= 1 or H <= 1:
            self.after(50, self._relayout)
            return
        if (W, H) != self._bg_size:
            try:
                from PIL import ImageTk
                import numpy as np

                img = ui_kit.render_background(W, H, list(self._panels()), self.kit.s(26))
                self._bg_photo = ImageTk.PhotoImage(img)
                self.kit.bg = np.asarray(img)
                self.canvas.delete("bg")
                self.canvas.create_image(0, 0, image=self._bg_photo, anchor="nw", tags=("bg",))
                self.canvas.tag_lower("bg")
                self._bg_size = (W, H)
            except Exception:  # noqa: BLE001 - sem Pillow/numpy: fica a cor solida
                bot.log.debug("Nao consegui desenhar o fundo.", exc_info=True)
        self.render()

    # ------------------------------------------------ widgets encaixados

    def _make_entry(self, show=""):
        e = tk.Entry(
            self.canvas, bd=0, relief="flat", highlightthickness=0, show=show,
            fg=skin.TEXT, insertbackground=skin.TEXT, font=self.kit.font(13),
            selectbackground=skin.SYSTEM_BLUE, selectforeground="#ffffff",
        )
        e.bind("<FocusIn>", lambda _e: self._set_focus(e), add="+")
        e.bind("<FocusOut>", lambda _e: self._set_focus(None), add="+")
        return e

    def _build_embeds(self):
        self.entry_account = self._make_entry()
        self.entry_password = self._make_entry(show="•")
        self.entry_server = self._make_entry()
        self.entry_character = self._make_entry()
        self.entry_launcher_path = self._make_entry()
        self.entry_account.bind("<Return>", lambda _e: self._save_profile())
        self.entry_character.bind("<Return>", lambda _e: self._save_profile())

        self.log_text = tk.Text(
            self.canvas, bd=0, relief="flat", highlightthickness=0, wrap="word",
            fg=skin.TEXT_SOFT, font=self.kit.font(12, family=skin.FONT_MONO),
            padx=0, pady=0, cursor="arrow", insertwidth=0,
            selectbackground=skin.SYSTEM_BLUE, selectforeground="#ffffff",
        )
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("error", foreground=skin.DANGER)
        self.log_text.tag_config("warning", foreground=skin.WARNING)
        self.log_text.tag_config("info", foreground=skin.TEXT_SOFT)

        self._form_entries = [
            self.entry_account, self.entry_password, self.entry_server,
            self.entry_character, self.entry_launcher_path,
        ]
        # um item "window" do canvas por widget, criado uma vez e so movido
        self._win = {}
        for w in self._form_entries + [self.log_text]:
            self._win[w] = self.canvas.create_window(0, 0, window=w, anchor="nw", tags=("embed",),
                                                     state="hidden")

    def _place(self, widget, x, y, w, h, bg):
        item = self._win[widget]
        self.canvas.coords(item, x, y)
        self.canvas.itemconfigure(item, width=max(1, int(w)), height=max(1, int(h)), state="normal")
        widget.configure(bg=bg)

    def _hide(self, widget):
        self.canvas.itemconfigure(self._win[widget], state="hidden")

    def _set_focus(self, entry):
        if entry is not self._focused:
            self._focused = entry
            self.render()

    # ------------------------------------------------------------ desenho

    def render(self):
        """Redesenha todos os componentes a partir do estado atual."""
        if self._bg_size is None:
            return
        self.kit.clear()
        side, main = self._panels()
        self._draw_sidebar(*side)
        self._draw_main(*main)

    # -- barra lateral --

    def _logo(self, size):
        def gerar():
            from PIL import Image

            return Image.open(ICON_PNG).convert("RGBA").resize((size, size), Image.LANCZOS)

        try:
            return self.kit.photo(("logo", size), gerar) if ICON_PNG.exists() else None
        except Exception:  # noqa: BLE001
            return None

    def _draw_sidebar(self, x0, y0, x1, y1):
        k, s = self.kit, self.kit.s
        p = s(20)
        cw = x1 - x0 - 2 * p

        # cabecalho: icone + nome do app, credito embaixo
        logo = self._logo(s(36))
        tx = x0 + p
        if logo is not None:
            k.image(x0 + p, y0 + p + s(2), logo)
            tx += s(48)
        k.text(tx, y0 + p - s(1), "Talisman Online", skin.TYPE["title2"], "bold",
               family=skin.FONT_TITLE)
        by_y = y0 + p + s(24)
        partes = [("Bot Login · by ", None), (APP_AUTHOR, "link"), (f"  ·  {APP_VERSION}", None)]
        cx = tx
        for texto, tipo in partes:
            cor = skin.TEXT_SOFT if tipo else skin.TEXT_MUTED
            tid = k.text(cx, by_y, texto, skin.TYPE["subheadline"], color=cor)
            largura = k.text_width(texto, skin.TYPE["subheadline"])
            if tipo == "link":
                k.add_hot(
                    (cx, by_y, cx + largura, by_y + s(16)), on_click=self._open_project_page,
                    on_hover=lambda d, tid=tid: self.canvas.itemconfigure(
                        tid, fill="#ffffff" if d else skin.TEXT_SOFT),
                )
            cx += largura

        y = y0 + p + s(56)
        k.divider(x0 + p, x1 - p, y)
        y += s(18)

        # titulo da secao + contagem + "parar todas"
        contas = profiles.list_profiles(profiles.load_profiles())
        k.text(x0 + p, y + s(3), "Contas", skin.TYPE["headline"], "bold")
        if contas:
            bx = x0 + p + k.text_width("Contas", skin.TYPE["headline"], "bold") + s(8)
            k.badge(bx + k.text_width(str(len(contas)), 11, "bold") + s(20), y,
                    str(len(contas)), (255, 255, 255, 30), skin.TEXT_SOFT)
        k.button(x1 - p - s(84), y, s(84), s(22), "parar todas", self._stop_bot,
                 style="plain", enabled=bool(self.running), size=12)
        y += s(36)

        # rodape: Iniciar Login + Nova conta
        h_ini, h_nova, vao = s(42), s(38), s(10)
        rodape_y = y1 - p - h_nova - vao - h_ini
        sel = self.selected_account
        if sel and sel in self.running:
            rotulo_login = "Parar Login"
        else:
            rotulo_login = "Iniciar Login"
        k.button(x0 + p, rodape_y, cw, h_ini, rotulo_login, self._toggle_login_selected,
                 style="white", enabled=bool(sel), size=14)
        k.button(x0 + p, rodape_y + h_ini + vao, cw, h_nova, "+  Nova conta", self._clear_form,
                 style="gray", size=13)

        # lista de contas
        lista_y0, lista_y1 = y, rodape_y - s(16)
        self._list_area = (x0, lista_y0, x1, lista_y1)
        if not contas:
            k.text(x0 + p, lista_y0 + s(6),
                   "Nenhuma conta cadastrada.\nClique em '+ Nova conta' pra comecar.",
                   skin.TYPE["callout"], color=skin.TEXT_DIM)
            self._list_overflow = False
            return
        rh, rvao = s(66), s(10)
        cabem = max(1, (lista_y1 - lista_y0 + rvao) // (rh + rvao))
        self._list_overflow = len(contas) > cabem
        self.list_offset = max(0, min(self.list_offset, len(contas) - cabem))
        for i, prof in enumerate(contas[self.list_offset:self.list_offset + cabem]):
            self._draw_account_row(prof, x0 + p - s(4), lista_y0 + i * (rh + rvao), cw + s(8), rh)
        if self._list_overflow:
            k.text((x0 + x1) / 2, lista_y1 + s(2), "role pra ver mais contas",
                   skin.TYPE["caption"], color=skin.TEXT_DIM, anchor="n")

    def _draw_account_row(self, prof, x, y, w, h):
        k, s = self.kit, self.kit.s
        conta = prof.get("account", "")
        login_on = conta in self.running
        estado = self._cave_state_for(prof)
        ativo = login_on or estado == "entrando"
        selecionado = conta == self.selected_account

        normal, hover = k.card_photos(w, h, active=ativo, selected=selecionado)
        iid = k.image(x, y, normal)
        k.add_hot(
            (x, y, x + w, y + h),
            on_click=lambda: self._on_account_row_click(conta),
            on_double=lambda: self._quick_start_account(conta),
            on_right=lambda e: self._show_row_menu(conta, e),
            on_hover=lambda d: self.canvas.itemconfigure(iid, image=hover if d else normal),
        )

        # interruptor do login (HIG: switch) -- liga/desliga SO o login
        k.toggle(x + s(14), y + (h - s(25)) / 2, login_on,
                 lambda: self._on_account_toggled(conta, not login_on))

        tx = x + s(70)
        k.text(tx, y + s(13), conta, 14, "bold")
        sub = " · ".join(v for v in (prof.get("server_name", ""), prof.get("character_name", "")) if v)
        k.text(tx, y + s(36), sub or "sem servidor/personagem", skin.TYPE["subheadline"],
               color="#dbe8ff" if ativo else skin.TEXT_MUTED, width=w - s(84))

        # etiqueta de estado
        if login_on:
            texto, fill, cor, dot = "rodando", _rgba_hex("#f5f5f7"), "#0a64e0", skin.SYSTEM_GREEN
        elif estado == "entrando":
            texto, fill, cor, dot = "entrando na cave", _rgba_hex("#f5f5f7"), "#0a64e0", skin.SYSTEM_GREEN
        elif estado == "online":
            texto, fill, cor, dot = "online", (48, 209, 88, 52), skin.SYSTEM_GREEN, skin.SYSTEM_GREEN
        elif estado == "offline":
            texto, fill, cor, dot = "offline", (255, 255, 255, 22), skin.SYSTEM_GRAY, skin.SYSTEM_GRAY2
        else:
            texto, fill, cor, dot = "...", (255, 255, 255, 22), skin.SYSTEM_GRAY, skin.SYSTEM_GRAY3
        k.badge(x + w - s(12), y + s(11), texto, fill, cor, dot=dot)

    # -- area principal --

    def _draw_main(self, x0, y0, x1, y1):
        k, s = self.kit, self.kit.s
        p = s(30)
        k.segmented(x0 + p, y0 + s(22), TABS, self.tab, self._show_tab)
        y = y0 + s(22) + s(32) + s(28)
        if self.tab == "Contas":
            y = self._draw_tab_contas(x0 + p, y, x1 - p)
        else:
            for e in self._form_entries:
                self._hide(e)
            y = self._draw_tab_cave(x0 + p, y, x1 - p)
        self._draw_log(x0 + p, y + s(26), x1 - p, y1 - s(24))

    def _title(self, x, y, titulo, sub, largura):
        k, s = self.kit, self.kit.s
        k.text(x, y, titulo, skin.TYPE["large_title"], "bold", family=skin.FONT_TITLE)
        k.text(x, y + s(38), sub, skin.TYPE["callout"], color=skin.TEXT_MUTED, width=largura)
        linhas = 1 + k.text_width(sub, skin.TYPE["callout"]) // max(1, largura)
        return y + s(38) + linhas * s(17) + s(22)

    def _label(self, x, y, texto):
        self.kit.text(x, y, texto, skin.TYPE["subheadline"], color=skin.TEXT_MUTED)

    def _entry_field(self, entry, x, y, w, h, direita=0):
        """Campo de texto (HIG) com o tk.Entry encaixado dentro."""
        s = self.kit.s
        cor = self.kit.field(x, y, w, h, focused=self._focused is entry)
        fh = self.kit.font(13).metrics("linespace")
        self._place(entry, x + s(12), y + (h - fh) / 2, w - s(24) - direita, fh, cor)

    def _draw_tab_contas(self, x0, y, x1):
        k, s = self.kit, self.kit.s
        cw = x1 - x0
        if self.editing_account:
            prof = self._profile(self.editing_account) or {}
            sub = " · ".join(v for v in (prof.get("server_name", ""), prof.get("character_name", "")) if v)
            y = self._title(x0, y, self.editing_account, sub or "sem servidor/personagem definidos", cw)
        else:
            y = self._title(x0, y, "Adicione uma conta", NEW_ACCOUNT_HINT, cw)

        col = (cw - s(18)) / 2
        fh = s(38)
        xr = x0 + col + s(18)
        linha = s(20) + fh + s(16)

        self._label(x0, y, "Conta")
        self._label(xr, y, "Senha")
        self._entry_field(self.entry_account, x0, y + s(20), col, fh)
        self._entry_field(self.entry_password, xr, y + s(20), col, fh)
        y += linha

        self._label(x0, y, "Servidor")
        self._label(xr, y, "Nick")
        self._entry_field(self.entry_server, x0, y + s(20), col, fh, direita=s(26))
        # chevron do servidor: abre a lista dos servidores conhecidos
        chev_x = x0 + col - s(30)
        k.chevron(chev_x + s(14), y + s(20) + fh / 2)
        k.add_hot((chev_x, y + s(20), x0 + col, y + s(20) + fh), on_click=lambda: self._menu_servidor(
            x0, y + s(20) + fh + s(4)))
        self._entry_field(self.entry_character, xr, y + s(20), col, fh)
        y += linha

        self._label(x0, y, "Pasta do jogo")
        bw = s(112)
        self._entry_field(self.entry_launcher_path, x0, y + s(20), cw - bw - s(10), fh)
        k.button(x1 - bw, y + s(20), bw, fh, "Procurar", self._browse_launcher_path, style="gray")
        y += linha + s(4)

        k.divider(x0, x1, y)
        y += s(18)
        k.button(x0, y, s(150), s(40), "Salvar conta", self._save_profile, style="white", size=14)
        return y + s(40)

    def _draw_tab_cave(self, x0, y, x1):
        k, s = self.kit, self.kit.s
        cw = x1 - x0
        y = self._title(x0, y, "Entrar na cave", CAVE_HINT, cw)

        # conta selecionada (so leitura)
        self._label(x0, y, "Conta")
        k.button(x1 - s(76), y - s(3), s(76), s(20), "atualizar", self._cave_detect, style="plain", size=12)
        fh = s(38)
        k.field(x0, y + s(20), cw, fh)
        prof = self._profile(self.selected_account) if self.selected_account else None
        pid = self._selected_cave_pid()
        if not prof:
            texto, cor = "Selecione uma conta online na lista da esquerda", skin.TEXT_MUTED
        else:
            nick = (prof.get("character_name") or "").strip()
            if not nick:
                estado = "sem nick cadastrado -- edite a conta"
            elif self.cave_online is None:
                estado = "procurando..."
            else:
                estado = "online" if pid else "offline"
            texto = f"{prof.get('account')}   ·   {nick or '?'}   ·   {estado}"
            cor = skin.TEXT if pid else skin.TEXT_MUTED
        k.text(x0 + s(14), y + s(20) + fh / 2, texto, skin.TYPE["body"], color=cor, anchor="w")
        y += s(20) + fh + s(6)
        status = self._cave_status_text()
        if status:
            k.text(x0 + s(2), y, status, skin.TYPE["footnote"], color=skin.TEXT_DIM)
        y += s(22)

        col = (cw - s(18)) / 2
        xr = x0 + col + s(18)
        self._label(x0, y, "Cave")
        self._label(xr, y, "Velocidade")
        k.popup(x0, y + s(20), col, fh, self.cave_choice, lambda: self._menu_cave(x0, y + s(20) + fh + s(4)))
        k.popup(xr, y + s(20), col, fh, self.speed_choice,
                lambda: self._menu_velocidade(xr, y + s(20) + fh + s(4)))
        y += s(20) + fh + s(22)

        k.divider(x0, x1, y)
        y += s(18)
        run = self.cave_runs.get(pid) if pid else None
        k.button(x0, y, s(150), s(40), "Parar" if run else "Entrar", self._toggle_cave,
                 style="white", enabled=bool(pid), size=14)
        return y + s(40)

    def _draw_log(self, x0, y0, x1, y1):
        k, s = self.kit, self.kit.s
        k.divider(x0, x1, y0 - s(14))
        k.text(x0, y0 + s(4), "Registro", skin.TYPE["headline"], "bold")
        k.button(x1 - s(60), y0, s(60), s(22), "limpar", self._clear_log, style="plain", size=12)
        top = y0 + s(32)
        h = max(s(90), y1 - top)
        cor = skin.mix(k.sample((x0 + x1) / 2, top + h / 2), "#000000", 0.45)
        foto = k.photo(("logbox", x1 - x0, h, cor), lambda: ui_kit.rounded(
            x1 - x0, h, s(16), fill=_rgba_hex(cor), outline=(255, 255, 255, 24)))
        k.image(x0, top, foto)
        self._place(self.log_text, x0 + s(14), top + s(12), x1 - x0 - s(28), h - s(24), cor)

    # -- menus --

    def _menu_at(self, items, x, y, checked=None):
        self.kit.menu(items, self.canvas.winfo_rootx() + x, self.canvas.winfo_rooty() + y, checked=checked)

    def _menu_servidor(self, x, y):
        def escolher(nome):
            self.entry_server.delete(0, "end")
            self.entry_server.insert(0, nome)

        self._menu_at([(n, lambda n=n: escolher(n)) for n in KNOWN_SERVERS], x, y,
                      checked=self.entry_server.get())

    def _menu_cave(self, x, y):
        """Pop-up das caves: as usadas por ultimo primeiro (secao
        "Recentes"), depois a lista completa na ordem de sempre."""
        import cave

        def escolher(rotulo):
            self.cave_choice = rotulo
            self.render()

        por_sigla = {c[0]: r for r, c in self._caves.items()}
        itens = []
        recentes = [por_sigla[s] for s in cave.recentes() if s in por_sigla]
        if recentes:
            itens.append(("Recentes", None))
            itens += [(r, lambda r=r: escolher(r)) for r in recentes]
            itens += [None, ("Todas as caves", None)]
        itens += [(r, lambda r=r: escolher(r)) for r in self._caves]
        self._menu_at(itens, x, y, checked=self.cave_choice)

    def _menu_velocidade(self, x, y):
        def escolher(rotulo):
            self.speed_choice = rotulo
            self.render()

        self._menu_at([(r, lambda r=r: escolher(r)) for r, _, _ in CAVE_VELOCIDADES], x, y,
                      checked=self.speed_choice)

    def _show_row_menu(self, account, event):
        """Menu do botao direito em cima de uma conta. "Editar" e o UNICO
        caminho que carrega uma conta no formulario."""
        rodando = account in self.running
        self.kit.menu([
            ("Parar login" if rodando else "Iniciar login",
             lambda: self._on_account_toggled(account, not rodando)),
            None,
            ("Editar", lambda: self._start_edit(account)),
            ("Remover", lambda: self._remove_profile(account)),
            None,
            ("Abrir a pasta das minhas contas", self._open_data_folder),
        ], event.x_root, event.y_root)

    def _on_wheel(self, event):
        a = self._list_area
        if not a or not self._list_overflow:
            return
        if a[0] <= event.x <= a[2] and a[1] <= event.y <= a[3]:
            self.list_offset += -1 if event.delta > 0 else 1
            self.render()

    def _show_tab(self, nome):
        self.tab = nome
        if nome == "Entrar Cave":
            # Abriu a aba: procura os jogos online na hora.
            self._cave_detect()
        self.render()

    # ------------------------------------------------------------- utilidades

    def _open_project_page(self):
        try:
            import webbrowser

            webbrowser.open(APP_URL)
        except Exception:  # noqa: BLE001
            messagebox.showinfo("Projeto", APP_URL)

    def _open_data_folder(self):
        """Abre no Explorer a pasta onde as contas ficam salvas."""
        try:
            import os

            os.startfile(str(USER_DATA_DIR))  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo("Pasta das contas", f"Suas contas ficam em:\n\n{USER_DATA_DIR}\n\n({exc})")

    def _attach_log_handler(self):
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
        bot.log.addHandler(handler)
        bot.log.setLevel(logging.INFO)

    # ------------------------------------------------------- contas (CRUD)

    def _profile(self, account):
        return next(
            (p for p in profiles.list_profiles(profiles.load_profiles()) if p.get("account") == account),
            None,
        )

    def _refresh_profile_list(self):
        self.render()

    def _on_account_row_click(self, account):
        self.selected_account = account
        self.render()

    def _on_account_toggled(self, account, checked):
        """Liga (inicia o login) ou desliga (para) a conta."""
        if checked:
            if account in self.running:
                return
            profile = self._profile(account)
            if not profile:
                return
            self._start_accounts([profile], confirm_multi=False)
        else:
            info = self.running.get(account)
            if info:
                info["stop_event"].set()
                self._log_direct(f"Parando '{account}'...")

    def _toggle_login_selected(self):
        """Botao "Iniciar Login": inicia (ou para) o login da conta selecionada."""
        account = self.selected_account
        if account:
            self._on_account_toggled(account, account not in self.running)

    def _start_edit(self, account):
        """Modo edicao: carrega a conta no formulario (so pelo botao direito
        -> Editar). Tambem seleciona a conta."""
        profile = self._profile(account)
        if not profile:
            return
        self.editing_account = account
        self.selected_account = account
        self.tab = "Contas"
        for entry, valor in (
            (self.entry_account, profile.get("account", "")),
            (self.entry_password, ""),  # nunca mostramos a senha salva
            (self.entry_server, profile.get("server_name", "")),
            (self.entry_character, profile.get("character_name", "")),
        ):
            entry.delete(0, "end")
            entry.insert(0, valor)
        self.render()

    def _clear_form(self):
        """Formulario no modo padrao: pronto pra cadastrar uma conta nova."""
        self.editing_account = None
        self.tab = "Contas"
        for entry in (self.entry_account, self.entry_password, self.entry_server, self.entry_character):
            entry.delete(0, "end")
        self.render()
        self.entry_account.focus_set()

    def _save_profile(self):
        account = self.entry_account.get().strip()
        server_name = self.entry_server.get().strip()
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

        # salvar encerra o modo edicao; a conta salva fica selecionada,
        # pronta pro "Iniciar Login"
        self._clear_form()
        self.canvas.focus_set()
        self._on_account_row_click(account)
        self._log_direct(f"Conta '{account}' salva.")

    def _remove_profile(self, account):
        if not messagebox.askyesno("Remover conta", f"Remover a conta '{account}' da lista?"):
            return
        data = profiles.load_profiles()
        data = profiles.remove_profile(data, account)
        profiles.save_profiles(data)
        if account == self.editing_account:
            self._clear_form()
        if account == self.selected_account:
            self.selected_account = None
        self.render()
        self._log_direct(f"Conta '{account}' removida.")

    # ------------------------------------------------------------ launcher

    def _load_launcher_path(self):
        # Vem do perfis.json; se vazio, tenta o config.json (versoes antigas).
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

    # ------------------------------------------------------------- login

    def _quick_start_account(self, account):
        # Duplo clique numa conta inicia o login so dela, na hora.
        profile = self._profile(account)
        if profile:
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
            "simultaneamente (uma por conta). Continuar?",
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
        self.render()

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
            # NAO tocar no Tk daqui (thread separada): so avisa por fila;
            # quem mexe na tela e o _poll_log_queue, na thread certa.
            self.finished_queue.put(account)

    def _stop_bot(self):
        if not self.running:
            return
        for info in self.running.values():
            info["stop_event"].set()
        self._log_direct(f"Parando {len(self.running)} conta(s)...")

    # --------------------------------------------------------------- cave

    def _pid_for_nick(self, nick):
        nick = (nick or "").strip().lower()
        if not nick:
            return None
        for pid, nome in self.cave_online or []:
            if nome and nome.lower() == nick:
                return pid
        return None

    def _cave_state_for(self, profile):
        """None se a deteccao ainda nao rodou, senao online/offline/entrando."""
        if self.cave_online is None:
            return None
        pid = self._pid_for_nick(profile.get("character_name"))
        if pid and pid in self.cave_runs:
            return "entrando"
        return "online" if pid else "offline"

    def _selected_cave_pid(self):
        p = self._profile(self.selected_account) if self.selected_account else None
        return self._pid_for_nick(p.get("character_name")) if p else None

    def _cave_status_text(self):
        if self.cave_online is None:
            return "procurando os jogos abertos..."
        cadastrados = {
            (q.get("character_name") or "").strip().lower()
            for q in profiles.list_profiles(profiles.load_profiles())
        }
        extras = [n for _, n in self.cave_online if n and n.lower() not in cadastrados]
        sem_resposta = sum(1 for _, n in self.cave_online if n is None)
        partes = []
        if extras:
            partes.append("online sem cadastro: " + ", ".join(extras))
        if sem_resposta:
            partes.append(f"{sem_resposta} jogo(s) sem resposta (fila/minimizado)")
        return "   ·   ".join(partes)

    def _cave_detect_tick(self):
        self._cave_detect()
        self.after(4000, self._cave_detect_tick)

    def _cave_detect(self):
        """Le o nick de cada jogo aberto (numa thread: conectar num jogo novo
        leva 0,5-2s) e manda o resultado pela fila."""
        if self._cave_detecting:
            return
        self._cave_detecting = True
        # Jogos tentando entrar na cave nao sao consultados: a deteccao
        # disputaria a conexao com as tentativas e atrasaria os pedidos.
        conhecidos = {pid: nome for pid, nome in (self.cave_online or []) if pid in self.cave_runs}

        def trabalho():
            import cave

            try:
                achados = cave.detectar_online(conhecidos)
            except Exception:  # noqa: BLE001
                bot.log.exception("Cave: erro ao procurar os jogos abertos.")
                achados = []
            self.cave_queue.put(("online", achados))

        threading.Thread(target=trabalho, daemon=True).start()

    def _toggle_cave(self):
        pid = self._selected_cave_pid()
        if not pid:
            return
        conta = self.selected_account
        run = self.cave_runs.get(pid)
        if run:
            run["stop_event"].set()
            self._log_direct(f"[{conta}] Cave: parando...")
            return
        sigla, nome, numero = self._caves[self.cave_choice]
        if not numero:
            return
        import cave

        cave.marcar_recente(sigla)  # sobe pro topo do pop-up de caves
        limite = float(bot.load_config().get("cave_limite_minutos", 10))
        _, intervalo, rajada = next(v for v in CAVE_VELOCIDADES if v[0] == self.speed_choice)
        stop_event = threading.Event()

        def trabalho():
            import cave

            try:
                cave.entrar(pid, numero, nome, stop_event, intervalo, limite, prefixo=conta, rajada=rajada)
            except Exception:  # noqa: BLE001
                bot.log.exception("Cave: erro inesperado.")
            finally:
                self.cave_queue.put(("fim", pid))

        thread = threading.Thread(target=trabalho, daemon=True)
        self.cave_runs[pid] = {
            "thread": thread, "stop_event": stop_event, "tipo": "entrar", "cave": sigla, "account": conta,
        }
        thread.start()
        self.render()

    def _poll_cave_queue(self):
        mudou = False
        try:
            while True:
                tipo, dado = self.cave_queue.get_nowait()
                if tipo == "online":
                    self._cave_detecting = False
                    if dado != self.cave_online:
                        self.cave_online = dado
                        mudou = True
                elif tipo == "fim":
                    self.cave_runs.pop(dado, None)
                    mudou = True
        except queue.Empty:
            pass
        if mudou:
            self.render()

    # ---------------------------------------------------------------- log

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

        # contas que terminaram (avisadas pelas threads via fila)
        finished = []
        try:
            while True:
                finished.append(self.finished_queue.get_nowait())
        except queue.Empty:
            pass
        for account in finished:
            self.running.pop(account, None)
        if finished:
            self.render()

        self._poll_cave_queue()
        self.after(200, self._poll_log_queue)

    def _append_log(self, level, line):
        tag = {"ERROR": "error", "CRITICAL": "error", "WARNING": "warning", "INFO": "info"}.get(level)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n", (tag,) if tag else ())
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
        # Cave: para as tentativas e desfaz a conexao com cada jogo, pra nao
        # deixar nada do bot rodando dentro deles depois de fechar.
        for info in self.cave_runs.values():
            info["stop_event"].set()
        for info in list(self.cave_runs.values()):
            info["thread"].join(timeout=3)
        try:
            import cliente_lua

            cliente_lua.desconectar_todos()
        except Exception:  # noqa: BLE001 - fechar o bot nunca pode travar aqui
            pass
        self.destroy()


def _rgba_hex(cor, alpha=1.0):
    r, g, b = skin.rgb(cor)
    return (r, g, b, int(255 * alpha))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
