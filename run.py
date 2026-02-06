import sys
from app import create_app

# Forçar saída sem buffer para aparecer no terminal
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = create_app()

if __name__ == '__main__':
    print('Iniciando PynelSAMU em http://127.0.0.1:5001 ...', flush=True)
    app.run(debug=True, host='0.0.0.0', port=5001)
