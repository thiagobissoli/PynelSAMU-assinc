"""
Rotas para gerenciamento de dashboards/páginas
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import os
from app import db
from app.models import Dashboard, Indicador, DashboardWidget, Alerta, ConfiguracaoDownload
from app.calculo_indicadores import calcular_indicador, calcular_variacao_percentual
import logging
import json

logger = logging.getLogger(__name__)

bp_dashboards = Blueprint('dashboards', __name__, url_prefix='/dashboards')


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
            
            # Adicionar indicadores
            if indicadores_ids:
                indicadores = Indicador.query.filter(Indicador.id.in_([int(id) for id in indicadores_ids])).all()
                dashboard.indicadores = indicadores
            
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
    return render_template('dashboards/form.html', modo='create', indicadores=indicadores)


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
            
            db.session.commit()
            
            flash('Dashboard atualizado com sucesso!', 'success')
            return redirect(url_for('dashboards.index'))
            
        except Exception as e:
            logger.error(f"Erro ao editar dashboard: {e}", exc_info=True)
            flash(f'Erro ao atualizar dashboard: {str(e)}', 'danger')
            return render_template('dashboards/form.html', modo='edit', dashboard=dashboard)
    
    # GET
    indicadores = Indicador.query.filter_by(ativo=True).order_by(Indicador.ordem, Indicador.nome).all()
    return render_template('dashboards/form.html', modo='edit', dashboard=dashboard, indicadores=indicadores)


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
    """Visualizar dashboard (estilo app Bolsa)"""
    dashboard = Dashboard.query.get_or_404(id)
    
    # Calcular todos os indicadores do dashboard
    indicadores_calculados = []
    for indicador in dashboard.indicadores:
        if indicador.ativo:
            resultado = calcular_indicador(indicador)
            resultado['id'] = indicador.id
            resultado['nome_completo'] = indicador.nome
            resultado['descricao'] = indicador.descricao
            resultado['tipo_calculo'] = indicador.tipo_calculo
            resultado['grafico_habilitado'] = indicador.grafico_habilitado
            resultado['grafico_ultimas_horas'] = indicador.grafico_ultimas_horas
            resultado['grafico_intervalo_minutos'] = indicador.grafico_intervalo_minutos
            resultado['filtro_ultimas_horas'] = indicador.filtro_ultimas_horas  # Janela de média móvel
            resultado['ordem'] = indicador.ordem
            
            # Configuração de tendência
            resultado['tendencia_inversa'] = indicador.tendencia_inversa
            resultado['cor_subida'] = indicador.cor_subida or '#34c759'
            resultado['cor_descida'] = indicador.cor_descida or '#ff3b30'
            
            # Calcular variação na última hora
            variacao = calcular_variacao_percentual(indicador)
            resultado['variacao_percentual'] = variacao.get('variacao_percentual')
            resultado['tendencia'] = variacao.get('tendencia', 'neutra')
            
            indicadores_calculados.append(resultado)
    
    # Ordenar por ordem configurada
    indicadores_calculados.sort(key=lambda x: x.get('ordem', 999))
    
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
        alertas_raw = Alerta.query.filter_by(status='ativo').order_by(Alerta.criado_em.desc()).limit(100).all()
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


@bp_dashboards.route('/widgets/<int:id>')
def widgets(id):
    """Visualizar dashboard em modo widgets (estilo iPhone)"""
    dashboard = Dashboard.query.get_or_404(id)
    
    # Calcular todos os indicadores do dashboard
    indicadores_calculados = []
    for indicador in dashboard.indicadores:
        if indicador.ativo:
            resultado = calcular_indicador(indicador)
            resultado['id'] = indicador.id
            resultado['nome_completo'] = indicador.nome
            resultado['descricao'] = indicador.descricao
            resultado['tipo_calculo'] = indicador.tipo_calculo
            resultado['grafico_habilitado'] = indicador.grafico_habilitado
            resultado['grafico_ultimas_horas'] = indicador.grafico_ultimas_horas
            resultado['grafico_intervalo_minutos'] = indicador.grafico_intervalo_minutos
            resultado['filtro_ultimas_horas'] = indicador.filtro_ultimas_horas  # Janela de média móvel
            resultado['grafico_historico_habilitado'] = indicador.grafico_historico_habilitado
            resultado['grafico_historico_cor'] = indicador.grafico_historico_cor or '#6c757d'
            resultado['grafico_meta_habilitado'] = indicador.grafico_meta_habilitado
            resultado['grafico_meta_cor'] = indicador.grafico_meta_cor or '#ffc107'
            resultado['grafico_meta_estilo'] = indicador.grafico_meta_estilo or 'dashed'
            resultado['ordem'] = indicador.ordem
            
            # Configuração de tendência
            resultado['tendencia_inversa'] = indicador.tendencia_inversa
            resultado['cor_subida'] = indicador.cor_subida or '#34c759'
            resultado['cor_descida'] = indicador.cor_descida or '#ff3b30'
            
            # Calcular variação na última hora
            variacao = calcular_variacao_percentual(indicador)
            resultado['variacao_percentual'] = variacao.get('variacao_percentual')
            resultado['tendencia'] = variacao.get('tendencia', 'neutra')
            
            indicadores_calculados.append(resultado)
    
    # Carregar configurações de widgets
    widgets_config = {w.indicador_id: w.to_dict() for w in dashboard.widgets_config}
    
    # Aplicar configurações aos indicadores
    for resultado in indicadores_calculados:
        ind_id = resultado['id']
        if ind_id in widgets_config:
            config = widgets_config[ind_id]
            resultado['widget_coluna_span'] = config.get('coluna_span', 1)
            resultado['widget_linha_span'] = config.get('linha_span', 1)
            resultado['widget_grafico_altura'] = config.get('grafico_altura', 80)
            resultado['widget_ordem'] = config.get('ordem', resultado.get('ordem', 999))
        else:
            resultado['widget_coluna_span'] = 1
            resultado['widget_linha_span'] = 1
            resultado['widget_grafico_altura'] = 80
            resultado['widget_ordem'] = resultado.get('ordem', 999)
    
    # Ordenar por ordem configurada
    indicadores_calculados.sort(key=lambda x: x.get('widget_ordem', 999))
    
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
