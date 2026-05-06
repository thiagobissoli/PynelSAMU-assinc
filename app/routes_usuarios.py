# Rotas de usuários e perfis (somente administrador)

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from werkzeug.security import generate_password_hash

from app import db
from app.models import User, Role, Permission
from app.auth_utils import admin_required


def _normalizar_cpf(cpf):
    if not cpf:
        return ''
    return ''.join(c for c in str(cpf) if c.isdigit())


bp_usuarios = Blueprint('usuarios', __name__, url_prefix='/usuarios')


@bp_usuarios.route('/')
@login_required
@admin_required
def index():
    usuarios = User.query.order_by(User.nome_completo).all()
    return render_template('usuarios/index.html', usuarios=usuarios)


@bp_usuarios.route('/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo():
    roles = Role.query.order_by(Role.nome).all()
    if not roles:
        flash('Cadastre pelo menos um perfil antes de criar usuários.', 'warning')
        return redirect(url_for('usuarios.perfis_index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        nome_completo = (request.form.get('nome_completo') or '').strip()
        cpf_raw = (request.form.get('cpf') or '').strip()
        crm = (request.form.get('crm') or '').strip()
        role_id = request.form.get('role_id', type=int)
        cpf = _normalizar_cpf(cpf_raw)
        if not username or not nome_completo or not cpf or not crm:
            flash('Preencha usuário, nome completo, CPF e CRM.', 'danger')
            return render_template('usuarios/form.html', modo='create', roles=roles,
                                   username=username, nome_completo=nome_completo, cpf=cpf_raw or cpf, crm=crm, role_id=role_id)
        if User.query.filter_by(username=username).first():
            flash('Já existe um usuário com este nome de usuário.', 'danger')
            return render_template('usuarios/form.html', modo='create', roles=roles,
                                   username=username, nome_completo=nome_completo, cpf=cpf_raw or cpf, crm=crm, role_id=role_id)
        if User.query.filter_by(cpf=cpf).first():
            flash('Já existe um usuário com este CPF.', 'danger')
            return render_template('usuarios/form.html', modo='create', roles=roles,
                                   username=username, nome_completo=nome_completo, cpf=cpf_raw or cpf, crm=crm, role_id=role_id)
        role = Role.query.get(role_id) if role_id else None
        if not role:
            flash('Perfil inválido.', 'danger')
            return render_template('usuarios/form.html', modo='create', roles=roles)
        senha_inicial = cpf
        user = User(
            username=username,
            nome_completo=nome_completo,
            cpf=cpf,
            crm=crm,
            password_hash=generate_password_hash(senha_inicial),
            role_id=role.id,
            ativo=True
        )
        db.session.add(user)
        db.session.commit()
        flash(f'Usuário "{username}" criado. Senha inicial: CPF do usuário.', 'success')
        return redirect(url_for('usuarios.index'))
    return render_template('usuarios/form.html', modo='create', roles=roles,
                           username='', nome_completo='', cpf='', crm='', role_id=None)


@bp_usuarios.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar(id):
    user = User.query.get_or_404(id)
    roles = Role.query.order_by(Role.nome).all()
    if request.method == 'POST':
        user.nome_completo = (request.form.get('nome_completo') or '').strip() or user.nome_completo
        user.crm = (request.form.get('crm') or '').strip() or user.crm
        role_id = request.form.get('role_id', type=int)
        if role_id:
            role = Role.query.get(role_id)
            if role:
                user.role_id = role.id
        ativo = request.form.get('ativo')
        user.ativo = ativo == '1' or ativo == 'on'
        db.session.commit()
        flash('Usuário atualizado.', 'success')
        return redirect(url_for('usuarios.index'))
    return render_template('usuarios/form.html', modo='edit', user=user, roles=roles)


@bp_usuarios.route('/resetar-senha/<int:id>', methods=['POST'])
@login_required
@admin_required
def resetar_senha(id):
    user = User.query.get_or_404(id)
    nova_senha = user.cpf
    user.password_hash = generate_password_hash(nova_senha)
    db.session.commit()
    flash(f'Senha de "{user.username}" resetada para o CPF (sem formatação).', 'success')
    return redirect(url_for('usuarios.index'))


# --- Perfis (Roles) e Permissões ---

@bp_usuarios.route('/perfis')
@login_required
@admin_required
def perfis_index():
    roles = Role.query.order_by(Role.nome).all()
    return render_template('usuarios/perfis_index.html', roles=roles)


@bp_usuarios.route('/perfis/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def perfil_novo():
    permissions = Permission.query.order_by(Permission.codigo).all()
    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        descricao = (request.form.get('descricao') or '').strip()
        if not nome:
            flash('Informe o nome do perfil.', 'danger')
            return render_template('usuarios/perfil_form.html', modo='create', permissions=permissions)
        if Role.query.filter_by(nome=nome).first():
            flash('Já existe um perfil com este nome.', 'danger')
            return render_template('usuarios/perfil_form.html', modo='create', permissions=permissions, nome=nome, descricao=descricao)
        role = Role(nome=nome, descricao=descricao or None)
        db.session.add(role)
        db.session.flush()
        perms_ids = request.form.getlist('permission_id', type=int)
        for pid in perms_ids:
            perm = Permission.query.get(pid)
            if perm:
                role.permissions.append(perm)
        db.session.commit()
        flash('Perfil criado.', 'success')
        return redirect(url_for('usuarios.perfis_index'))
    return render_template('usuarios/perfil_form.html', modo='create', permissions=permissions)


@bp_usuarios.route('/perfis/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def perfil_editar(id):
    role = Role.query.get_or_404(id)
    permissions = Permission.query.order_by(Permission.codigo).all()
    if request.method == 'POST':
        role.nome = (request.form.get('nome') or '').strip() or role.nome
        role.descricao = (request.form.get('descricao') or '').strip() or None
        role.permissions = []
        perms_ids = request.form.getlist('permission_id', type=int)
        for pid in perms_ids:
            perm = Permission.query.get(pid)
            if perm:
                role.permissions.append(perm)
        db.session.commit()
        flash('Perfil atualizado.', 'success')
        return redirect(url_for('usuarios.perfis_index'))
    return render_template('usuarios/perfil_form.html', modo='edit', role=role, permissions=permissions)
