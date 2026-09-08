"""
Gerenciamento de perfis (varias contas, cada uma com seu servidor, nick e
senha). Fica tudo num perfis.json unico.

ONDE ESSE ARQUIVO MORA -- e o ponto importante:
    Ele NAO fica na pasta do bot. Fica em
    "Documentos/Bot Login - Talisman Online/perfis.json".

    O motivo e simples: assim voce pode mandar a pasta do bot (ou o .exe)
    pra qualquer pessoa sem mandar suas contas e senhas junto. O bot e o
    programa; as contas sao suas e ficam com voce.

    Se existir um perfis.json antigo na pasta do bot (de versoes anteriores),
    ele e MOVIDO pra la sozinho na primeira execucao.

A SENHA FICA EM TEXTO LEGIVEL nesse arquivo. Isso e uma escolha deliberada:
o usuario ve exatamente onde os dados dele estao e pode abrir, editar,
copiar ou apagar o arquivo na mao, sem depender de nada. O preco e que quem
tiver acesso ao ARQUIVO le as senhas -- por isso ele mora numa pasta sua, e
nao junto do programa que voce compartilha.

Formato de perfis.json:
{
  "profiles": [
    {"account": "conta1", "server_name": "Sky Ice (GSM&BI)",
     "character_name": "Fulano", "password": "senha1"}
  ],
  "game_path": "C:/Program Files (x86)/TalismanOnline - 3D"
}

Nao existe "conta ativa" -- quem escolhe quais contas logam e sempre o
usuario, marcando a caixinha de cada uma (ou "Iniciar todas") na interface.
"game_path" e a pasta onde o jogo esta instalado.

Versoes antigas guardavam a senha no cofre de credenciais do Windows (via
`keyring`). Na primeira execucao desta versao, essas senhas sao movidas
automaticamente pro perfis.json e as entradas antigas do cofre sao
apagadas, pra nao ficar copia sobrando espalhada pelo sistema.
"""

import json

from paths import BASE_DIR, USER_DATA_DIR, ensure_user_data_dir

PROFILES_PATH = USER_DATA_DIR / "perfis.json"
OLD_SINGLE_PROFILE_PATH = USER_DATA_DIR / "perfil.json"  # formato antigo (1 perfil so)

# Onde esses arquivos ficavam antes (junto do bot) -- so pra migrar
LEGACY_PROFILES_PATH = BASE_DIR / "perfis.json"
LEGACY_SINGLE_PROFILE_PATH = BASE_DIR / "perfil.json"

KEYRING_SERVICE = "talisman_online_bot"


_KEYRING_MIGRATION_DONE = False
_LOCATION_MIGRATION_DONE = False


