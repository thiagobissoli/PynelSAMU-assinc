#!/bin/bash
# Reinicia o PynelSAMU e exibe logs em tempo real

cd "$(dirname "$0")"

echo "Encerrando processo na porta 5001..."
lsof -ti:5001 | xargs kill -9 2>/dev/null || true
sleep 2

echo "Iniciando PynelSAMU..."
source .venv/bin/activate
exec python3 run.py
