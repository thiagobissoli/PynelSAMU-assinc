# Modelos do banco de dados

from app import db
from datetime import datetime
import json


def _fmt_sp(dt):
    """Formata datetime em horário de São Paulo (evita import circular no to_dict)."""
    if dt is None:
        return None
    try:
        from app.utils import formatar_data_hora_sao_paulo
        return formatar_data_hora_sao_paulo(dt)
    except Exception:
        return dt.strftime('%d/%m/%Y %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)

# Tabela de associação muitos-para-muitos
indicador_dashboard = db.Table('indicador_dashboard',
    db.Column('indicador_id', db.Integer, db.ForeignKey('indicador.id'), primary_key=True),
    db.Column('dashboard_id', db.Integer, db.ForeignKey('dashboard.id'), primary_key=True)
)

# Dashboard ↔ ConfiguracaoAlerta: quais tipos de alerta automático exibir neste dashboard
dashboard_configuracao_alerta = db.Table('dashboard_configuracao_alerta',
    db.Column('dashboard_id', db.Integer, db.ForeignKey('dashboard.id'), primary_key=True),
    db.Column('configuracao_alerta_id', db.Integer, db.ForeignKey('configuracao_alerta.id'), primary_key=True)
)

class ConfiguracaoDownload(db.Model):
    """Modelo para configuração de download automático"""
    id = db.Column(db.Integer, primary_key=True)
    ativo = db.Column(db.Boolean, default=False)
    
    # Tipo de agendamento: 'intervalo' ou 'hora_fixa'
    tipo_agendamento = db.Column(db.String(20), default='intervalo')  # intervalo, hora_fixa
    
    # Para intervalo: minutos entre downloads
    intervalo_minutos = db.Column(db.Integer, default=60)
    
    # Para hora fixa: hora do dia (0-23)
    hora_fixa = db.Column(db.Integer, nullable=True)
    
    # Dias atrás para download
    dias_atras = db.Column(db.Integer, default=1)
    
    # Última execução
    ultima_execucao = db.Column(db.DateTime, nullable=True)
    proxima_execucao = db.Column(db.DateTime, nullable=True)
    
    # Status da última execução
    ultimo_status = db.Column(db.String(20), nullable=True)  # sucesso, erro, executando
    ultimo_erro = db.Column(db.Text, nullable=True)
    
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ConfiguracaoDownload ativo={self.ativo}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'ativo': self.ativo,
            'tipo_agendamento': self.tipo_agendamento,
            'intervalo_minutos': self.intervalo_minutos,
            'hora_fixa': self.hora_fixa,
            'dias_atras': self.dias_atras,
            'ultima_execucao': _fmt_sp(self.ultima_execucao),
            'proxima_execucao': _fmt_sp(self.proxima_execucao),
            'ultimo_status': self.ultimo_status,
            'ultimo_erro': self.ultimo_erro
        }

class Dashboard(db.Model):
    """Modelo para páginas/dashboards configuráveis"""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    cor_tema = db.Column(db.String(20), default='dark')  # dark, light
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    
    # Configuração de widgets
    widgets_grid_template = db.Column(db.String(50), default='auto')  # auto, 2col, 3col, 4col, masonry
    widgets_colunas = db.Column(db.Integer, default=3)  # Número de colunas no grid
    widgets_linhas = db.Column(db.Integer, nullable=True)  # Número de linhas no grid (opcional, None = ilimitado)
    incluir_alertas = db.Column(db.Boolean, default=False)  # Na visão lista: exibir alertas no painel direito
    opacidade_area_grafico = db.Column(db.Integer, default=20)  # 0-100, % opacidade da área sob a linha do gráfico
    
    # Quais tipos de alerta automático exibir (ConfiguracaoAlerta). Vazio = todos.
    alertas_config = db.relationship('ConfiguracaoAlerta', secondary=dashboard_configuracao_alerta,
                                     backref=db.backref('dashboards', lazy='dynamic'), lazy='select')
    
    # Relacionamento muitos-para-muitos com indicadores
    indicadores = db.relationship('Indicador', secondary=indicador_dashboard, 
                                  backref=db.backref('dashboards', lazy='dynamic'))
    
    # Configurações individuais de widgets
    widgets_config = db.relationship('DashboardWidget', backref='dashboard', lazy=True, cascade='all, delete-orphan')
    
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Dashboard {self.nome}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'cor_tema': self.cor_tema,
            'ordem': self.ordem,
            'ativo': self.ativo,
            'widgets_grid_template': self.widgets_grid_template,
            'widgets_colunas': self.widgets_colunas,
            'widgets_linhas': self.widgets_linhas,
            'incluir_alertas': self.incluir_alertas,
            'opacidade_area_grafico': self.opacidade_area_grafico,
            'indicadores_ids': [ind.id for ind in self.indicadores],
            'widgets_config': [w.to_dict() for w in self.widgets_config],
            'criado_em': self.criado_em.strftime('%d/%m/%Y %H:%M:%S') if self.criado_em else None,
        }


