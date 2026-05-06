# Utilitários de autenticação e autorização

from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def permission_required(codigo_permissao):
    """Decorator que exige que o usuário esteja logado e tenha a permissão indicada."""
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Faça login para acessar esta página.', 'warning')
                from flask import request
                next_url = request.url if request.url else None
                return redirect(url_for('auth.login', next=next_url))
            if not current_user.tem_permissao(codigo_permissao):
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return inner
    return decorator


def admin_required(f):
    """Decorator que exige que o usuário seja administrador."""
    return permission_required('admin')(f)


def permission_required_or_admin(codigo_permissao):
    """Decorator: exige a permissão indicada OU perfil administrador."""
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Faça login para acessar esta página.', 'warning')
                from flask import request
                next_url = request.url if request.url else None
                return redirect(url_for('auth.login', next=next_url))
            if current_user.is_admin():
                return f(*args, **kwargs)
            if not current_user.tem_permissao(codigo_permissao):
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return inner
    return decorator
