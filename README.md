# BeastBot — Talisman Online

Bot de uso pessoal para tirar as filas do Talisman Online do caminho:

- **Login automático**: digita conta e senha, escolhe servidor e personagem, espera a fila de login e reconecta quando a conexão cai. Várias contas ao mesmo tempo, cada uma na sua cópia do jogo.
- **Entrar na cave**: com o personagem perto do NPC da cave, o bot conversa com o NPC e repete o pedido de entrada até pegar vaga, sem você ficar clicando.

Ele **não joga por você** — não anda, não farma, não luta.

## Como funciona

**Login** — o bot olha a janela do jogo, reconhece em que tela está comparando com imagens de referência (`templates/`) e clica no lugar certo. O clique vai direto pra janela pelo Windows, sem mover o mouse, então dá pra usar o PC normalmente. A janela do jogo não pode ficar minimizada (pode ficar atrás de outras). Na tela de fila ele só espera.

**Cave** — o bot roda trechos de Lua dentro da interface do próprio jogo (`cliente_lua.py`):

1. Abre o diálogo do NPC da cave (o servidor só aceita o pedido de entrar de quem conversou com o NPC).
2. Manda o pedido de entrar (`RequestIntoEctype`), 1 a cada 200 ms, de dentro do laço principal do jogo.
3. Para quando o personagem muda de mapa (entrou), morre, passa do tempo limite (`cave_limite_minutos` no `config.json`) ou quando você clica em Parar.

Antes de mexer na memória do jogo, o bot confere byte a byte que a versão do `client.exe` é a que ele conhece; se for outra, ele não injeta nada. Ao parar, tudo o que foi mudado no jogo é desfeito.

## Rodando

Precisa de [Python 3.9+](https://www.python.org/downloads/) no Windows, com **"Add python.exe to PATH"** marcado.

```
pip install -r requirements.txt
python bot.py
```

Ou rode o `build_exe.bat` para gerar `dist\BeastBot.exe`, um arquivo único que roda sem Python.

Use **uma cópia do bot por vez**: duas cópias conectadas no mesmo jogo brigam pelo mesmo gancho.

## Usando

**Contas**

1. Clique em **+ Nova conta** e preencha login, senha, servidor e nick.
2. Em **Pasta do jogo**, aponte a pasta do Talisman (a que tem o `game.exe`) para o bot abrir o jogo sozinho.
3. Selecione a conta na lista e clique em **Iniciar Login**. Botão direito numa conta edita ou remove.

**Entrar Cave**

1. Deixe o personagem logado e perto do NPC da cave.
2. Selecione a conta (a lista mostra quais estão online), escolha a cave e clique em **Entrar**.

## Onde ficam os dados

Em `Documentos\BeastBot\`, fora da pasta do bot: contas (`perfis.json`), log (`bot.log`) e as caves usadas por último. Se existir a pasta antiga (`Documentos\Bot Login - Talisman Online`), o bot a renomeia sozinho na primeira abertura.

> ⚠️ As senhas ficam legíveis no `perfis.json`. Cuidado com backup automático da pasta Documentos em nuvem.

O bot não faz nenhuma conexão de rede própria.

## Se alguma tela de login não for reconhecida

A interface do Talisman é desenhada em tamanho fixo (em pixels), então os templates valem em qualquer resolução do jogo. Se o jogo mudar o visual de alguma tela, o log avisa que não reconheceu; tire um print da janela, recorte o pedaço equivalente e substitua o arquivo em `templates/` (o `config.json` lista o que cada um representa).

## Arquivos

| Arquivo | O que faz |
|---|---|
| `bot.py` | Login: reconhece as telas e decide o que clicar |
| `gui.py`, `ui_kit.py`, `skin.py` | Interface (canvas com vidro, no estilo Apple) |
| `cave.py` | Entrar na cave |
| `cliente_lua.py` | Roda Lua dentro do jogo (gancho no `uiGetglobal` e gancho por quadro) |
| `profiles.py` | Contas, salvas em Documentos |
| `win_input.py` | Clique e digitação em segundo plano, via Windows |
| `screen_match.py` | Comparação de imagem |
| `paths.py` | Onde cada coisa mora (programa × usuário) |
| `config.json` | Ajustes finos e lista de templates |
| `templates/` | Recortes das telas do jogo |
| `build_exe.bat` | Gera o `.exe` |
