"""
Rotas para download e visualização de indicadores
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
import os
import logging
import threading
from datetime import datetime, timedelta
import pytz

from app import db
from app.models import ConfiguracaoDownload
from app.selenium_utils import baixar_arquivo_sistema
from app.download_scheduler import configurar_agendamento
from app.indicadores import (
    carregar_dados, 
    carregar_dados_historico,
    gerar_indicadores_gerais,
    gerar_resumo_dados,
    obter_estatisticas_coluna
)

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')

bp_download = Blueprint('download', __name__, url_prefix='/download')


@bp_download.route('/')
def index():
    """Página principal de download e indicadores"""
    # Verificar se arquivos existem
    caminho_arquivo = os.path.abspath("download/convertido_tabela.xlsx")
    caminho_historico = os.path.abspath("download/historico.xlsx")
    
    arquivo_existe = os.path.exists(caminho_arquivo)
    historico_existe = os.path.exists(caminho_historico)
    
    # Carregar dados se existirem
    df = None
    indicadores = {}
    resumo = {}
    
    if arquivo_existe:
        df = carregar_dados()
        if df is not None:
            indicadores = gerar_indicadores_gerais(df)
            resumo = gerar_resumo_dados(df)
    
    # Carregar configuração de download automático
    config = ConfiguracaoDownload.query.first()
    
    # Download manual só pode ser executado via localhost (evita concorrência com acesso por IP)
    pode_executar_download = request.remote_addr in ('127.0.0.1', '::1')
    
    return render_template(
        'download/index.html',
        arquivo_existe=arquivo_existe,
        historico_existe=historico_existe,
        indicadores=indicadores,
        resumo=resumo,
        df=df,
        config=config,
        pode_executar_download=pode_executar_download
    )


def _eh_localhost():
    """Verifica se a requisição veio de localhost (permite download manual apenas localmente)"""
    return request.remote_addr in ('127.0.0.1', '::1')


@bp_download.route('/executar', methods=['POST'])
def executar_download():
    """Executa o download do arquivo de forma assíncrona. Apenas via localhost."""
    try:
        if not _eh_localhost():
            flash('Download manual só pode ser executado acessando via localhost (127.0.0.1). O timer automático continua funcionando.', 'warning')
            return redirect(url_for('download.index'))
        
        # Obter parâmetros do formulário
        dias_atras = int(request.form.get('dias_atras', 1))
        data_inicio = request.form.get('data_inicio', '').strip()
        data_fim = request.form.get('data_fim', '').strip()
        
        # Validar datas se fornecidas
        if data_inicio and data_fim:
            try:
                datetime.strptime(data_inicio, '%d/%m/%Y')
                datetime.strptime(data_fim, '%d/%m/%Y')
            except ValueError:
                flash('Formato de data inválido. Use DD/MM/YYYY', 'danger')
                return redirect(url_for('download.index'))
        else:
            data_inicio = None
            data_fim = None
        
        logger.info(f"Iniciando download assíncrono (dias_atras={dias_atras}, data_inicio={data_inicio}, data_fim={data_fim})")
        
        app = current_app._get_current_object()
        def download_thread():
            with app.app_context():
                try:
                    sucesso = baixar_arquivo_sistema(
                        dias_atras=dias_atras,
                        data_inicio=data_inicio,
                        data_fim=data_fim
                    )
                    if sucesso:
                        logger.info("Download concluído com sucesso")
                        try:
                            config_dl = ConfiguracaoDownload.query.first()
                            if config_dl:
                                config_dl.ultima_execucao = datetime.utcnow()
                                config_dl.ultimo_status = 'sucesso'
                                config_dl.ultimo_erro = None
                                from datetime import timedelta
                                import pytz
                                brasilia = pytz.timezone('America/Sao_Paulo')
                                agora = datetime.now(brasilia)
                                proxima = agora + timedelta(minutes=config_dl.intervalo_minutos or 60)
                                config_dl.proxima_execucao = proxima.astimezone(pytz.utc).replace(tzinfo=None)
                                db.session.commit()
                        except Exception:
                            pass
                        try:
                            from app.gerador_alertas import gerar_alertas_automaticos
                            n = gerar_alertas_automaticos()
                            if n > 0:
                                logger.info(f"Alertas gerados automaticamente após download: {n}")
                        except Exception as ex:
                            logger.warning(f"Erro ao gerar alertas após download: {ex}")
                    else:
                        logger.error("Download falhou")
                except Exception as e:
                    logger.error(f"Erro no download: {e}", exc_info=True)
        
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
        
        flash('Download iniciado em background. Você pode continuar usando o sistema.', 'info')
        return redirect(url_for('download.index'))
        
    except Exception as e:
        logger.error(f"Erro ao iniciar download: {e}", exc_info=True)
        flash(f'Erro ao iniciar download: {str(e)}', 'danger')
        return redirect(url_for('download.index'))


@bp_download.route('/indicadores')
def ver_indicadores():
    """Visualiza indicadores detalhados"""
    df = carregar_dados()
    
    if df is None:
        flash('Nenhum arquivo encontrado. Execute um download primeiro.', 'warning')
        return redirect(url_for('download.index'))
    
    indicadores = gerar_indicadores_gerais(df)
    resumo = gerar_resumo_dados(df)
    
    # Estatísticas por coluna
    estatisticas_colunas = {}
    for coluna in df.columns:
        stats = obter_estatisticas_coluna(df, coluna)
        if stats:
            estatisticas_colunas[coluna] = stats
    
    return render_template(
        'download/indicadores.html',
        indicadores=indicadores,
        resumo=resumo,
        estatisticas_colunas=estatisticas_colunas,
        colunas=df.columns.tolist()
    )


@bp_download.route('/dados')
def ver_dados():
    """Visualiza os dados em formato de tabela"""
    df = carregar_dados()
    
    if df is None:
        flash('Nenhum arquivo encontrado. Execute um download primeiro.', 'warning')
        return redirect(url_for('download.index'))
    
    # Paginação simples
    pagina = int(request.args.get('pagina', 1))
    por_pagina = int(request.args.get('por_pagina', 50))
    
    total_linhas = len(df)
    total_paginas = (total_linhas + por_pagina - 1) // por_pagina
    
    inicio = (pagina - 1) * por_pagina
    fim = inicio + por_pagina
    
    df_paginado = df.iloc[inicio:fim]
    
    return render_template(
        'download/dados.html',
        df=df_paginado,
        pagina=pagina,
        total_paginas=total_paginas,
        total_linhas=total_linhas,
        por_pagina=por_pagina,
        colunas=df.columns.tolist()
    )


@bp_download.route('/api/status')
def api_status():
    """API para verificar status dos arquivos. Usado por dashboards para atualizar após download."""
    caminho_arquivo = os.path.abspath("download/convertido_tabela.xlsx")
    caminho_historico = os.path.abspath("download/historico.xlsx")
    
    status = {
        'arquivo_existe': os.path.exists(caminho_arquivo),
        'historico_existe': os.path.exists(caminho_historico),
    }
    
    config = ConfiguracaoDownload.query.first()
    status['intervalo_minutos'] = config.intervalo_minutos if config else 60
    status['download_automatico_ativo'] = bool(config and config.ativo)
    status['ultimo_status'] = config.ultimo_status if config else None
    if config and config.proxima_execucao:
        status['proxima_execucao_iso'] = config.proxima_execucao.isoformat() + 'Z'
    else:
        status['proxima_execucao_iso'] = None
    
    if status['arquivo_existe']:
        try:
            from app.utils import formatar_data_hora_sao_paulo
            stat_info = os.stat(caminho_arquivo)
            dt_utc = datetime.utcfromtimestamp(stat_info.st_mtime)
            status['arquivo_modificado'] = formatar_data_hora_sao_paulo(dt_utc)
            status['arquivo_tamanho'] = stat_info.st_size
        except Exception:
            pass
    
    return jsonify(status)


@bp_download.route('/config', methods=['GET', 'POST'])
def config_download_automatico():
    """Configurar download automático"""
    config = ConfiguracaoDownload.query.first()
    if not config:
        config = ConfiguracaoDownload(
            ativo=False,
            tipo_agendamento='intervalo',
            intervalo_minutos=60,
            dias_atras=1
        )
        db.session.add(config)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            config.ativo = request.form.get('ativo') == 'on'
            config.tipo_agendamento = request.form.get('tipo_agendamento', 'intervalo')
            config.intervalo_minutos = int(request.form.get('intervalo_minutos', 60))
            config.hora_fixa = int(request.form.get('hora_fixa', 0)) if request.form.get('hora_fixa') else None
            config.dias_atras = int(request.form.get('dias_atras', 1))
            
            db.session.commit()
            
            # Reconfigurar agendamento (usar o app atual)
            app = current_app._get_current_object()
            def reconfigurar():
                with app.app_context():
                    configurar_agendamento()
            
            thread = threading.Thread(target=reconfigurar, daemon=True)
            thread.start()
            
            flash('Configuração de download automático salva com sucesso!', 'success')
            return redirect(url_for('download.config_download_automatico'))
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}", exc_info=True)
            flash(f'Erro ao salvar configuração: {str(e)}', 'danger')
    
    return render_template('download/config.html', config=config)


@bp_download.route('/api/config')
def api_config():
    """API para obter configuração atual"""
    config = ConfiguracaoDownload.query.first()
    if not config:
        return jsonify({'ativo': False})
    return jsonify(config.to_dict())