class DashboardWidget(db.Model):
    """Configuração individual de widget no dashboard"""
    id = db.Column(db.Integer, primary_key=True)
    dashboard_id = db.Column(db.Integer, db.ForeignKey('dashboard.id'), nullable=False)
    indicador_id = db.Column(db.Integer, db.ForeignKey('indicador.id'), nullable=False)
    
    # Posição e tamanho
    ordem = db.Column(db.Integer, default=0)  # Ordem de exibição
    coluna_span = db.Column(db.Integer, default=1)  # Quantas colunas ocupa (1-4)
    linha_span = db.Column(db.Integer, default=1)  # Quantas linhas ocupa (1-4)
    
    # Tamanho do gráfico
    grafico_altura = db.Column(db.Integer, default=80)  # Altura do gráfico em pixels ou porcentagem
    
    # Posição customizada (opcional)
    posicao_x = db.Column(db.Integer, nullable=True)  # Posição X no grid
    posicao_y = db.Column(db.Integer, nullable=True)  # Posição Y no grid
    
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com indicador
    indicador = db.relationship('Indicador', backref='widget_configs')
    
    def __repr__(self):
        return f'<DashboardWidget dashboard={self.dashboard_id} indicador={self.indicador_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'indicador_id': self.indicador_id,
            'ordem': self.ordem,
            'coluna_span': self.coluna_span,
            'linha_span': self.linha_span,
            'grafico_altura': self.grafico_altura,
            'posicao_x': self.posicao_x,
            'posicao_y': self.posicao_y,
        }

