"""
Sistema de agendamento de downloads automáticos
"""

import threading
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import pytz

from app import db
from app.models import ConfiguracaoDownload
from app.selenium_utils import baixar_arquivo_sistema

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')

# Scheduler global
scheduler = None
scheduler_lock = threading.Lock()


# Variável global para armazenar o app
_app = None

def set_app(app):
    """Define o app Flask para uso no scheduler"""
    global _app
    _app = app

def executar_download_agendado():
    """Executa o download agendado de forma assíncrona"""
    global _app
    
    if not _app:
        logger.error("App Flask não configurado no scheduler")
        return
    
    with _app.app_context():
        with scheduler_lock:
            config = ConfiguracaoDownload.query.first()
            if not config or not config.ativo:
                logger.info("Download automático desativado")
                return
            
            logger.info(f"Iniciando download automático (dias_atras={config.dias_atras})")
            config.ultimo_status = 'executando'
            config.ultima_execucao = datetime.utcnow()
            db.session.commit()
            dias_atras = config.dias_atras
        
        # Executar download em thread separada
        def download_thread():
            with _app.app_context():
                try:
                    sucesso = baixar_arquivo_sistema(dias_atras=dias_atras)
                    
                    with scheduler_lock:
                        config = ConfiguracaoDownload.query.first()
                        if config:
                            if sucesso:
                                config.ultimo_status = 'sucesso'
                                config.ultimo_erro = None
                                logger.info("Download automático concluído com sucesso")
                                try:
                                    from app.gerador_alertas import gerar_alertas_automaticos
                                    n = gerar_alertas_automaticos()
                                    if n > 0:
                                        logger.info(f"Alertas gerados automaticamente após download: {n}")
                                except Exception as ex:
                                    logger.warning(f"Erro ao gerar alertas após download: {ex}")
                            else:
                                config.ultimo_status = 'erro'
                                config.ultimo_erro = "Falha no download"
                                logger.error("Download automático falhou")
                            
                            # Calcular próxima execução
                            calcular_proxima_execucao(config)
                            db.session.commit()
                except Exception as e:
                    logger.error(f"Erro no download automático: {e}", exc_info=True)
                    with scheduler_lock:
                        config = ConfiguracaoDownload.query.first()
                        if config:
                            config.ultimo_status = 'erro'
                            config.ultimo_erro = str(e)
                            calcular_proxima_execucao(config)
                            db.session.commit()
        
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()


def calcular_proxima_execucao(config):
    """Calcula a próxima execução baseada na configuração"""
    agora = datetime.now(brasilia_tz)
    
    if config.tipo_agendamento == 'intervalo':
        # Próxima execução = agora + intervalo
        proxima = agora + timedelta(minutes=config.intervalo_minutos)
    else:  # hora_fixa
        # Próxima execução = hoje na hora configurada, ou amanhã se já passou
        proxima = agora.replace(hour=config.hora_fixa, minute=0, second=0, microsecond=0)
        if proxima <= agora:
            proxima += timedelta(days=1)
    
    config.proxima_execucao = proxima.astimezone(pytz.utc).replace(tzinfo=None)


def configurar_agendamento():
    """Configura o agendamento baseado na configuração do banco"""
    global scheduler, _app
    
    if not _app:
        logger.error("App Flask não configurado no scheduler")
        return
    
    with _app.app_context():
        with scheduler_lock:
            # Remover jobs existentes
            if scheduler:
                scheduler.remove_all_jobs()
            
            config = ConfiguracaoDownload.query.first()
            if not config or not config.ativo:
                logger.info("Nenhum agendamento ativo")
                return
            
            # Criar scheduler se não existir
            if not scheduler:
                scheduler = BackgroundScheduler(timezone=brasilia_tz)
                scheduler.start()
                logger.info("Scheduler iniciado")
            
            # Adicionar job baseado no tipo
            if config.tipo_agendamento == 'intervalo':
                trigger = IntervalTrigger(minutes=config.intervalo_minutos)
                scheduler.add_job(
                    executar_download_agendado,
                    trigger=trigger,
                    id='download_automatico',
                    replace_existing=True
                )
                logger.info(f"Agendamento configurado: a cada {config.intervalo_minutos} minutos")
            else:  # hora_fixa
                trigger = CronTrigger(hour=config.hora_fixa, minute=0)
                scheduler.add_job(
                    executar_download_agendado,
                    trigger=trigger,
                    id='download_automatico',
                    replace_existing=True
                )
                logger.info(f"Agendamento configurado: diariamente às {config.hora_fixa:02d}:00")
            
            # Calcular próxima execução
            calcular_proxima_execucao(config)
            db.session.commit()


def iniciar_scheduler(app):
    """Inicia o scheduler quando a aplicação inicia"""
    global scheduler, _app
    _app = app
    
    with app.app_context():
        # Criar configuração padrão se não existir
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
            logger.info("Configuração padrão de download criada")
        
        # Configurar agendamento se ativo
        if config.ativo:
            configurar_agendamento()


def parar_scheduler():
    """Para o scheduler"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler parado")
