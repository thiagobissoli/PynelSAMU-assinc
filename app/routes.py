from flask import Blueprint, redirect, url_for, Response

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Redireciona para a página de download"""
    return redirect(url_for('download.index'))


@bp.route('/favicon.ico')
def favicon():
    """Evita 404 no console quando o navegador solicita favicon."""
    return Response(status=204)
