from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.config import Config
import logging

db = SQLAlchemy()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    from app.utils import formatar_valor_indicador, formatar_data_hora_sao_paulo
    app.jinja_env.filters['formatar_indicador'] = formatar_valor_indicador
    app.jinja_env.filters['horario_sao_paulo'] = formatar_data_hora_sao_paulo
    
    # Filtro para parsear JSON em templates
    import json
    def from_json(value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except:
            return {}
    app.jinja_env.filters['from_json'] = from_json

    def transparencia_hex(pct):
        """Converte % (0-100) em sufixo hex para cor com alpha. Ex: 20 -> '33'"""
        if pct is None:
            pct = 20
        pct = max(0, min(100, int(pct)))
        return '{:02x}'.format(int(round(pct / 100 * 255)))
    app.jinja_env.filters['transparencia_hex'] = transparencia_hex

    def gray_gradient_hex(value, min_val, max_val, light_hex='#e9ecef', dark_hex='#495057'):
        """Retorna dict com bg e color para valor no intervalo. Menor=mais claro, maior=mais escuro."""
        if value is None or min_val is None or max_val is None:
            return None
        if max_val == min_val:
            ratio = 1.0
        else:
            ratio = max(0, min(1, (value - min_val) / (max_val - min_val)))
        def hex_to_rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        def rgb_to_hex(r, g, b):
            return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))
        r1, g1, b1 = hex_to_rgb(light_hex)
        r2, g2, b2 = hex_to_rgb(dark_hex)
        r = r1 + (r2 - r1) * ratio
        g = g1 + (g2 - g1) * ratio
        b = b1 + (b2 - b1) * ratio
        bg = rgb_to_hex(r, g, b)
        fg = '#212529' if ratio < 0.5 else '#fff'
        return {'bg': bg, 'color': fg}
    app.jinja_env.filters['gray_gradient'] = gray_gradient_hex

    db.init_app(app)
    
    # Registrar blueprints
    from app.routes import bp
    app.register_blueprint(bp)
    
    from app.routes_download import bp_download
    app.register_blueprint(bp_download)
    
    from app.routes_indicadores import bp_indicadores
    app.register_blueprint(bp_indicadores)
    
    from app.routes_dashboards import bp_dashboards
    app.register_blueprint(bp_dashboards)
    
    from app.routes_alertas import bp_alertas
    app.register_blueprint(bp_alertas)
    
    with app.app_context():
        # Criar tabelas do banco de dados (se houver modelos)
        db.create_all()
        
        # NOTA: Migração de alertas removida - não apagar dados automaticamente
        # Se precisar fazer migração manual, execute via script separado
        
        # Migração: adicionar colunas em indicador se não existirem (bancos antigos)
        try:
            from sqlalchemy import inspect, text
            insp = inspect(db.engine)
            if 'indicador' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('indicador')]
                with db.engine.connect() as conn:
                    if 'contagem_por' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN contagem_por VARCHAR(20) DEFAULT 'linhas'"))
                    if 'coluna_ocorrencia' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN coluna_ocorrencia VARCHAR(100)"))
                    if 'meta_valor' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN meta_valor FLOAT"))
                    if 'meta_operador' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN meta_operador VARCHAR(10)"))
                    if 'grafico_historico_habilitado' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_historico_habilitado BOOLEAN DEFAULT 0"))
                    if 'grafico_historico_cor' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_historico_cor VARCHAR(20) DEFAULT '#6c757d'"))
                    if 'grafico_historico_dados' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_historico_dados TEXT"))
                    if 'grafico_meta_habilitado' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_habilitado BOOLEAN DEFAULT 0"))
                    if 'grafico_meta_valor' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_valor FLOAT"))
                    if 'grafico_meta_cor' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_cor VARCHAR(20) DEFAULT '#ffc107'"))
                    if 'grafico_meta_estilo' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_estilo VARCHAR(20) DEFAULT 'dashed'"))
                    conn.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("Migração indicador: %s", e)
        
        # Migração: adicionar sumir_quando_resolvido em configuracao_alerta
        try:
            from sqlalchemy import inspect, text
            insp = inspect(db.engine)
            if 'configuracao_alerta' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('configuracao_alerta')]
                if 'sumir_quando_resolvido' not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE configuracao_alerta ADD COLUMN sumir_quando_resolvido BOOLEAN DEFAULT 0"))
                        conn.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("Migração configuracao_alerta: %s", e)
        
        # Migração: adicionar incluir_alertas e opacidade_area_grafico em dashboard
        try:
            from sqlalchemy import inspect, text
            insp = inspect(db.engine)
            if 'dashboard' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('dashboard')]
                with db.engine.connect() as conn:
                    if 'incluir_alertas' not in cols:
                        conn.execute(text("ALTER TABLE dashboard ADD COLUMN incluir_alertas BOOLEAN DEFAULT 0"))
                        conn.commit()
                    if 'opacidade_area_grafico' not in cols:
                        conn.execute(text("ALTER TABLE dashboard ADD COLUMN opacidade_area_grafico INTEGER DEFAULT 20"))
                        conn.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("Migração dashboard: %s", e)
        
        # Criar tabela configuracao_alertas_sistema e inserir linha padrão se vazia
        try:
            from app.models import ConfiguracaoAlertasSistema
            from sqlalchemy import inspect, text
            db.create_all()
            insp = inspect(db.engine)
            if 'configuracao_alertas_sistema' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('configuracao_alertas_sistema')]
                if 'som_alerta' not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE configuracao_alertas_sistema ADD COLUMN som_alerta VARCHAR(50) DEFAULT 'beep'"))
                        conn.commit()
                        if 'son_notificar_novo_alerta' in cols:
                            conn.execute(text("UPDATE configuracao_alertas_sistema SET som_alerta = CASE WHEN COALESCE(son_notificar_novo_alerta, 1) = 0 THEN 'none' ELSE 'beep' END"))
                            conn.commit()
                if 'transparencia_alerta' not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE configuracao_alertas_sistema ADD COLUMN transparencia_alerta INTEGER DEFAULT 20"))
                        conn.commit()
            if ConfiguracaoAlertasSistema.query.first() is None:
                cfg = ConfiguracaoAlertasSistema(resolver_apos_minutos=45)
                db.session.add(cfg)
                db.session.commit()
        except Exception as e:
            logging.getLogger(__name__).warning("Migração configuracao_alertas_sistema: %s", e)
        
        # Iniciar scheduler de downloads automáticos
        from app.download_scheduler import iniciar_scheduler
        iniciar_scheduler(app)
    
    return app
