"""
Rotas para gerenciamento de dashboards/páginas
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import os
from datetime import datetime
from app import db
from app.models import Dashboard, Indicador, DashboardWidget, Alerta, ConfiguracaoDownload, ConfiguracaoAlerta
from app.calculo_indicadores import calcular_indicador, calcular_variacao_percentual
from app.cache_indicadores import get_or_calc_indicadores
import logging
import json

logger = logging.getLogger(__name__)

bp_dashboards = Blueprint('dashboards', __name__, url_prefix='/dashboards')


def _alertas_para_dashboard(dashboard):
    """Retorna alertas ativos filtrados por dashboard (automáticos selecionados + manuais do dashboard)."""
    from sqlalchemy import or_
    q = Alerta.query.filter_by(status='ativo')
    config_ids = [c.id for c in dashboard.alertas_config] if dashboard.alertas_config else []
    manual_cond = (Alerta.origem == 'manual') & (
        (Alerta.dashboard_id == dashboard.id) | (Alerta.dashboard_id.is_(None))
    )
    if config_ids:
        q = q.filter(or_(Alerta.configuracao_alerta_id.in_(config_ids), manual_cond))
    else:
        q = q.filter(manual_cond)  # Nenhum marcado = só alertas manuais
    return q.order_by(Alerta.criado_em.desc()).limit(100).all()


@bp_dashboards.route('/')
def index():
    """Lista de dashboards"""
    dashboards = Dashboard.query.filter_by(ativo=True).order_by(Dashboard.ordem, Dashboard.nome).all()
    return render_template('dashboards/index.html', dashboards=dashboards)


@bp_dashboards.route('/create', methods=['GET', 'POST'])
def create():
    """Criar novo dashboard"""
    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()
            cor_tema = request.form.get('cor_tema', 'dark')
            ordem = int(request.form.get('ordem', 0) or 0)
            ativo = request.form.get('ativo') == 'on'
            
            indicadores_ids = request.form.getlist('indicadores')
            
            if not nome:
                flash('O nome do dashboard é obrigatório!', 'danger')
                return render_template('dashboards/form.html', modo='create')
            
            opacidade = request.form.get('opacidade_area_grafico', '20').strip()
            opacidade_val = max(0, min(100, int(opacidade) if opacidade.isdigit() else 20))
            dashboard = Dashboard(
                nome=nome,
                descricao=descricao,
                cor_tema=cor_tema,
                ordem=ordem,
                ativo=ativo,
                widgets_grid_template=request.form.get('widgets_grid_template', 'auto'),
                widgets_colunas=int(request.form.get('widgets_colunas', 3) or 3),
                widgets_linhas=int(request.form.get('widgets_linhas') or 0) if request.form.get('widgets_linhas') else None,
                incluir_alertas=request.form.get('incluir_alertas') == 'on',
                opacidade_area_grafico=opacidade_val
            )
            
            # Adicionar indicadores e alertas_config
            if indicadores_ids:
                indicadores = Indicador.query.filter(Indicador.id.in_([int(id) for id in indicadores_ids])).all()
                dashboard.indicadores = indicadores
            alertas_config_ids = request.form.getlist('alertas_config')
            if alertas_config_ids:
                configs = ConfiguracaoAlerta.query.filter(ConfiguracaoAlerta.id.in_([int(x) for x in alertas_config_ids])).all()
                dashboard.alertas_config = configs
            
            db.session.add(dashboard)
            db.session.commit()
            
            flash('Dashboard criado com sucesso!', 'success')
            return redirect(url_for('dashboards.index'))
            
        except Exception as e:
            logger.error(f"Erro ao criar dashboard: {e}", exc_info=True)
            flash(f'Erro ao criar dashboard: {str(e)}', 'danger')
            return render_template('dashboards/form.html', modo='create')
    
    # GET
    indicadores = Indicador.query.filter_by(ativo=True).order_by(Indicador.ordem, Indicador.nome).all()
    configuracoes_alerta = ConfiguracaoAlerta.query.filter_by(ativo=True).order_by(ConfiguracaoAlerta.ordem, ConfiguracaoAlerta.nome).all()
    return render_template('dashboards/form.html', modo='create', indicadores=indicadores, configuracoes_alerta=configuracoes_alerta)


@bp_dashboards.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    """Editar dashboard"""
    dashboard = Dashboard.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            dashboard.nome = request.form.get('nome', '').strip()
            dashboard.descricao = request.form.get('descricao', '').strip()
            dashboard.cor_tema = request.form.get('cor_tema', 'dark')
            dashboard.ordem = int(request.form.get('ordem', 0) or 0)
            dashboard.ativo = request.form.get('ativo') == 'on'
            
            # Configurações de widgets
            dashboard.widgets_grid_template = request.form.get('widgets_grid_template', 'auto')
            dashboard.widgets_colunas = int(request.form.get('widgets_colunas', 3) or 3)
            widgets_linhas = request.form.get('widgets_linhas', '').strip()
            dashboard.widgets_linhas = int(widgets_linhas) if widgets_linhas else None
            dashboard.incluir_alertas = request.form.get('incluir_alertas') == 'on'
            opacidade = request.form.get('opacidade_area_grafico', '20').strip()
            dashboard.opacidade_area_grafico = max(0, min(100, int(opacidade) if opacidade.isdigit() else 20))
            
            if not dashboard.nome:
                flash('O nome do dashboard é obrigatório!', 'danger')
                return render_template('dashboards/form.html', modo='edit', dashboard=dashboard)
            
            # Atualizar indicadores
            indicadores_ids = request.form.getlist('indicadores')
            if indicadores_ids:
                indicadores = Indicador.query.filter(Indicador.id.in_([int(id) for id in indicadores_ids])).all()
                dashboard.indicadores = indicadores
            else:
                dashboard.indicadores = []
            
            # Atualizar alertas_config (quais tipos de alerta automático exibir)
            alertas_config_ids = request.form.getlist('alertas_config')
            if alertas_config_ids:
                configs = ConfiguracaoAlerta.query.filter(ConfiguracaoAlerta.id.in_([int(x) for x in alertas_config_ids])).all()
                dashboard.alertas_config = configs
            else:
                dashboard.alertas_config = []
            
            db.session.commit()
            
            flash('Dashboard atualizado com sucesso!', 'success')
            return redirect(url_for('dashboards.index'))
            
        except Exception as e:
            logger.error(f"Erro ao editar dashboard: {e}", exc_info=True)
            flash(f'Erro ao atualizar dashboard: {str(e)}', 'danger')
            return render_template('dashboards/form.html', modo='edit', dashboard=dashboard)
    
    # GET
    indicadores = Indicador.query.filter_by(ativo=True).order_by(Indicador.ordem, Indicador.nome).all()
    configuracoes_alerta = ConfiguracaoAlerta.query.filter_by(ativo=True).order_by(ConfiguracaoAlerta.ordem, ConfiguracaoAlerta.nome).all()
    return render_template('dashboards/form.html', modo='edit', dashboard=dashboard, indicadores=indicadores, configuracoes_alerta=configuracoes_alerta)


@bp_dashboards.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    """Deletar dashboard"""
    dashboard = Dashboard.query.get_or_404(id)
    
    try:
        db.session.delete(dashboard)
        db.session.commit()
        flash('Dashboard deletado com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao deletar dashboard: {e}", exc_info=True)
        flash(f'Erro ao deletar dashboard: {str(e)}', 'danger')
    
    return redirect(url_for('dashboards.index'))


@bp_dashboards.route('/view/<int:id>')
def view(id):
    """Visualizar dashboard (estilo app Bolsa) - usa cache de indicadores"""
    dashboard = Dashboard.query.get_or_404(id)
    indicadores_calculados = get_or_calc_indicadores(dashboard, 'lista')
    
    # Se incluir_alertas, buscar alertas ativos e dados para modal
    alertas = []
    icones_manual = []
    cores_manual = []
    config_alertas = None
    if getattr(dashboard, 'incluir_alertas', False):
        from app.routes_alertas import _resolver_alertas_por_tempo, ICONES_ALERTA, CORES_ALERTA
        from app.models import ConfiguracaoAlertasSistema
        _resolver_alertas_por_tempo()
        from app.routes_alertas import _deduplicar_alertas
        alertas_raw = _alertas_para_dashboard(dashboard)
        alertas = _deduplicar_alertas(alertas_raw)[:50]
        icones_manual = ICONES_ALERTA
        cores_manual = CORES_ALERTA
        config_alertas = ConfiguracaoAlertasSistema.query.first()
    
    download_config = ConfiguracaoDownload.query.first()
    intervalo_minutos = download_config.intervalo_minutos if download_config else 60
    download_automatico_ativo = bool(download_config and download_config.ativo)
    proxima_execucao_iso = None
    if download_config:
        if download_config.proxima_execucao:
            proxima_execucao_iso = download_config.proxima_execucao.isoformat() + 'Z'
        elif download_automatico_ativo:
            from datetime import timedelta
            import pytz
            brasilia = pytz.timezone('America/Sao_Paulo')
            proxima = datetime.now(brasilia) + timedelta(minutes=intervalo_minutos)
            proxima_execucao_iso = proxima.astimezone(pytz.utc).replace(tzinfo=None).isoformat() + 'Z'
    arquivo_modificado = None
    caminho = os.path.abspath("download/convertido_tabela.xlsx")
    if os.path.exists(caminho):
        try:
            from app.utils import formatar_data_hora_sao_paulo
            from datetime import datetime
            dt = datetime.utcfromtimestamp(os.stat(caminho).st_mtime)
            arquivo_modificado = formatar_data_hora_sao_paulo(dt)
        except Exception:
            pass
    
    return render_template('dashboards/view.html', dashboard=dashboard, indicadores=indicadores_calculados, alertas=alertas, icones_manual=icones_manual, cores_manual=cores_manual, config_alertas=config_alertas, download_intervalo_minutos=intervalo_minutos, download_arquivo_modificado=arquivo_modificado, download_automatico_ativo=download_automatico_ativo, download_proxima_execucao_iso=proxima_execucao_iso)


@bp_dashboards.route('/<int:id>/alertas-manual', methods=['GET', 'POST'])
def alertas_manual(id):
    """Página para gerenciar alertas manuais do dashboard (supervisor)."""
    dashboard = Dashboard.query.get_or_404(id)
    if not dashboard.incluir_alertas:
        flash('Este dashboard não possui painel de alertas.', 'warning')
        return redirect(url_for('dashboards.view', id=id))
    
    from app.routes_alertas import ICONES_ALERTA, CORES_ALERTA
    from app.models import ConfiguracaoAlertasSistema
    
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()
        if titulo and mensagem:
            try:
                alerta = Alerta(
                    configuracao_alerta_id=None,
                    nome_tipo='Manual',
                    icone_tipo=request.form.get('icone', 'megaphone').strip() or 'megaphone',
                    cor_tipo=request.form.get('cor', '#6c757d').strip() or '#6c757d',
                    titulo=titulo,
                    mensagem=mensagem,
                    prioridade=3,
                    origem='manual',
                    status='ativo',
                    dashboard_id=id,
                    criado_por='Sistema'
                )
                db.session.add(alerta)
                db.session.commit()
                try:
                    from app.socketio_alertas import emit_alerta_atualizado
                    emit_alerta_atualizado('criado', alerta_dict=alerta.to_dict())
                except Exception:
                    pass
                flash('Alerta criado com sucesso!', 'success')
            except Exception as e:
                logger.error(f"Erro ao criar alerta manual: {e}", exc_info=True)
                db.session.rollback()
                flash(f'Erro ao criar alerta: {str(e)}', 'danger')
        else:
            flash('Título e mensagem são obrigatórios.', 'danger')
        return redirect(url_for('dashboards.alertas_manual', id=id))
    
    alertas_manuais = Alerta.query.filter_by(
        status='ativo', origem='manual'
    ).filter(
        (Alerta.dashboard_id == id) | (Alerta.dashboard_id.is_(None))
    ).order_by(Alerta.criado_em.desc()).all()
    
    config_alertas = ConfiguracaoAlertasSistema.query.first()
    return render_template('dashboards/alertas_manual.html',
        dashboard=dashboard,
        alertas=alertas_manuais,
        icones=ICONES_ALERTA,
        cores=CORES_ALERTA,
        config_alertas=config_alertas
    )


@bp_dashboards.route('/widgets/<int:id>')
def widgets(id):
    """Visualizar dashboard em modo widgets (estilo iPhone) - usa cache de indicadores"""
    dashboard = Dashboard.query.get_or_404(id)
    indicadores_calculados = get_or_calc_indicadores(dashboard, 'widgets')
    
    download_config = ConfiguracaoDownload.query.first()
    intervalo_minutos = download_config.intervalo_minutos if download_config else 60
    download_automatico_ativo = bool(download_config and download_config.ativo)
    proxima_execucao_iso = None
    if download_config:
        if download_config.proxima_execucao:
            proxima_execucao_iso = download_config.proxima_execucao.isoformat() + 'Z'
        elif download_automatico_ativo:
            from datetime import timedelta
            import pytz
            brasilia = pytz.timezone('America/Sao_Paulo')
            proxima = datetime.now(brasilia) + timedelta(minutes=intervalo_minutos)
            proxima_execucao_iso = proxima.astimezone(pytz.utc).replace(tzinfo=None).isoformat() + 'Z'
    arquivo_modificado = None
    caminho = os.path.abspath("download/convertido_tabela.xlsx")
    if os.path.exists(caminho):
        try:
            from app.utils import formatar_data_hora_sao_paulo
            from datetime import datetime
            dt = datetime.utcfromtimestamp(os.stat(caminho).st_mtime)
            arquivo_modificado = formatar_data_hora_sao_paulo(dt)
        except Exception:
            pass
    
    return render_template('dashboards/widgets.html', 
                         dashboard=dashboard, 
                         indicadores=indicadores_calculados,
                         widgets_grid_template=dashboard.widgets_grid_template,
                         widgets_colunas=dashboard.widgets_colunas,
                         widgets_linhas=dashboard.widgets_linhas,
                         download_intervalo_minutos=intervalo_minutos,
                         download_arquivo_modificado=arquivo_modificado,
                         download_automatico_ativo=download_automatico_ativo,
                         download_proxima_execucao_iso=proxima_execucao_iso)


@bp_dashboards.route('/api/dados/<int:id>')
def api_dados(id):
    """API para obter indicadores do dashboard (cache). ?mode=lista|widgets"""
    dashboard = Dashboard.query.get_or_404(id)
    mode = request.args.get('mode', 'lista')
    if mode not in ('lista', 'widgets'):
        mode = 'lista'
    indicadores = get_or_calc_indicadores(dashboard, mode)
    return jsonify({'indicadores': indicadores})


@bp_dashboards.route('/api/indicador/<int:id>')
def api_indicador(id):
    """API para obter dados de um indicador específico"""
    indicador = Indicador.query.get_or_404(id)
    resultado = calcular_indicador(indicador)
    resultado['id'] = indicador.id
    return jsonify(resultado)


@bp_dashboards.route('/widgets/config/<int:id>', methods=['GET', 'POST'])
def widgets_config(id):
    """Configurar widgets do dashboard"""
    dashboard = Dashboard.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Salvar configurações de widgets individuais
            if request.is_json:
                payload = request.get_json()
                if isinstance(payload, dict) and 'widgets' in payload:
                    widgets_data = payload.get('widgets', [])
                    # Atualizar grid do dashboard
                    if 'grid_colunas' in payload:
                        dashboard.widgets_colunas = int(payload.get('grid_colunas', 3) or 3)
                    if 'grid_linhas' in payload and payload.get('grid_linhas') is not None:
                        vl = payload.get('grid_linhas')
                        dashboard.widgets_linhas = int(vl) if vl else None
                    if 'grid_template' in payload:
                        dashboard.widgets_grid_template = payload.get('grid_template', 'auto')
                else:
                    widgets_data = payload if isinstance(payload, list) else []
            else:
                widgets_data_str = request.form.get('widgets_data', '[]')
                widgets_data = json.loads(widgets_data_str) if widgets_data_str else []
            
            # Remover configurações antigas
            DashboardWidget.query.filter_by(dashboard_id=id).delete()
            
            # Criar novas configurações
            for widget_data in widgets_data:
                widget = DashboardWidget(
                    dashboard_id=id,
                    indicador_id=int(widget_data.get('indicador_id')),
                    ordem=int(widget_data.get('ordem', 0)),
                    coluna_span=int(widget_data.get('coluna_span', 1)),
                    linha_span=int(widget_data.get('linha_span', 1)),
                    grafico_altura=int(widget_data.get('grafico_altura', 80)),
                    posicao_x=widget_data.get('posicao_x'),
                    posicao_y=widget_data.get('posicao_y')
                )
                db.session.add(widget)
            
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True})
            else:
                flash('Configuração de widgets salva com sucesso!', 'success')
                return redirect(url_for('dashboards.widgets_config', id=id))
            
        except Exception as e:
            logger.error(f"Erro ao salvar configuração de widgets: {e}", exc_info=True)
            if request.is_json:
                return jsonify({'success': False, 'error': str(e)}), 400
            else:
                flash(f'Erro ao salvar configuração: {str(e)}', 'danger')
                return redirect(url_for('dashboards.widgets_config', id=id))
    
    # GET - mostrar página de configuração
    widgets_config = {w.indicador_id: w.to_dict() for w in dashboard.widgets_config}
    indicadores_com_config = []
    
    for indicador in dashboard.indicadores:
        if indicador.ativo:
            if indicador.id in widgets_config:
                config = widgets_config[indicador.id]
            else:
                # Configuração padrão
                config = {
                    'ordem': indicador.ordem,
                    'coluna_span': 1,
                    'linha_span': 1,
                    'grafico_altura': 80,
                    'posicao_x': None,
                    'posicao_y': None
                }
            indicadores_com_config.append({
                'indicador': indicador,
                'config': config
            })
    
    # Ordenar por ordem configurada
    indicadores_com_config.sort(key=lambda x: x['config'].get('ordem', x['indicador'].ordem))
    
    # Mesmas variáveis da view de widgets para o preview corresponder fielmente
    return render_template('dashboards/widgets_config.html', 
                         dashboard=dashboard, 
                         indicadores_com_config=indicadores_com_config,
                         widgets_grid_template=dashboard.widgets_grid_template or 'auto',
                         widgets_colunas=dashboard.widgets_colunas or 3,
                         widgets_linhas=dashboard.widgets_linhas)
