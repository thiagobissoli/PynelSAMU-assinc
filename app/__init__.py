from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from app.config import Config
from app.socketio_alertas import socketio
import logging

db = SQLAlchemy()
login_manager = LoginManager()

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
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Registrar blueprints
    from app.routes_auth import bp_auth
    app.register_blueprint(bp_auth, url_prefix='/auth')
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

    from app.routes_usuarios import bp_usuarios
    app.register_blueprint(bp_usuarios)

    from flask import request
    from flask_login import current_user

    @app.before_request
    def exigir_login():
        if request.endpoint and request.endpoint not in ('auth.login', 'static', 'main.favicon'):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                return redirect(url_for('auth.login', next=request.url))

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
                    if 'grafico_meta_operador' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_operador VARCHAR(10) DEFAULT '<='"))
                    if 'grafico_meta_cor_abaixo' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_cor_abaixo VARCHAR(20) DEFAULT '#34c759'"))
                    if 'grafico_meta_cor_acima' not in cols:
                        conn.execute(text("ALTER TABLE indicador ADD COLUMN grafico_meta_cor_acima VARCHAR(20) DEFAULT '#ff3b30'"))
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
        
        # Migração: dashboard_configuracao_alerta e alerta.dashboard_id
        try:
            from sqlalchemy import inspect, text
            db.create_all()
            insp = inspect(db.engine)
            if 'alerta' in insp.get_table_names():
                cols = [c['name'] for c in insp.get_columns('alerta')]
                if 'dashboard_id' not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE alerta ADD COLUMN dashboard_id INTEGER REFERENCES dashboard(id)"))
                        conn.commit()
            if 'dashboard_configuracao_alerta' not in insp.get_table_names():
                db.create_all()
        except Exception as e:
            logging.getLogger(__name__).warning("Migração dashboard alertas: %s", e)

        # Seed de autenticação: permissões, perfil Administrador e usuário administrador
        try:
            from app.models import User, Role, Permission
            from werkzeug.security import generate_password_hash
            import os
            db.create_all()
            # Permissões padrão (configuráveis depois pelo admin)
            permissoes_padrao = [
                ('admin', 'Administrador', 'Acesso total; criar usuários, resetar senhas e gerenciar perfis'),
                ('download.ver', 'Download - Ver', 'Visualizar página de download'),
                ('download.config', 'Download - Configurar', 'Configurar download automático'),
                ('indicadores.ver', 'Indicadores - Ver', 'Visualizar indicadores e painel'),
                ('indicadores.editar', 'Indicadores - Editar', 'Criar e editar indicadores'),
                ('dashboards.ver', 'Dashboards - Ver', 'Visualizar dashboards'),
                ('dashboards.editar', 'Dashboards - Editar', 'Criar e editar dashboards'),
                ('alertas.ver', 'Alertas - Ver', 'Visualizar alertas'),
                ('alertas.config', 'Alertas - Configurar', 'Configurar alertas'),
                ('usuarios.ver', 'Usuários - Ver', 'Listar usuários'),
                ('usuarios.criar', 'Usuários - Criar/Editar', 'Criar e editar usuários'),
                ('perfis.gerenciar', 'Perfis - Gerenciar', 'Gerenciar perfis e permissões'),
            ]
            for codigo, nome, descricao in permissoes_padrao:
                if Permission.query.filter_by(codigo=codigo).first() is None:
                    db.session.add(Permission(codigo=codigo, nome=nome, descricao=descricao))
            db.session.commit()
            # Perfil Administrador com todas as permissões
            role_admin = Role.query.filter_by(nome='Administrador').first()
            if role_admin is None:
                role_admin = Role(nome='Administrador', descricao='Acesso total ao sistema')
                db.session.add(role_admin)
                db.session.flush()
                for p in Permission.query.all():
                    role_admin.permissions.append(p)
                db.session.commit()
            # Usuário administrador inicial (senha = CPF)
            if User.query.filter_by(username='administrador').first() is None:
                cpf_admin = os.environ.get('ADMIN_CPF', '00000000000').strip()
                cpf_admin = ''.join(c for c in cpf_admin if c.isdigit()) or '00000000000'
                admin_role = Role.query.filter_by(nome='Administrador').first()
                if admin_role:
                    u = User(
                        username='administrador',
                        nome_completo='Administrador',
                        cpf=cpf_admin,
                        crm='N/A',
                        password_hash=generate_password_hash(cpf_admin),
                        role_id=admin_role.id,
                        ativo=True
                    )
                    db.session.add(u)
                    db.session.commit()
                    logging.getLogger(__name__).info('Usuário administrador criado. Login: administrador, Senha: CPF (configurado em ADMIN_CPF ou 00000000000).')
        except Exception as e:
            logging.getLogger(__name__).warning("Seed autenticação: %s", e)

        # Iniciar scheduler de downloads automáticos
        from app.download_scheduler import iniciar_scheduler
        iniciar_scheduler(app)
    
    # Registrar handlers do SocketIO
    socketio.init_app(app)
    
    return app
