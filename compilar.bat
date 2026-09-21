@echo off
setlocal
title Compilador do Gestor de Evidencias
cd /d "%~dp0"

set "PYTHON=venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo.
    echo  ERRO: ambiente virtual nao encontrado em "%CD%\venv".
    echo  Crie o ambiente e instale as dependencias antes de compilar:
    echo.
    echo      py -m venv venv
    echo      venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem O comtypes gera o modulo de UI Automation na primeira vez que e usado, e
rem o PyInstaller so consegue embutir o que ja existe. Gerando aqui, a
rem deteccao por acessibilidade (a que enxerga dentro de navegador e Electron)
rem entra no pacote mesmo numa maquina onde o app nunca rodou.
echo Preparando modulos de UI Automation...
"%PYTHON%" -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"
if errorlevel 1 (
    echo.
    echo  AVISO: nao foi possivel gerar o modulo de UI Automation.
    echo  O app funciona, mas a sugestao de area perde a leitura por acessibilidade.
    echo.
)

echo =====================================================
echo    Limpando pastas temporarias e versoes antigas...
echo =====================================================
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo =====================================================
echo    Iniciando compilacao (PyInstaller)...
echo =====================================================
echo Isso pode levar alguns minutos dependendo do PC.
echo.

rem --onedir, e nao --onefile: o arquivo unico descompacta o bundle inteiro no
rem TEMP a cada execucao, o que custava cerca de 30 segundos para abrir e ainda
rem deixava pastas _MEI orfas quando o processo era encerrado. Em pasta, o app
rem abre direto. Para distribuir, compacte a pasta dist\GestorEvidencias.
rem
rem O PyInstaller e chamado pelo Python da venv, e nao pelo do PATH: e o que
rem garante que o executavel saia com as versoes fixadas em requirements.txt.
rem
rem numpy entra pelo hook padrao (sem --collect-all), que nao arrasta os ~10 MB
rem de testes do pacote. pythonwin nao e usado pelo app e fica de fora.
"%PYTHON%" -m PyInstaller --noconfirm --onedir --windowed ^
 --collect-all pystray ^
 --collect-all PIL ^
 --collect-all tkinterdnd2 ^
 --collect-all docx ^
 --collect-all emoji ^
 --collect-all comtypes ^
 --hidden-import "win32clipboard" ^
 --hidden-import "win32gui" ^
 --hidden-import "win32con" ^
 --hidden-import "win32ui" ^
 --hidden-import "win32api" ^
 --hidden-import "screeninfo" ^
 --hidden-import "win32com.client" ^
 --hidden-import "numpy" ^
 --exclude-module "pywin" ^
 --exclude-module "pythonwin" ^
 --exclude-module "numpy.f2py" ^
 --exclude-module "pytest" ^
 --exclude-module "setuptools" ^
 --add-data "icon.ico;." ^
 --icon="icon.ico" ^
 --name "GestorEvidencias" ^
 main.py

if errorlevel 1 (
    echo.
    echo  A compilacao FALHOU. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo    CONCLUIDO
echo    O aplicativo esta em: %CD%\dist\GestorEvidencias\
echo    Execute por: dist\GestorEvidencias\GestorEvidencias.exe
echo =====================================================
pause