def _migrate_from_bot_folder():
    """Move o perfis.json que ficava na pasta do bot pra pasta do usuario,
    em Documentos. Roda uma vez por execucao e so faz alguma coisa se
    realmente existir um arquivo antigo pra mover.

    Move (nao copia) de proposito: se ficasse uma copia na pasta do bot,
    ela iria junto quando voce compartilhasse o bot -- que e exatamente o
    que essa mudanca veio evitar."""
    global _LOCATION_MIGRATION_DONE
    if _LOCATION_MIGRATION_DONE:
        return
    _LOCATION_MIGRATION_DONE = True

    pares = [
        (LEGACY_PROFILES_PATH, PROFILES_PATH),
        (LEGACY_SINGLE_PROFILE_PATH, OLD_SINGLE_PROFILE_PATH),
    ]
    for antigo, novo in pares:
        try:
            if antigo == novo or not antigo.exists() or novo.exists():
                continue
            ensure_user_data_dir()
            antigo.replace(novo)
        except OSError:
            # sem permissao pra mover? tenta ao menos copiar o conteudo,
            # pra o usuario nao perder o cadastro
            try:
                novo.write_text(antigo.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass


def _empty():
    return {"profiles": [], "game_path": ""}


def _migrate_passwords_from_keyring(data):
    """Traz pro perfis.json as senhas que ficaram no cofre do Windows das
    versoes antigas, e APAGA a entrada antiga do cofre depois de copiar --
    assim a senha nao fica guardada em dois lugares.

    Roda no maximo uma vez por execucao do programa, e so mexe no arquivo
    se realmente tiver achado alguma senha pra trazer. Se o keyring nao
    estiver instalado (ou der qualquer erro), simplesmente nao faz nada:
    contas novas ja nascem com a senha no arquivo mesmo."""
    global _KEYRING_MIGRATION_DONE
    if _KEYRING_MIGRATION_DONE:
        return False
    _KEYRING_MIGRATION_DONE = True

    pending = [p for p in data.get("profiles", []) if p.get("account") and not p.get("password")]
    if not pending:
        return False

    try:
        import keyring
    except Exception:  # noqa: BLE001 - sem keyring nao ha o que migrar
        return False

    changed = False
    for profile in pending:
        account = profile["account"]
        try:
            password = keyring.get_password(KEYRING_SERVICE, account)
        except Exception:  # noqa: BLE001
            password = None
        if not password:
            continue
        profile["password"] = password
        changed = True
        try:
            keyring.delete_password(KEYRING_SERVICE, account)
        except Exception:  # noqa: BLE001 - se nao der pra apagar, tudo bem: a copia boa ja esta no arquivo
            pass
    return changed


def load_profiles():
    """Le perfis.json. Se nao existir mas o perfil.json antigo (de 1 conta
    so) existir, migra automaticamente pro novo formato. Tambem traz pro
    arquivo, na primeira vez, as senhas que estavam no cofre do Windows."""
    _migrate_from_bot_folder()

    if PROFILES_PATH.exists():
        try:
            with open(PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = _empty()
        data.setdefault("profiles", [])
        data.setdefault("game_path", "")
        if _migrate_passwords_from_keyring(data):
            save_profiles(data)
        return data

    if OLD_SINGLE_PROFILE_PATH.exists():
        try:
            with open(OLD_SINGLE_PROFILE_PATH, "r", encoding="utf-8") as f:
                old = json.load(f)
        except (json.JSONDecodeError, OSError):
            old = {}
        data = _empty()
        if old.get("account"):
            data["profiles"] = [old]
        save_profiles(data)
        return data

    return _empty()


def save_profiles(data):
    ensure_user_data_dir()
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_profiles(data=None):
    data = data if data is not None else load_profiles()
    return data.get("profiles", [])


def get_default_profile(data=None):
    """Nao existe "conta ativa": isso so serve de fallback pra quando o bot
    roda SEM interface grafica (`--nogui`/`--headless`) e ninguem escolheu
    uma conta explicitamente -- nesse caso, usa o primeiro perfil
    cadastrado. Retorna {} se nao tiver nenhum perfil."""
    data = data if data is not None else load_profiles()
    profiles = data.get("profiles", [])
    return profiles[0] if profiles else {}


def upsert_profile(data, account, server_name, character_name):
    """Adiciona ou atualiza (por conta) um perfil na lista. NAO mexe na
    senha ja salva -- editar servidor/personagem de uma conta existente
    preserva a senha dela (isso e feito separadamente por set_password)."""
    profiles = data.setdefault("profiles", [])
    entry = {
        "account": account,
        "server_name": server_name,
        "character_name": character_name,
    }
    for i, p in enumerate(profiles):
        if p.get("account") == account:
            entry["password"] = p.get("password", "")  # preserva a senha existente
            profiles[i] = entry
            break
    else:
        entry["password"] = ""
        profiles.append(entry)
    return data


def remove_profile(data, account):
    data["profiles"] = [p for p in data.get("profiles", []) if p.get("account") != account]
    # limpa tambem qualquer sobra no cofre do Windows de versoes antigas,
    # pra remover a conta nao deixar rastro em lugar nenhum
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, account)
    except Exception:  # noqa: BLE001 - normal: quase sempre nao existe entrada la
        pass
    return data


def get_game_path():
    """Pasta (ou executavel) do jogo, configurada pela interface. Fica aqui
    no perfis.json -- e nao no config.json -- porque o config.json viaja
    DENTRO do .exe e e so leitura; este arquivo e o unico que o usuario
    edita/possui de verdade."""
    return (load_profiles().get("game_path") or "").strip()


def set_game_path(path):
    data = load_profiles()
    data["game_path"] = (path or "").strip()
    save_profiles(data)


def set_password(account, password):
    """Grava a senha da conta no perfis.json, na pasta do bot. Fica em
    texto legivel -- veja o aviso no topo deste arquivo."""
    if not account:
        return
    data = load_profiles()
    for p in data.setdefault("profiles", []):
        if p.get("account") == account:
            p["password"] = password
            break
    else:
        data["profiles"].append(
            {
                "account": account,
                "server_name": "",
                "character_name": "",
                "password": password,
            }
        )
    save_profiles(data)


def get_password(account):
    """Le a senha do perfis.json. Se a conta ainda nao tiver senha no
    arquivo, tenta o cofre do Windows (caso de quem esta vindo de uma
    versao antiga e a migracao automatica nao rodou por algum motivo)."""
    if not account:
        return None

    for p in list_profiles():
        if p.get("account") == account:
            if p.get("password"):
                return p["password"]
            break

    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, account)
    except Exception:  # noqa: BLE001
        return None
