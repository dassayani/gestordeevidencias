@echo off
rem Roda a suite inteira e abre o relatorio no navegador.
rem   executar.bat                 -> tudo
rem   executar.bat documentos      -> so a suite de documentos
rem   executar.bat -i regressao    -> so os casos marcados como regressao
setlocal
cd /d "%~dp0.."

rem Sem isto o console em cp1252 quebra ao imprimir mensagem com acento, e o
rem proprio Robot estoura ao formatar o erro.
set PYTHONIOENCODING=utf-8
set PYTHON=venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo Nao encontrei o venv em %CD%\venv
    exit /b 1
)

set ALVO=tests\suites
if not "%~1"=="" if not "%~1"=="-i" set ALVO=tests\suites\%~1.robot & shift

"%PYTHON%" -m robot --outputdir tests\_saida\relatorio ^
    --name "Gestor de Evidencias" ^
    --log log.html --report report.html ^
    %* "%ALVO%"

set CODIGO=%ERRORLEVEL%
echo.
echo Relatorio: %CD%\tests\_saida\relatorio\report.html
if exist tests\_saida\relatorio\report.html start "" tests\_saida\relatorio\report.html
exit /b %CODIGO%
