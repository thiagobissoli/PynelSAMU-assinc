# Sistema Flask Básico

Sistema básico em Flask com Bootstrap, SQLite e suporte a variáveis de ambiente (.env).

## Características

- ✅ Flask 3.0
- ✅ SQLite com SQLAlchemy
- ✅ Bootstrap 5.3.2
- ✅ Variáveis de ambiente (.env)
- ✅ CRUD completo (Create, Read, Update, Delete)
- ✅ Interface responsiva

## Instalação

### Windows (modo fácil)
1. Instale o [Python](https://www.python.org/downloads/) (marque "Add Python to PATH")
2. Instale o [Google Chrome](https://www.google.com/chrome/)
3. Copie `env.example` para `.env` e configure `SAMU_USERNAME` e `SAMU_PASSWORD`
4. Clique com o botão direito em `INICIAR_WINDOWS.ps1` → **Executar com PowerShell**

📖 **Guia completo para iniciantes:** veja [PASSO_A_PASSO_WINDOWS.md](PASSO_A_PASSO_WINDOWS.md)

### Linux/Mac ou instalação manual

1. Clone o repositório ou navegue até a pasta do projeto

2. Crie um ambiente virtual:
```bash
python3 -m venv .venv
```

3. Ative o ambiente virtual:
```bash
# Linux/Mac
source .venv/bin/activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

4. Instale as dependências:
```bash
pip install -r requirements.txt
```

5. Configure o arquivo `.env`:
```bash
cp env.example .env
```

Edite o arquivo `.env` e configure:
- `SECRET_KEY`: Chave secreta para produção
- `SAMU_USERNAME`: Usuário do sistema SAMU
- `SAMU_PASSWORD`: Senha do sistema SAMU
- `SELENIUM_HEADLESS`: `true` para modo headless, `false` para ver o navegador

## Executando o Sistema

```bash
python run.py
```

O sistema estará disponível em: `http://localhost:5001`

### Scripts de atalho
- **Windows:** `INICIAR_WINDOWS.ps1` (inicia) | `restart.ps1` (reinicia)
- **Linux/Mac:** `./restart.sh` (reinicia)

## Estrutura do Projeto

```
PynelSAMU/
├── app/
│   ├── __init__.py          # Inicialização do Flask
│   ├── config.py            # Configurações
│   ├── models.py            # Modelos SQLAlchemy
│   ├── routes.py            # Rotas CRUD básico
│   ├── routes_download.py   # Rotas de download e indicadores
│   ├── utils.py             # Utilitários gerais
│   ├── download_utils.py    # Utilitários de download
│   ├── selenium_utils.py    # Automação Selenium
│   ├── indicadores.py       # Geração de indicadores
│   └── templates/           # Templates HTML
│       ├── base.html
│       ├── index.html
│       ├── create.html
│       ├── edit.html
│       └── download/
│           ├── index.html
│           ├── indicadores.html
│           └── dados.html
├── download/                # Diretório de arquivos baixados
├── run.py                   # Arquivo principal
├── requirements.txt         # Dependências
├── env.example              # Exemplo de variáveis de ambiente
└── README.md
```

## Funcionalidades

### CRUD Básico
- **Listagem**: Visualize todos os itens cadastrados
- **Criação**: Adicione novos itens ao sistema
- **Edição**: Atualize informações dos itens existentes
- **Exclusão**: Remova itens do sistema

### Sistema de Download e Indicadores
- **Download Automatizado**: Robô que acessa o sistema SAMU e baixa arquivos Excel
- **Processamento**: Converte arquivos .xls para .xlsx automaticamente
- **Indicadores**: Gera indicadores estatísticos a partir dos dados baixados
- **Visualização**: Interface web para visualizar dados e indicadores
- **Histórico**: Suporte para download de dados históricos (8 dias)

## Banco de Dados

O banco de dados SQLite será criado automaticamente na primeira execução. O arquivo `app.db` será gerado na pasta `instance/`.

## Sistema de Download

### Como Usar

1. Configure as credenciais no arquivo `.env`:
   - `SAMU_USERNAME`: Seu usuário
   - `SAMU_PASSWORD`: Sua senha

2. Acesse a página de Download:
   - Navegue para `/download` no navegador
   - Ou clique em "Download" no menu principal

3. Execute o Download:
   - Escolha o número de dias atrás ou informe datas específicas
   - Clique em "Executar Download"
   - Aguarde o processo concluir (pode levar alguns minutos)

4. Visualize os Dados:
   - Após o download, você pode ver os dados em formato de tabela
   - Ou visualizar os indicadores gerados automaticamente

### Modo Headless

Por padrão, o Selenium roda em modo headless (sem interface gráfica). Para ver o navegador durante o download, configure:
```
SELENIUM_HEADLESS=false
```

### Arquivos Gerados

- `download/convertido_tabela.xlsx`: Dados do último download
- `download/historico.xlsx`: Dados históricos (quando aplicável)

## Desenvolvimento

Para desenvolvimento, certifique-se de que `FLASK_ENV=development` está configurado no arquivo `.env`.

## Licença

Este é um projeto básico para uso como base de desenvolvimento.
