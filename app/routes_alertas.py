"""
Rotas para gerenciamento de alertas
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import ConfiguracaoAlerta, Alerta, ConfiguracaoAlertasSistema
from app.gerador_alertas import gerar_alertas_automaticos
from app.indicadores import carregar_dados as carregar_dados_indicadores
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

bp_alertas = Blueprint('alertas', __name__, url_prefix='/alertas')


def _deduplicar_alertas(alertas):
    """Mantém apenas o alerta mais recente por (config_id, valor_identificado). Evita duplicados na tela."""
    vistos = set()
    resultado = []
    for a in alertas:
        det = a.get_detalhes_dict()
        vid = det.get('valor_identificado')
        vid_norm = str(vid).strip() if vid is not None else None
        if vid_norm:
            key = (a.configuracao_alerta_id, vid_norm)
            if key in vistos:
                continue
            vistos.add(key)
        resultado.append(a)
    return resultado


@bp_alertas.route('/')
def index():
    """Redireciona para o dashboard de alertas"""
    return redirect(url_for('alertas.dashboard'))


def _resolver_alertas_por_tempo():
    """Resolve alertas automáticos (sem sumir_quando_resolvido) após X minutos."""
    cfg = ConfiguracaoAlertasSistema.query.first()
    minutos = (cfg.resolver_apos_minutos if cfg else 45) or 45
    from datetime import timedelta
    limite = datetime.utcnow() - timedelta(minutes=minutos)
    configs_sem_auto = [c.id for c in ConfiguracaoAlerta.query.filter_by(sumir_quando_resolvido=False).all()]
    if not configs_sem_auto:
        return
    for a in Alerta.query.filter(Alerta.status == 'ativo', Alerta.configuracao_alerta_id.in_(configs_sem_auto), Alerta.criado_em < limite).all():
        a.status = 'resolvido'
        a.resolvido_em = datetime.utcnow()
        a.resolvido_por = 'Sistema'
    try:
        db.session.commit()
    except Exception as e:
        logger.warning("Erro ao resolver alertas por tempo: %s", e)
        db.session.rollback()


@bp_alertas.route('/api/ativos')
def api_ativos():
    """API para polling: retorna alertas ativos e config (son_notificar)."""
    _resolver_alertas_por_tempo()
    alertas_raw = Alerta.query.filter_by(status='ativo').order_by(
        Alerta.criado_em.desc()
    ).limit(100).all()
    alertas = _deduplicar_alertas(alertas_raw)[:50]
    cfg = ConfiguracaoAlertasSistema.query.first()
    som = (getattr(cfg, 'som_alerta', None) or 'beep') if cfg else 'beep'
    return jsonify({
        'alertas': [a.to_dict() for a in alertas],
        'config': {'som_alerta': som}
    })


@bp_alertas.route('/dashboard')
def dashboard():
    """Dashboard de alertas (estilo lista de mensagens)"""
    _resolver_alertas_por_tempo()
    alertas_raw = Alerta.query.filter_by(status='ativo').order_by(
        Alerta.criado_em.desc()
    ).limit(100).all()
    alertas = _deduplicar_alertas(alertas_raw)[:50]
    
    total_alertas = len(alertas)
    config_sistema = ConfiguracaoAlertasSistema.query.first()
    
    return render_template('alertas/dashboard.html', 
                         alertas=alertas, 
                         total_alertas=total_alertas,
                         config_sistema=config_sistema)


@bp_alertas.route('/config', methods=['GET', 'POST'])
def config():
    """Lista de configurações de alerta (modelo único)"""
    if request.method == 'POST' and 'resolver_apos_minutos' in request.form:
        try:
            cfg = ConfiguracaoAlertasSistema.query.first()
            if not cfg:
                cfg = ConfiguracaoAlertasSistema(resolver_apos_minutos=45)
                db.session.add(cfg)
            val = request.form.get('resolver_apos_minutos', '45').strip()
            cfg.resolver_apos_minutos = max(1, min(1440, int(val) if val.isdigit() else 45))
            transp = request.form.get('transparencia_alerta', '20').strip()
            cfg.transparencia_alerta = max(0, min(100, int(transp) if transp.isdigit() else 20))
            som = (request.form.get('som_alerta') or 'beep').strip()
            if som in ('none', 'beep', 'beep2', 'alert', 'notification', 'urgente'):
                cfg.som_alerta = som
            db.session.commit()
            flash('Configuração salva.', 'success')
        except Exception as e:
            logger.warning("Erro ao salvar config alertas: %s", e)
            db.session.rollback()
            flash('Erro ao salvar.', 'danger')
        return redirect(url_for('alertas.config'))
    config_sistema = ConfiguracaoAlertasSistema.query.first()
    configuracoes = ConfiguracaoAlerta.query.order_by(ConfiguracaoAlerta.ordem, ConfiguracaoAlerta.nome).all()
    sons_disponiveis = [
        ('none', 'Sem som'),
        ('beep', 'Beep simples'),
        ('beep2', 'Beep duplo'),
        ('alert', 'Alerta'),
        ('notification', 'Notificação'),
        ('urgente', 'Urgente'),
    ]
    return render_template('alertas/config.html', configuracoes=configuracoes, config_sistema=config_sistema, sons_disponiveis=sons_disponiveis)


# Tipos de verificação/cálculo genéricos para alertas
TIPOS_VERIFICACAO = [
    ('contar', 'Contar'),
    ('contar_unicos', 'Contar Valores Únicos'),
    ('contar_repetidos', 'Contar Repetidos'),
    ('contem', 'Contém'),
    ('nao_contem', 'Não Contém'),
    ('igual', 'Igual a'),
    ('diferente', 'Diferente de'),
    ('maior_que', 'Maior que'),
    ('menor_que', 'Menor que'),
    ('maior_igual', 'Maior ou Igual a'),
    ('menor_igual', 'Menor ou Igual a'),
    ('media', 'Média'),
    ('soma', 'Soma'),
    ('maximo', 'Máximo'),
    ('minimo', 'Mínimo'),
    ('vazio', 'É Vazio/Nulo'),
    ('nao_vazio', 'Não É Vazio'),
]
TIPOS_VERIFICACAO_CODIGOS = [t[0] for t in TIPOS_VERIFICACAO]

# Ícones Bootstrap Icons para tipos de alerta: (valor para bi-*, rótulo em PT)
# Inclui ícones de saúde, medicina de emergência, atendimento pré-hospitalar e paramédicos
ICONES_ALERTA = [
    ('exclamation-triangle', 'Alerta / Aviso'),
    ('exclamation-circle', 'Alerta círculo'),
    ('exclamation-diamond', 'Alerta diamante'),
    ('bell', 'Sino'),
    ('bell-fill', 'Sino preenchido'),
    ('lightning', 'Raio'),
    ('lightning-charge', 'Raio carga'),
    ('lightning-charge-fill', 'Raio preenchido'),
    ('cloud-rain', 'Chuva'),
    ('cloud-lightning-rain', 'Tempestade'),
    ('thermometer-high', 'Temperatura alta'),
    ('thermometer-half', 'Temperatura'),
    ('droplet', 'Gota / Umidade'),
    ('phone', 'Telefone'),
    ('phone-vibrate', 'Telefone vibrando'),
    ('phone-fill', 'Telefone preenchido'),
    ('truck', 'Caminhão / Ambulância'),
    ('car-front', 'Veículo'),
    ('heart-pulse', 'Batimento / Emergência'),
    ('heart-pulse-fill', 'Batimento preenchido'),
    ('activity', 'Atividade'),
    ('people', 'Pessoas'),
    ('people-fill', 'Pessoas preenchido'),
    ('building', 'Prédio'),
    ('geo-alt', 'Localização'),
    ('megaphone', 'Megafone'),
    ('megaphone-fill', 'Megafone preenchido'),
    ('flag', 'Bandeira'),
    ('flag-fill', 'Bandeira preenchida'),
    ('shield-exclamation', 'Escudo alerta'),
    ('clipboard-pulse', 'Prontuário / Pulso'),
    ('clipboard2-pulse', 'Prontuário 2'),
    ('calendar-event', 'Evento / Data'),
    ('graph-up-arrow', 'Gráfico subindo'),
    ('speedometer2', 'Velocímetro'),
    # Saúde e medicina de emergência
    ('bandaid', 'Primeiros socorros'),
    ('bandaid-fill', 'Primeiros socorros preenchido'),
    ('hospital', 'Hospital'),
    ('hospital-fill', 'Hospital preenchido'),
    ('file-earmark-medical', 'Prontuário médico'),
    ('file-medical', 'Arquivo médico'),
    ('journal-medical', 'Registro médico'),
    ('capsule', 'Cápsula / Medicamento'),
    ('capsule-pill', 'Medicamento'),
    ('crosshair', 'Mira / Alvo'),
    ('alarm', 'Alarme'),
    ('alarm-fill', 'Alarme preenchido'),
]

CORES_ALERTA = [
    ('#dc3545', 'Vermelho'),
    ('#fd7e14', 'Laranja'),
    ('#ffc107', 'Amarelo'),
    ('#28a745', 'Verde'),
    ('#0d6efd', 'Azul'),
    ('#6f42c1', 'Roxo'),
    ('#e83e8c', 'Rosa'),
    ('#20c997', 'Verde Água'),
    ('#6c757d', 'Cinza'),
    ('#212529', 'Preto'),
]


def _colunas_para_form():
    """Colunas da planilha para o formulário de alerta."""
    df = carregar_dados_indicadores()
    return df.columns.tolist() if df is not None else []


def _extrair_condicoes_from_form():
    """Extrai condições do form (condicao_i_coluna/operador/valor/conector)."""
    condicoes = []
    num = int(request.form.get('num_condicoes', 0) or 0)
    for i in range(num):
        coluna = request.form.get(f'condicao_{i}_coluna', '').strip()
        operador = request.form.get(f'condicao_{i}_operador', '==').strip()
        valor = request.form.get(f'condicao_{i}_valor', '').strip()
        conector = (request.form.get(f'condicao_{i}_conector') or 'and').strip().lower()
        if conector not in ('and', 'or', 'if'):
            conector = 'and'
        if coluna:
            condicoes.append({'coluna': coluna, 'operador': operador, 'valor': valor, 'conector': conector})
    return condicoes


def _extrair_configuracoes_from_form():
    """Extrai configurações dinâmicas do form (config_chave_i/config_valor_i)."""
    configuracoes = {}
    num = int(request.form.get('num_configs', 0) or 0)
    for i in range(num):
        chave = request.form.get(f'config_chave_{i}', '').strip()
        valor = request.form.get(f'config_valor_{i}', '').strip()
        # Só adiciona se chave não estiver vazia, não for campo especial, e for um tipo de verificação válido
        if chave and chave not in ['coluna_dados', 'contagem_por', 'coluna_ocorrencia']:
            # Verificar se é um tipo de verificação válido
            tipos_validos = [t[0] for t in TIPOS_VERIFICACAO]
            if chave in tipos_validos:
                # Tentar converter para número se possível, senão manter string
                try:
                    if valor and '.' in valor:
                        configuracoes[chave] = float(valor)
                    elif valor:
                        configuracoes[chave] = int(valor)
                    else:
                        configuracoes[chave] = valor  # Pode ser string vazia
                except ValueError:
                    # Se contém vírgula, pode ser lista
                    if ',' in valor:
                        configuracoes[chave] = [v.strip() for v in valor.split(',') if v.strip()]
                    else:
                        configuracoes[chave] = valor
    return configuracoes


@bp_alertas.route('/config/create', methods=['GET', 'POST'])
def create():
    """Criar nova configuração de alerta (formulário único)."""
    colunas = _colunas_para_form()
    if request.method == 'POST':
        try:
            tipo = (request.form.get('tipo', '') or '').strip()
            if not tipo:
                flash('Tipo de alerta é obrigatório.', 'danger')
                return render_template('alertas/form.html', modo='create', config=None, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)
            descricao = request.form.get('descricao', '').strip()
            ativo = request.form.get('ativo') == 'on'
            ordem = int(request.form.get('ordem', 0) or 0)
            icone = request.form.get('icone', '').strip() or 'exclamation-triangle'
            cor = request.form.get('cor', '#dc3545').strip() or '#dc3545'
            periodo_verificacao_horas = max(1, int(request.form.get('periodo_verificacao_horas', 1) or 1))
            coluna_data_filtro = request.form.get('coluna_data_filtro', '').strip() or None
            condicoes = _extrair_condicoes_from_form()
            configuracoes = _extrair_configuracoes_from_form()
            # Adicionar coluna_dados nas configurações
            coluna_dados = request.form.get('coluna_dados', '').strip()
            if coluna_dados:
                configuracoes['coluna_dados'] = coluna_dados
            # Adicionar tipo_calculo, unidade, colunas de data (igual aos indicadores)
            tipo_calculo = request.form.get('tipo_calculo', '').strip() or None
            if tipo_calculo:
                configuracoes['tipo_calculo'] = tipo_calculo
                unidade = request.form.get('unidade', 'minutos').strip()
                configuracoes['unidade'] = unidade
                if tipo_calculo in ('diferenca_tempo', 'percentual_meta', 'diferenca_ate_agora'):
                    col_inicio = request.form.get('coluna_data_inicio', '').strip() or None
                    col_fim = request.form.get('coluna_data_fim', '').strip() or None
                    if col_inicio:
                        configuracoes['coluna_data_inicio'] = col_inicio
                    if col_fim and tipo_calculo != 'diferenca_ate_agora':
                        configuracoes['coluna_data_fim'] = col_fim
                elif tipo_calculo in ('media', 'soma'):
                    col_num = request.form.get('coluna_data_fim_numerica', '').strip() or None
                    if col_num:
                        configuracoes['coluna_data_fim'] = col_num
                if tipo_calculo == 'percentual_meta':
                    meta_val = request.form.get('meta_valor', '').strip()
                    if meta_val:
                        try:
                            configuracoes['meta_valor'] = float(meta_val)
                        except ValueError:
                            pass
                    configuracoes['meta_operador'] = request.form.get('meta_operador', '<=').strip() or '<='
                elif tipo_calculo in ('diferenca_tempo', 'diferenca_ate_agora', 'contagem', 'media', 'soma'):
                    alerta_op = request.form.get('alerta_operador', '>=').strip() or '>='
                    if alerta_op in ('>=', '<=', '>', '<', '=='):
                        configuracoes['alerta_operador'] = alerta_op
                    alerta_val = request.form.get('alerta_valor', '').strip()
                    if alerta_val:
                        try:
                            configuracoes['alerta_valor'] = float(alerta_val)
                        except ValueError:
                            pass
            # Adicionar contagem_por e coluna_ocorrencia
            contagem_por = request.form.get('contagem_por', 'linhas').strip() or 'linhas'
            configuracoes['contagem_por'] = contagem_por
            if contagem_por == 'ocorrencia':
                coluna_ocorrencia = request.form.get('coluna_ocorrencia', '').strip()
                if coluna_ocorrencia:
                    configuracoes['coluna_ocorrencia'] = coluna_ocorrencia
            sumir_quando_resolvido = request.form.get('sumir_quando_resolvido') == 'on'
            config = ConfiguracaoAlerta(
                nome=tipo,  # Usa tipo como nome
                descricao=descricao,
                tipo=tipo,
                configuracoes=json.dumps(configuracoes),
                periodo_verificacao_horas=periodo_verificacao_horas,
                coluna_data_filtro=coluna_data_filtro,
                condicoes=json.dumps(condicoes) if condicoes else None,
                prioridade=3,
                icone=icone,
                cor=cor,
                ativo=ativo,
                ordem=ordem,
                sumir_quando_resolvido=sumir_quando_resolvido
            )
            db.session.add(config)
            db.session.commit()
            flash('Configuração de alerta criada com sucesso!', 'success')
            return redirect(url_for('alertas.config'))
        except Exception as e:
            logger.error(f"Erro ao criar configuração de alerta: {e}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao criar: {str(e)}', 'danger')
            return render_template('alertas/form.html', modo='create', config=None, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)
    return render_template('alertas/form.html', modo='create', config=None, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)


@bp_alertas.route('/config/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    """Editar configuração de alerta."""
    config = ConfiguracaoAlerta.query.get_or_404(id)
    colunas = _colunas_para_form()
    if request.method == 'POST':
        try:
            tipo = (request.form.get('tipo', '') or '').strip()
            if not tipo:
                flash('Tipo de alerta é obrigatório.', 'danger')
                return render_template('alertas/form.html', modo='edit', config=config, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)
            config.nome = tipo  # Usa tipo como nome
            config.descricao = request.form.get('descricao', '').strip()
            config.tipo = tipo
            config.ativo = request.form.get('ativo') == 'on'
            config.ordem = int(request.form.get('ordem', 0) or 0)
            config.icone = request.form.get('icone', '').strip() or 'exclamation-triangle'
            config.cor = request.form.get('cor', '#ff3b30').strip() or '#ff3b30'
            config.sumir_quando_resolvido = request.form.get('sumir_quando_resolvido') == 'on'
            config.periodo_verificacao_horas = max(1, int(request.form.get('periodo_verificacao_horas', 1) or 1))
            config.coluna_data_filtro = request.form.get('coluna_data_filtro', '').strip() or None
            config.condicoes = json.dumps(_extrair_condicoes_from_form()) or None
            configuracoes = _extrair_configuracoes_from_form()
            # Adicionar coluna_dados nas configurações
            coluna_dados = request.form.get('coluna_dados', '').strip()
            if coluna_dados:
                configuracoes['coluna_dados'] = coluna_dados
            # Adicionar tipo_calculo, unidade, colunas de data
            tipo_calculo = request.form.get('tipo_calculo', '').strip() or None
            if tipo_calculo:
                configuracoes['tipo_calculo'] = tipo_calculo
                unidade = request.form.get('unidade', 'minutos').strip()
                configuracoes['unidade'] = unidade
                if tipo_calculo in ('diferenca_tempo', 'percentual_meta', 'diferenca_ate_agora'):
                    col_inicio = request.form.get('coluna_data_inicio', '').strip() or None
                    col_fim = request.form.get('coluna_data_fim', '').strip() or None
                    if col_inicio:
                        configuracoes['coluna_data_inicio'] = col_inicio
                    if col_fim and tipo_calculo != 'diferenca_ate_agora':
                        configuracoes['coluna_data_fim'] = col_fim
                elif tipo_calculo in ('media', 'soma'):
                    col_num = request.form.get('coluna_data_fim_numerica', '').strip() or None
                    if col_num:
                        configuracoes['coluna_data_fim'] = col_num
                if tipo_calculo == 'percentual_meta':
                    meta_val = request.form.get('meta_valor', '').strip()
                    if meta_val:
                        try:
                            configuracoes['meta_valor'] = float(meta_val)
                        except ValueError:
                            pass
                    configuracoes['meta_operador'] = request.form.get('meta_operador', '<=').strip() or '<='
                elif tipo_calculo in ('diferenca_tempo', 'diferenca_ate_agora', 'contagem', 'media', 'soma'):
                    alerta_op = request.form.get('alerta_operador', '>=').strip() or '>='
                    if alerta_op in ('>=', '<=', '>', '<', '=='):
                        configuracoes['alerta_operador'] = alerta_op
                    alerta_val = request.form.get('alerta_valor', '').strip()
                    if alerta_val:
                        try:
                            configuracoes['alerta_valor'] = float(alerta_val)
                        except ValueError:
                            pass
            # Adicionar contagem_por e coluna_ocorrencia
            contagem_por = request.form.get('contagem_por', 'linhas').strip() or 'linhas'
            configuracoes['contagem_por'] = contagem_por
            if contagem_por == 'ocorrencia':
                coluna_ocorrencia = request.form.get('coluna_ocorrencia', '').strip()
                if coluna_ocorrencia:
                    configuracoes['coluna_ocorrencia'] = coluna_ocorrencia
            config.configuracoes = json.dumps(configuracoes)
            db.session.commit()
            flash('Configuração de alerta atualizada com sucesso!', 'success')
            return redirect(url_for('alertas.config'))
        except Exception as e:
            logger.error(f"Erro ao editar configuração de alerta: {e}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao editar: {str(e)}', 'danger')
            return render_template('alertas/form.html', modo='edit', config=config, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)
    return render_template('alertas/form.html', modo='edit', config=config, colunas=colunas, icones=ICONES_ALERTA, tipos_verificacao=TIPOS_VERIFICACAO, tipos_verificacao_codigos=TIPOS_VERIFICACAO_CODIGOS)


@bp_alertas.route('/config/duplicate/<int:id>', methods=['POST'])
def duplicate(id):
    """Duplicar configuração de alerta. Nome: copy - [nome original]."""
    config = ConfiguracaoAlerta.query.get_or_404(id)
    try:
        nome_copia = f"copy - {config.tipo}"
        copia = ConfiguracaoAlerta(
            nome=nome_copia,
            descricao=config.descricao,
            tipo=nome_copia,
            configuracoes=config.configuracoes,
            periodo_verificacao_horas=config.periodo_verificacao_horas,
            coluna_data_filtro=config.coluna_data_filtro,
            condicoes=config.condicoes,
            prioridade=config.prioridade,
            icone=config.icone,
            cor=config.cor or '#ff3b30',
            ativo=False,
            ordem=(config.ordem or 0) + 1,
            sumir_quando_resolvido=config.sumir_quando_resolvido,
        )
        db.session.add(copia)
        db.session.commit()
        flash(f'Alerta duplicado: "{nome_copia}". Edite para ajustar e ativar.', 'success')
    except Exception as e:
        logger.error(f"Erro ao duplicar configuração de alerta: {e}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao duplicar: {str(e)}', 'danger')
    return redirect(url_for('alertas.config'))


@bp_alertas.route('/config/delete/<int:id>', methods=['POST'])
def delete(id):
    """Deletar configuração de alerta. Alertas já gerados mantêm nome_tipo/icone_tipo/cor_tipo."""
    config = ConfiguracaoAlerta.query.get_or_404(id)
    try:
        db.session.delete(config)
        db.session.commit()
        flash('Configuração de alerta removida com sucesso.', 'success')
    except Exception as e:
        logger.error(f"Erro ao deletar configuração de alerta: {e}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao deletar: {str(e)}', 'danger')
    return redirect(url_for('alertas.config'))


@bp_alertas.route('/manual/create', methods=['GET', 'POST'])
def manual_create():
    """Criar alerta manual. Sempre tipo Manual, com escolha de ícone e cor."""
    if request.method == 'POST':
        try:
            titulo = request.form.get('titulo', '').strip()
            mensagem = request.form.get('mensagem', '').strip()
            if not titulo or not mensagem:
                flash('Título e mensagem são obrigatórios.', 'danger')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': 'Título e mensagem são obrigatórios.'}), 400
                return render_template('alertas/manual_form.html', icones=ICONES_ALERTA, cores=CORES_ALERTA, next_url=request.form.get('next') or request.args.get('next'))
            icone_tipo = request.form.get('icone', 'megaphone').strip() or 'megaphone'
            cor_tipo = request.form.get('cor', '#6c757d').strip() or '#6c757d'
            alerta = Alerta(
                configuracao_alerta_id=None,
                nome_tipo='Manual',
                icone_tipo=icone_tipo,
                cor_tipo=cor_tipo,
                titulo=titulo,
                mensagem=mensagem,
                prioridade=3,
                origem='manual',
                status='ativo',
                criado_por='Sistema'
            )
            db.session.add(alerta)
            db.session.commit()
            flash('Alerta criado com sucesso!', 'success')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'alerta': alerta.to_dict()})
            next_url = request.form.get('next') or request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('alertas.dashboard'))
        except Exception as e:
            logger.error(f"Erro ao criar alerta manual: {e}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao criar alerta: {str(e)}', 'danger')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': str(e)}), 400
            return render_template('alertas/manual_form.html', icones=ICONES_ALERTA, cores=CORES_ALERTA, next_url=request.form.get('next') or request.args.get('next'))
    return render_template('alertas/manual_form.html', icones=ICONES_ALERTA, cores=CORES_ALERTA, next_url=request.args.get('next'))


@bp_alertas.route('/resolver/<int:id>', methods=['POST'])
def resolver(id):
    """Resolver um alerta. Retorna JSON se for requisição AJAX (evita reload da página)."""
    alerta = Alerta.query.get_or_404(id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        alerta.status = 'resolvido'
        alerta.resolvido_em = datetime.utcnow()
        alerta.resolvido_por = 'Sistema'  # TODO: usar usuário logado
        
        db.session.commit()
        if is_ajax:
            return jsonify({'success': True})
        flash('Alerta resolvido com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao resolver alerta: {e}", exc_info=True)
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)}), 400
        flash(f'Erro ao resolver alerta: {str(e)}', 'danger')
    
    next_url = request.form.get('next') or request.args.get('next')
    if next_url:
        return redirect(next_url)
    return redirect(url_for('alertas.dashboard'))


@bp_alertas.route('/arquivar/<int:id>', methods=['POST'])
def arquivar(id):
    """Arquivar um alerta"""
    alerta = Alerta.query.get_or_404(id)
    
    try:
        alerta.status = 'arquivado'
        alerta.arquivado_em = datetime.utcnow()
        
        db.session.commit()
        flash('Alerta arquivado com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao arquivar alerta: {e}", exc_info=True)
        db.session.rollback()
        flash(f'Erro ao arquivar alerta: {str(e)}', 'danger')
    
    return redirect(url_for('alertas.dashboard'))


@bp_alertas.route('/gerar', methods=['POST'])
def gerar():
    """Gerar alertas automaticamente"""
    try:
        quantidade = gerar_alertas_automaticos()
        flash(f'{quantidade} alerta(s) gerado(s) com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao gerar alertas: {e}", exc_info=True)
        flash(f'Erro ao gerar alertas: {str(e)}', 'danger')
    
    next_url = request.form.get('next') or request.args.get('next')
    if next_url:
        return redirect(next_url)
    return redirect(url_for('alertas.dashboard'))
