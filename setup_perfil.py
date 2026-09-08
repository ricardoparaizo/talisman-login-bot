"""
Configura um perfil (conta, servidor, personagem) por texto, sem abrir a
interface grafica -- util pra automacao/testes, ou se preferir so terminal.
Pra gerenciar varias contas com mais conforto, use a interface grafica
(rode "python bot.py" sem argumentos, ou de le TalismanLoginBot.exe).

Onde ficam os dados: tudo (conta, servidor, nick e SENHA) e gravado no
perfis.json, dentro de "Documentos/Bot Login - Talisman Online" -- FORA da
pasta do bot, pra voce poder compartilhar o bot sem mandar suas contas
junto. Nada e enviado pra internet.

A senha fica em TEXTO LEGIVEL nesse arquivo, de proposito: voce abre e ve
exatamente o que esta salvo. Em compensacao, quem tiver acesso ao arquivo
le as senhas -- entao nao mande o perfis.json pra ninguem e tome cuidado
com backup automatico da pasta Documentos em nuvem.

Rode isso uma vez (ou de novo, se quiser atualizar os dados):

    python bot.py --setup
    (ou, se ja tiver empacotado em .exe: TalismanLoginBot.exe --setup)
    (ou ainda, direto: python setup_perfil.py)
"""

import getpass

import profiles


def main():
    print("=== Configuracao de perfil do bot (Talisman Online) ===")
    print("(deixe em branco e aperte Enter para nao alterar um campo existente)\n")

    data = profiles.load_profiles()
    existentes = profiles.list_profiles(data)
    if existentes:
        print("Contas ja cadastradas:", ", ".join(p["account"] for p in existentes))
        print("(digite uma conta existente pra editar, ou uma nova pra cadastrar)\n")

    account = input("Conta/usuario: ").strip()
    if not account:
        print("\nConta em branco -- cancelando. Nada foi salvo.")
        return

    existing = next((p for p in existentes if p.get("account") == account), {})

    server_name = input(
        f"Nome do servidor (exatamente como aparece na lista) [{existing.get('server_name', '')}]: "
    ).strip() or existing.get("server_name", "")
    character_name = input(
        f"Nome do personagem [{existing.get('character_name', '')}]: "
    ).strip() or existing.get("character_name", "")

    password = getpass.getpass("Senha (nao aparece na tela enquanto digita, Enter p/ manter a atual): ")

    if password:
        profiles.set_password(account, password)
        print("Senha salva no cofre de credenciais do Windows (nao fica em nenhum arquivo texto).")
    elif not profiles.get_password(account):
        print("\nAviso: nenhuma senha foi definida para essa conta ainda.")

    data = profiles.upsert_profile(data, account, server_name, character_name)
    profiles.save_profiles(data)

    print(f"\nPerfil salvo em {profiles.PROFILES_PATH.name}:")
    print(f"  conta: {account}")
    print(f"  servidor: {server_name}")
    print(f"  personagem: {character_name}")
    print(
        "\nLembre-se: se o nome do servidor/personagem tiver que ser 'clicado' numa "
        "lista, ainda e necessario capturar o template de imagem correspondente em "
        "templates/ (veja o README.md, secao 'selecionando servidor e personagem')."
    )


if __name__ == "__main__":
    main()
