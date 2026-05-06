from flask import Blueprint, redirect, url_for, Response, render_template

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Página inicial: mostra atalhos conforme permissões do usuário."""
    return render_template('main/home.html')


@bp.route('/favicon.ico')
def favicon():
    """Evita 404 no console quando o navegador solicita favicon."""
    return Response(status=204)
