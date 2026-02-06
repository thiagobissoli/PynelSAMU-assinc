@echo off
REM Configurar política de execução do PowerShell
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"

REM Ativar ambiente virtual
call "%~dp0venv\Scripts\activate.bat"

REM Definir modo produção
set FLASK_ENV=production

REM Mensagem de inicialização
echo ========================================
echo  PynelSAMU - MODO PRODUCAO
echo ========================================
echo.
echo Iniciando servidor Flask em modo producao...
echo.

REM Executar Flask via run.py
python run.py
