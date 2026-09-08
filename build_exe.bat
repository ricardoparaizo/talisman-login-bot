@echo off
setlocal

echo ================================================================
echo  Gerando TalismanLoginBot.exe localmente (a partir deste codigo)
echo ================================================================
echo.
echo Isso precisa de Python instalado so AGORA, pra gerar o .exe.
echo Depois de gerado, o .exe roda em qualquer PC sem precisar de Python.
echo.

echo === Verificando o Python ===
python --version
if errorlevel 1 (
    echo.
    echo Nao encontrei o comando 'python'. Confirme que o Python esta
    echo instalado e marcado como "Add python.exe to PATH" na instalacao
    echo ^(ou abra um terminal novo, se acabou de instalar^).
    goto :erro
)

echo.
echo === Instalando dependencias ^(via "python -m pip", mais confiavel que so "pip"^) ===
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :erro

python -m pip install pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :erro

echo.
echo === Empacotando em UM arquivo so ===
echo.
echo  Os templates das telas do jogo e o config.json vao DENTRO do .exe.
echo  Assim nao sobra pasta "_internal" nem "templates" pra alguem apagar
echo  ou editar sem querer e desconfigurar o bot.
echo.
echo  E suas contas ficam em "Documentos\Bot Login - Talisman Online",
echo  fora da pasta do bot -- entao da pra compartilhar o .exe sem elas.
echo.

python -m PyInstaller --onefile --noupx --windowed --noconfirm --name TalismanLoginBot ^
    --icon=icon.ico ^
    --version-file=version_info.txt ^
    --add-data "templates;templates" ^
    --add-data "config.json;." ^
    --add-data "icon.png;." ^
    --add-data "icon.ico;." ^
    --collect-submodules keyring ^
    --hidden-import keyring.backends.Windows ^
    bot.py
if errorlevel 1 goto :erro

echo.
echo  Obs: o perfis.json (suas contas) NAO e copiado pra pasta dist de
echo  proposito -- ele mora em "Documentos\Bot Login - Talisman Online" e o
echo  bot acha ele sozinho de la.

echo.
echo ================================================================
echo  AVISO SOBRE ANTIVIRUS ^(leia se aparecer alerta^)
echo ================================================================
echo.
echo  E normal alguns antivirus reclamarem deste .exe. O motivo nao e o
echo  codigo do bot: e o PyInstaller. O "miolo" que ele coloca em todo
echo  .exe gerado e igual em todos os programas feitos com ele -- inclusive
echo  nos maus -- entao os antivirus que usam IA marcam por semelhanca.
echo  Some a isso um arquivo sem assinatura digital e sem reputacao ainda.
echo.
echo  ATENCAO: o modo "arquivo unico" costuma ser MAIS marcado que o modo
echo  pasta, porque o .exe se descompacta sozinho numa pasta temporaria --
echo  comportamento que os antivirus acham suspeito. Se as reclamacoes
echo  aumentarem, troque "--onefile" por "--onedir" na linha do PyInstaller
echo  aqui em cima ^^(volta a ter a pasta _internal^^).
echo.
echo  O que ajuda de verdade, em ordem:
echo    1^) Reportar como falso positivo pra Microsoft ^(leva alguns dias e
echo       resolve pro Defender, que e o que a maioria das pessoas usa^):
echo       https://www.microsoft.com/en-us/wdsi/filesubmission
echo    2^) Passar a pasta do CODIGO em vez do .exe pra quem for usar, e a
echo       pessoa rodar este build_exe.bat na maquina dela ^(ou rodar direto
echo       com "python bot.py"^) -- ai nao ha .exe estranho nenhum.
echo    3^) Assinatura digital paga, se um dia valer a pena.
echo.
echo ================================================================
echo  Pronto! O executavel esta em:
echo  dist\TalismanLoginBot.exe
echo.
echo  Da duplo clique nele -- abre a interface grafica, onde voce
echo  cadastra suas contas (conta/senha/servidor/personagem) e clica
echo  em "Iniciar bot".
echo.
echo  E um arquivo unico -- da pra levar sozinho pra onde quiser.
echo.
echo  Pode compartilhar esse .exe a vontade: suas contas e senhas NAO estao
echo  dentro dele. Elas ficam na sua pasta Documentos, em
echo  "Documentos\Bot Login - Talisman Online\perfis.json" -- e o bot cria
echo  esse arquivo do zero na maquina de quem receber.
echo ================================================================
goto :fim

:erro
echo.
echo Algo deu errado no passo acima. Veja a mensagem de erro em vermelho
echo mais pra cima e me manda que eu ajudo a resolver.

:fim
pause