class Indicador(db.Model):
    """Modelo para configuração de indicadores customizados"""
    __table_args__ = (
        db.Index('idx_indicador_ativo_ordem', 'ativo', 'ordem'),
    )
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    
    # Coluna de cálculo (ex: diferença entre duas datas)
    coluna_calculo = db.Column(db.String(100), nullable=True)  # Ex: "tempo_resposta"
    coluna_data_inicio = db.Column(db.String(100), nullable=True)  # Ex: "Data ocorrência"
    coluna_data_fim = db.Column(db.String(100), nullable=True)  # Ex: "Chegada no local"
    tipo_calculo = db.Column(db.String(50), nullable=False, default='diferenca_tempo')  # diferenca_tempo, soma, media, contagem, etc.
    
    # Condições de filtro (JSON)
    # Formato: [{"coluna": "...", "operador": "==", "valor": "...", "conector": "and"}, ...]
    condicoes = db.Column(db.Text, nullable=True)  # JSON string
    
    # Unidade de medida
    unidade = db.Column(db.String(50), nullable=True)  # Ex: "minutos", "horas", "segundos"
    
    # Filtro de tempo relativo
    filtro_ultimas_horas = db.Column(db.Integer, nullable=True)  # Ex: 2 para últimas 2 horas
    coluna_data_filtro = db.Column(db.String(100), nullable=True)  # Coluna de data para filtrar
    
    # Contagem: 'linhas' = todas as linhas; 'ocorrencia' = uma por valor na coluna_ocorrencia
    contagem_por = db.Column(db.String(20), default='linhas', nullable=True)  # 'linhas', 'ocorrencia'
    coluna_ocorrencia = db.Column(db.String(100), nullable=True)  # Ex: "Ocorrência" — identifica a ocorrência única
    
    # % que atinge a meta (tipo_calculo='percentual_meta'): valor da meta e operador (<= ou >=)
    meta_valor = db.Column(db.Float, nullable=True)  # ex.: 15 (minutos)
    meta_operador = db.Column(db.String(10), nullable=True)  # '<=' ou '>='
    
    # Configuração de gráfico
    grafico_habilitado = db.Column(db.Boolean, default=False)
    grafico_ultimas_horas = db.Column(db.Integer, nullable=True)  # Ex: 12 para gráfico das últimas 12 horas
    grafico_intervalo_minutos = db.Column(db.Integer, default=60)  # Intervalo do gráfico (ex: 60 minutos)
    # Linha histórica (dados informados pelo usuário, ex: mesmo mês ano anterior)
    grafico_historico_habilitado = db.Column(db.Boolean, default=False)
    grafico_historico_cor = db.Column(db.String(20), default='#6c757d')
    grafico_historico_dados = db.Column(db.Text, nullable=True)  # JSON: {"01": {"00": 12, ...}, "02": {...}, ...} por mês
    # Linha de meta (valor fixo, linha reta horizontal)
    grafico_meta_habilitado = db.Column(db.Boolean, default=False)
    grafico_meta_valor = db.Column(db.Float, nullable=True)
    grafico_meta_cor = db.Column(db.String(20), default='#ffc107')
    grafico_meta_estilo = db.Column(db.String(20), default='dashed')  # solid, dashed, dotted, long_dash, dash_dot
    
    # Configuração de tendência
    # tendencia_inversa = True significa que MENOR é melhor (ex: tempo de resposta)
    # tendencia_inversa = False significa que MAIOR é melhor (ex: número de atendimentos)
    tendencia_inversa = db.Column(db.Boolean, default=False)
    cor_subida = db.Column(db.String(20), default='#28a745')  # Verde padrão (padronizado)
    cor_descida = db.Column(db.String(20), default='#dc3545')  # Vermelho padrão (padronizado)
    
    # Ordem de exibição
    ordem = db.Column(db.Integer, default=0)
    
    # Status
    ativo = db.Column(db.Boolean, default=True)
    
    # Timestamps
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Indicador {self.nome}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'coluna_calculo': self.coluna_calculo,
            'coluna_data_inicio': self.coluna_data_inicio,
            'coluna_data_fim': self.coluna_data_fim,
            'tipo_calculo': self.tipo_calculo,
            'condicoes': json.loads(self.condicoes) if self.condicoes else [],
            'unidade': self.unidade,
            'filtro_ultimas_horas': self.filtro_ultimas_horas,
            'coluna_data_filtro': self.coluna_data_filtro,
            'contagem_por': self.contagem_por or 'linhas',
            'coluna_ocorrencia': self.coluna_ocorrencia,
            'meta_valor': self.meta_valor,
            'meta_operador': self.meta_operador or '<=',
            'grafico_habilitado': self.grafico_habilitado,
            'grafico_ultimas_horas': self.grafico_ultimas_horas,
            'grafico_intervalo_minutos': self.grafico_intervalo_minutos,
            'grafico_historico_habilitado': self.grafico_historico_habilitado,
            'grafico_historico_cor': self.grafico_historico_cor or '#6c757d',
            'grafico_historico_dados': json.loads(self.grafico_historico_dados) if self.grafico_historico_dados else {},
            'grafico_meta_habilitado': self.grafico_meta_habilitado,
            'grafico_meta_valor': self.grafico_meta_valor,
            'grafico_meta_cor': self.grafico_meta_cor or '#ffc107',
            'grafico_meta_estilo': self.grafico_meta_estilo or 'dashed',
            'tendencia_inversa': self.tendencia_inversa,
            'cor_subida': self.cor_subida or '#28a745',
            'cor_descida': self.cor_descida or '#dc3545',
            'ordem': self.ordem,
            'ativo': self.ativo,
            'criado_em': self.criado_em.strftime('%d/%m/%Y %H:%M:%S') if self.criado_em else None,
            'atualizado_em': self.atualizado_em.strftime('%d/%m/%Y %H:%M:%S') if self.atualizado_em else None
        }
    
    def get_condicoes_dict(self):
        """Retorna as condições como dicionário"""
        if self.condicoes:
            try:
                return json.loads(self.condicoes)
            except:
                return []
        return []

    def get_historico_dados_dict(self):
        """Retorna os dados da linha histórica. Formato novo: {mes: {hora: valor}}. Formato antigo: {hora: valor}."""
        if self.grafico_historico_dados:
            try:
                return json.loads(self.grafico_historico_dados)
            except:
                return {}
        return {}

    def get_historico_dados_mes(self, mes):
        """Retorna dados da linha histórica para o mês (1-12). Formato novo: por mês. Formato antigo: único conjunto."""
        data = self.get_historico_dados_dict()
        if not data:
            return {}
        mes_key = f'{mes:02d}'
        if mes_key in data and isinstance(data[mes_key], dict):
            return data[mes_key]
        if all(len(k) == 2 and k.isdigit() and int(k) < 24 for k in data.keys()):
            return data
        return {}


