# PynelSAMU - Script de inicialização para Windows
# Execute este script na pasta do projeto (clique com botão direito > Executar com PowerShell)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=== PynelSAMU - Iniciando ===" -ForegroundColor Cyan

# Verificar se Python está instalado
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERRO: Python nao encontrado. Instale em https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "Marque a opcao 'Add Python to PATH' durante a instalacao." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Criar ambiente virtual se não existir
if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual..." -ForegroundColor Yellow
    python -m venv .venv
    Write-Host "Ambiente virtual criado." -ForegroundColor Green
}

# Ativar ambiente virtual
Write-Host "Ativando ambiente virtual..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"

# Instalar dependências se necessário
$pipList = pip list 2>&1
if ($pipList -notmatch "Flask") {
    Write-Host "Instalando dependencias (pode demorar alguns minutos)..." -ForegroundColor Yellow
    pip install -r requirements.txt
    Write-Host "Dependencias instaladas." -ForegroundColor Green
}

# Verificar se .env existe
if (-not (Test-Path ".env")) {
    if (Test-Path "env.example") {
        Write-Host "Copiando env.example para .env..." -ForegroundColor Yellow
        Copy-Item "env.example" ".env"
        Write-Host "Arquivo .env criado. Edite-o e configure SAMU_USERNAME e SAMU_PASSWORD." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Iniciando PynelSAMU em http://localhost:5001 ..." -ForegroundColor Green
Write-Host "Pressione Ctrl+C para encerrar." -ForegroundColor Gray
Write-Host ""

python run.py
