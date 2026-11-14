@echo off
setlocal

echo ================================================================
echo  Gerando o BeastBot.exe (a partir deste codigo)
echo ================================================================
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
echo === Instalando dependencias ===
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :erro

python -m pip install pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto :erro

echo.
echo === Empacotando em UM arquivo so ===
echo.
echo  Os templates das telas do jogo, o visual e o config.json vao DENTRO
echo  do .exe. Suas contas NAO: elas ficam em "Documentos\BeastBot".
echo.

python -m PyInstaller --onefile --noupx --windowed --noconfirm --name BeastBot ^
    --icon=icon.ico ^
    --version-file=version_info.txt ^
    --add-data "templates;templates" ^
    --add-data "assets;assets" ^
    --add-data "config.json;." ^
    --add-data "icon.png;." ^
    --add-data "icon.ico;." ^
    --collect-submodules keyring ^
    --hidden-import keyring.backends.Windows ^
    bot.py
if errorlevel 1 goto :erro

echo.
echo ================================================================
echo  Pronto! O executavel esta em:
echo  dist\BeastBot.exe
echo.
echo  Se o antivirus reclamar: e falso positivo comum de programas
echo  gerados pelo PyInstaller (o .exe nao tem assinatura digital).
echo ================================================================
goto :fim

:erro
echo.
echo Algo deu errado no passo acima. Veja a mensagem de erro mais
echo pra cima.

:fim
pause
