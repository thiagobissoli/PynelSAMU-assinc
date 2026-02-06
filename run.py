import sys
import os
from app import create_app

# Forçar saída sem buffer para aparecer no terminal
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = create_app()

if __name__ == '__main__':
    # Verificar se está em modo produção via variável de ambiente
    env = os.getenv('FLASK_ENV', 'development')
    is_production = env == 'production'
    
    if is_production:
        print('Iniciando PynelSAMU em MODO PRODUÇÃO em http://0.0.0.0:5001 ...', flush=True)
        app.run(debug=False, host='0.0.0.0', port=5001)
    else:
        print('Iniciando PynelSAMU em MODO DESENVOLVIMENTO em http://127.0.0.1:5001 ...', flush=True)
        app.run(debug=True, host='0.0.0.0', port=5001)