class ConfiguracaoAlerta(db.Model):
    """Configuração única de alerta (tipo + regra no mesmo registro)."""
    __tablename__ = 'configuracao_alerta'
    __table_args__ = (
        db.Index('idx_config_alerta_ativo_ordem', 'ativo', 'ordem'),
    )
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.String(50), nullable=False)  # multiplos_chamados, tempo_resposta_municipio, clima_tempo, apoio_instituicoes, alta_demanda, tempo_resposta_elevado
    configuracoes = db.Column(db.Text, nullable=True)  # JSON string
    periodo_verificacao_horas = db.Column(db.Integer, default=1)
    coluna_data_filtro = db.Column(db.String(100), nullable=True)
    condicoes = db.Column(db.Text, nullable=True)  # JSON
    prioridade = db.Column(db.Integer, default=3)
    icone = db.Column(db.String(50), nullable=True)
    cor = db.Column(db.String(20), default='#ff3b30')
    ativo = db.Column(db.Boolean, default=True)
    ordem = db.Column(db.Integer, default=0)
    sumir_quando_resolvido = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<ConfiguracaoAlerta {self.nome}>'

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'tipo': self.tipo,
            'configuracoes': json.loads(self.configuracoes) if self.configuracoes else {},
            'periodo_verificacao_horas': self.periodo_verificacao_horas,
            'coluna_data_filtro': self.coluna_data_filtro,
            'condicoes': json.loads(self.condicoes) if self.condicoes else [],
            'ativo': self.ativo,
            'prioridade': self.prioridade,
            'icone': self.icone,
            'cor': self.cor,
            'ordem': self.ordem,
            'sumir_quando_resolvido': self.sumir_quando_resolvido
        }

    def get_configuracoes_dict(self):
        if self.configuracoes:
            try:
                return json.loads(self.configuracoes)
            except Exception:
                return {}
        return {}

    def get_condicoes_dict(self):
        if self.condicoes:
            try:
                return json.loads(self.condicoes)
            except Exception:
                return []
        return []


class ConfiguracaoAlertasSistema(db.Model):
    """Configurações globais do módulo de alertas (uma única linha)."""
    __tablename__ = 'configuracao_alertas_sistema'
    id = db.Column(db.Integer, primary_key=True)
    resolver_apos_minutos = db.Column(db.Integer, default=45)
    som_alerta = db.Column(db.String(50), default='beep')  # none, beep, beep2, alert, notification, urgente
    transparencia_alerta = db.Column(db.Integer, default=20)  # 0-100, % opacidade do fundo
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Alerta(db.Model):
    """Alerta disparado (instância)."""
    __tablename__ = 'alerta'
    __table_args__ = (
        db.Index('idx_alerta_status_criado', 'status', 'criado_em'),
        db.Index('idx_alerta_origem_dashboard', 'origem', 'dashboard_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    configuracao_alerta_id = db.Column(db.Integer, db.ForeignKey('configuracao_alerta.id'), nullable=True)
    nome_tipo = db.Column(db.String(200), nullable=True)  # preenchido na geração para exibição
    icone_tipo = db.Column(db.String(50), nullable=True)
    cor_tipo = db.Column(db.String(20), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    mensagem = db.Column(db.Text, nullable=False)
    detalhes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='ativo')
    prioridade = db.Column(db.Integer, default=3)
    origem = db.Column(db.String(50), default='automatico')
    dashboard_id = db.Column(db.Integer, db.ForeignKey('dashboard.id'), nullable=True)  # Para alertas manuais: qual dashboard
    data_ocorrencia = db.Column(db.DateTime, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    resolvido_em = db.Column(db.DateTime, nullable=True)
    arquivado_em = db.Column(db.DateTime, nullable=True)
    criado_por = db.Column(db.String(100), nullable=True)
    resolvido_por = db.Column(db.String(100), nullable=True)

    configuracao_alerta = db.relationship('ConfiguracaoAlerta', backref=db.backref('alertas', lazy=True))
    dashboard = db.relationship('Dashboard', backref=db.backref('alertas_manuais', lazy='dynamic'))

    def __repr__(self):
        return f'<Alerta {self.titulo}>'

    def to_dict(self):
        return {
            'id': self.id,
            'configuracao_alerta_id': self.configuracao_alerta_id,
            'tipo_alerta_nome': self.nome_tipo,
            'tipo_alerta_icone': self.icone_tipo,
            'tipo_alerta_cor': self.cor_tipo or '#ff3b30',
            'titulo': self.titulo,
            'mensagem': self.mensagem,
            'detalhes': json.loads(self.detalhes) if self.detalhes else {},
            'status': self.status,
            'prioridade': self.prioridade,
            'origem': self.origem,
            'dashboard_id': self.dashboard_id,
            'data_ocorrencia': _fmt_sp(self.data_ocorrencia),
            'criado_em': _fmt_sp(self.criado_em),
            'resolvido_em': _fmt_sp(self.resolvido_em),
            'criado_por': self.criado_por,
            'resolvido_por': self.resolvido_por
        }

    def get_detalhes_dict(self):
        if self.detalhes:
            try:
                return json.loads(self.detalhes)
            except Exception:
                return {}
        return {}
