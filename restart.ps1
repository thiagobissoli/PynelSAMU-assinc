# PynelSAMU - Reinicia o programa (Windows)
# Encerra o processo na porta 5001 e inicia novamente

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Encerrando processo na porta 5001..." -ForegroundColor Yellow
try {
    $conn = Get-NetTCPConnection -LocalPort 5001 -ErrorAction SilentlyContinue
    if ($conn) {
        $conn | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }
} catch {
    # Fallback: tenta via netstat se Get-NetTCPConnection falhar
    $netstat = netstat -ano 2>$null | Select-String ":5001"
    if ($netstat) {
        $netstat | ForEach-Object {
            $pid = ($_ -split '\s+')[-1]
            if ($pid -match '^\d+$') { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue }
        }
        Start-Sleep -Seconds 2
    }
}

Write-Host "Iniciando PynelSAMU..." -ForegroundColor Green
& ".\.venv\Scripts\Activate.ps1"
python run.py
