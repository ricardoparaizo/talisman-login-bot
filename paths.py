"""
Onde cada coisa mora. Sao TRES lugares diferentes, de proposito:

    RESOURCE_DIR -- coisas do PROGRAMA (so leitura): templates das telas do
                    jogo, config.json, icones. Quando empacotado em .exe
                    unico, isso viaja dentro do proprio executavel e e
                    extraido numa pasta temporaria pelo Windows -- ninguem
                    apaga nem edita sem querer.

    USER_DATA_DIR -- coisas do USUARIO (leitura e escrita): perfis.json com
                    as contas e senhas, e o bot.log. Fica em
                    "Documentos/Bot Login - Talisman Online", FORA da pasta
                    do bot. Assim da pra mandar o bot inteiro pra outra
                    pessoa sem mandar suas contas junto.

    BASE_DIR     -- a pasta onde o bot esta (o .exe ou o codigo). Usada so
                    pra achar o PARAR.txt e pra migrar arquivos antigos.

Funciona tanto rodando como script Python quanto empacotado com o
PyInstaller (build_exe.bat) -- quando "congelado", `__file__` nao se
comporta normalmente, entao usamos a pasta do proprio .exe.
"""

import sys
from pathlib import Path

APP_FOLDER_NAME = "Bot Login - Talisman Online"

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))


def _documents_dir():
    """Acha a pasta Documentos de verdade do usuario.

    No Windows, "Documentos" nem sempre e C:/Users/Fulano/Documents -- quem
    usa OneDrive tem ela redirecionada, e em Windows em portugues o nome da
    pasta pode aparecer traduzido. Por isso perguntamos pro proprio Windows
    (SHGetKnownFolderPath) em vez de chutar o caminho. Se qualquer coisa
    der errado, caimos nos palpites tradicionais.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import windll, wintypes
            from uuid import UUID

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

                def __init__(self, uuid_str):
                    super().__init__()
                    u = UUID(uuid_str)
                    self.Data1, self.Data2, self.Data3 = u.fields[0], u.fields[1], u.fields[2]
                    for i, b in enumerate(u.bytes[8:]):
                        self.Data4[i] = b

            FOLDERID_Documents = GUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")
            ptr = ctypes.c_wchar_p()
            resultado = windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(FOLDERID_Documents), 0, None, ctypes.byref(ptr)
            )
            if resultado == 0 and ptr.value:
                caminho = Path(ptr.value)
                windll.ole32.CoTaskMemFree(ptr)
                if caminho.is_dir():
                    return caminho
        except Exception:  # noqa: BLE001 - se falhar, usa os palpites abaixo
            pass

    for nome in ("Documents", "Documentos"):
        candidato = Path.home() / nome
        if candidato.is_dir():
            return candidato
    return Path.home()


USER_DATA_DIR = _documents_dir() / APP_FOLDER_NAME


def ensure_user_data_dir():
    """Cria a pasta de dados do usuario se ainda nao existir. Se nao der
    (permissao, disco cheio), volta pra pasta do bot -- e melhor salvar num
    lugar menos ideal do que perder o cadastro do usuario."""
    global USER_DATA_DIR
    try:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        USER_DATA_DIR = BASE_DIR
    return USER_DATA_DIR
