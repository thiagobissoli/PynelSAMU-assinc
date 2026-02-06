import os
import logging
from dotenv import load_dotenv

load_dotenv()
_log = logging.getLogger(__name__)

# Diretório do projeto (pai de app/) — garante DB sempre no mesmo lugar, com caminho absoluto
_basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_instance_dir = os.path.join(_basedir, 'instance')
os.makedirs(_instance_dir, exist_ok=True)
_default_db_path = os.path.join(_instance_dir, 'app.db')
_default_db_uri = 'sqlite:///' + _default_db_path.replace('\\', '/')

# Fallback se a pasta do projeto for só leitura (ex.: iCloud)
_fallback_db_dir = os.path.join(os.path.expanduser('~'), '.pynel_samu')
_fallback_db_path = os.path.join(_fallback_db_dir, 'app.db')
_fallback_db_uri = 'sqlite:///' + _fallback_db_path.replace('\\', '/')


def _resolve_sqlite_uri(uri):
    """Garante que URIs sqlite com caminho relativo usem diretório absoluto."""
    if not uri or not str(uri).strip().lower().startswith('sqlite:///'):
        return uri
    path = uri[10:].strip()
    if not path or os.path.isabs(path):
        return uri
    abs_path = os.path.join(_instance_dir, os.path.basename(path) or 'app.db')
    return 'sqlite:///' + abs_path.replace('\\', '/')


def _uri_to_path(uri):
    """Extrai caminho absoluto do arquivo a partir da URI sqlite."""
    if not uri or not str(uri).strip().lower().startswith('sqlite:///'):
        return None
    path = uri[10:].strip()
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(_instance_dir, path or 'app.db')
    return os.path.abspath(path)


def _get_writable_db_uri():
    """Retorna URI do banco em diretório gravável. Se instance/ for read-only, usa ~/.pynel_samu/."""
    uri = os.environ.get('DATABASE_URL') or _default_db_uri
    uri = _resolve_sqlite_uri(uri)
    path = _uri_to_path(uri)
    if path:
        dir_path = os.path.dirname(path)
        if not os.access(dir_path, os.W_OK):
            os.makedirs(_fallback_db_dir, exist_ok=True)
            if os.access(_fallback_db_dir, os.W_OK):
                _log.warning(
                    'Diretório do banco não é gravável (%s). Usando %s',
                    dir_path, _fallback_db_path
                )
                return _fallback_db_uri
    return uri


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = _get_writable_db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
