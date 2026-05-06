# Rotas de autenticação: login, logout

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import User
from app.auth_utils import permission_required

bp_auth = Blueprint('auth', __name__)


def _normalizar_cpf(cpf):
    """Remove tudo que não for dígito do CPF."""
    if not cpf:
        return ''
    return ''.join(c for c in str(cpf) if c.isdigit())


@bp_auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Informe usuário e senha.', 'danger')
            return render_template('auth/login.html')
        user = User.query.filter_by(username=username).first()
        if user is None or not user.ativo:
            flash('Usuário ou senha inválidos.', 'danger')
            return render_template('auth/login.html')
        if not check_password_hash(user.password_hash, password):
            flash('Usuário ou senha inválidos.', 'danger')
            return render_template('auth/login.html')
        login_user(user)
        next_url = request.form.get('next') or request.args.get('next') or url_for('main.index')
        from urllib.parse import urlparse
        if next_url and urlparse(next_url).netloc:
            next_url = url_for('main.index')
        return redirect(next_url)
    return render_template('auth/login.html')


@bp_auth.route('/alterar-senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    """Permite ao usuário logado alterar a própria senha."""
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual') or ''
        nova_senha = request.form.get('nova_senha') or ''
        confirmar = request.form.get('confirmar_senha') or ''
        if not senha_atual or not nova_senha or not confirmar:
            flash('Preencha todos os campos.', 'danger')
            return render_template('auth/alterar_senha.html')
        if not check_password_hash(current_user.password_hash, senha_atual):
            flash('Senha atual incorreta.', 'danger')
            return render_template('auth/alterar_senha.html')
        if len(nova_senha) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('auth/alterar_senha.html')
        if nova_senha != confirmar:
            flash('A confirmação da nova senha não confere.', 'danger')
            return render_template('auth/alterar_senha.html')
        current_user.password_hash = generate_password_hash(nova_senha)
        db.session.commit()
        flash('Senha alterada com sucesso.', 'success')
        return redirect(url_for('main.index'))
    return render_template('auth/alterar_senha.html')


@bp_auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))
