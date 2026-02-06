"""
Módulo para geração automática de alertas baseado em regras configuradas
"""

import pandas as pd
import logging
from datetime import datetime, timedelta
import pytz
import json
import requests
from app import db
from app.models import Alerta, ConfiguracaoAlerta
from app.indicadores import carregar_dados
from app.calculo_indicadores import aplicar_condicao, filtrar_dataframe, calcular_indicador, calcular_diferenca_ate_agora

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')


def _normalizar_valor_identificado(val):
    """Normaliza valor para comparação (evita 28999614877 vs 28999614877.0)."""
    s = str(val).strip()
    if s.endswith('.0') and s[:-2].replace('-', '').isdigit():
        return s[:-2]
    return s


def _alerta_existe_valor_identificado(config_id, valor_identificado):
    """Verifica se já existe alerta ativo com este valor_identificado (json.dumps usa ": " com espaço)."""
    v = _normalizar_valor_identificado(valor_identificado)
    v_float = v + '.0'  # pandas pode retornar float
    conds = [
        Alerta.detalhes.like(f'%"valor_identificado": "{v}"%'),
        Alerta.detalhes.like(f'%"valor_identificado":"{v}"%'),
        Alerta.detalhes.like(f'%"valor_identificado": "{v_float}"%'),
        Alerta.detalhes.like(f'%"valor_identificado": {v}%'),
    ]
    return Alerta.query.filter_by(configuracao_alerta_id=config_id, status='ativo').filter(
        db.or_(*conds)
    ).first() is not None


def _alerta_existe_numero_ocorrencia(config_id, numero_ocorrencia, tipo_verif):
    """Verifica se já existe alerta ativo com este numero_ocorrencia e tipo_verificacao."""
    n = str(numero_ocorrencia)
    t = str(tipo_verif)
    return Alerta.query.filter_by(configuracao_alerta_id=config_id, status='ativo').filter(
        db.or_(
            Alerta.detalhes.like(f'%"numero_ocorrencia": "{n}"%'),
            Alerta.detalhes.like(f'%"numero_ocorrencia":"{n}"%')
        )
    ).filter(
        db.or_(
            Alerta.detalhes.like(f'%"tipo_verificacao": "{t}"%'),
            Alerta.detalhes.like(f'%"tipo_verificacao":"{t}"%')
        )
    ).first() is not None


def _formatar_valor_tempo(valor, unidade='minutos'):
    """Formata valor numérico como tempo legível (ex: 76.31 min -> 1h 16min)."""
    if valor is None:
        return ''
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if unidade in ('minutos', 'min'):
        if v >= 60:
            h, m = int(v // 60), int(round(v % 60))
            return f"{h}h {m}min" if m else f"{h}h"
        return f"{int(round(v))} min"
    if unidade in ('horas', 'h'):
        if v >= 1:
            h, m = int(v), int(round((v % 1) * 60))
            return f"{h}h {m}min" if m else f"{h}h"
        return f"{int(round(v * 60))} min"
    if unidade in ('segundos', 's'):
        if v >= 60:
            m, s = int(v // 60), int(round(v % 60))
            return f"{m}min {s}s" if s else f"{m}min"
        return f"{int(round(v))}s"
    return f"{v:.1f} {unidade}"


def gerar_alertas_automaticos():
    """
    Gera alertas automaticamente baseado nas configurações ativas
    Retorna a quantidade de alertas gerados
    """
    configuracoes = ConfiguracaoAlerta.query.filter_by(ativo=True).all()
    
    if not configuracoes:
        logger.info("Nenhuma configuração de alerta ativa encontrada")
        return 0
    
    # Carregar dados
    df = carregar_dados()
    if df is None or df.empty:
        logger.warning("Não foi possível carregar dados para gerar alertas")
        return 0
    
    alertas_gerados = 0
    
    for config in configuracoes:
        try:
            tipo_codigo = (config.tipo or '').strip()
            if not tipo_codigo:
                continue

            # Gerar alerta baseado no tipo (suporta tipos pré-definidos e customizados)
            # Tipos pré-definidos mantidos para compatibilidade
            if tipo_codigo == 'multiplos_chamados':
                alertas_gerados += gerar_alerta_multiplos_chamados(config, df)
            elif tipo_codigo == 'tempo_resposta_municipio':
                alertas_gerados += gerar_alerta_tempo_resposta_municipio(config, df)
            elif tipo_codigo == 'clima_tempo':
                alertas_gerados += gerar_alerta_clima_tempo(config)
            elif tipo_codigo == 'apoio_instituicoes':
                alertas_gerados += gerar_alerta_apoio_instituicoes(config, df)
            elif tipo_codigo == 'alta_demanda':
                alertas_gerados += gerar_alerta_alta_demanda(config, df)
            elif tipo_codigo == 'tempo_resposta_elevado':
                alertas_gerados += gerar_alerta_tempo_resposta_elevado(config, df)
            else:
                # Tipo customizado - usar lógica genérica
                alertas_gerados += gerar_alerta_generico(config, df)
            
        except Exception as e:
            logger.error(f"Erro ao gerar alerta para configuração {config.id}: {e}", exc_info=True)
            continue
    
    resolver_alertas_automaticos(df)
    return alertas_gerados


def resolver_alertas_automaticos(df):
    """
    Resolve automaticamente alertas cuja condição de criação não existe mais nos dados.
    Só aplica a configurações com sumir_quando_resolvido=True.
    """
    if df is None or df.empty:
        return 0
    configs = ConfiguracaoAlerta.query.filter_by(ativo=True, sumir_quando_resolvido=True).all()
    total_resolvidos = 0
    for config in configs:
        try:
            total_resolvidos += _resolver_alertas_config(config, df)
        except Exception as e:
            logger.error(f"Erro ao resolver alertas da configuração {config.id}: {e}", exc_info=True)
    if total_resolvidos > 0:
        db.session.commit()
    return total_resolvidos


def _resolver_alertas_config(config, df):
    """Resolve alertas ativos de uma config quando a condição não existe mais."""
    alertas_ativos = Alerta.query.filter_by(configuracao_alerta_id=config.id, status='ativo').all()
    if not alertas_ativos:
        return 0
    tipo_codigo = (config.tipo or '').strip()
    resolvidos = 0
    if tipo_codigo == 'multiplos_chamados':
        resolvidos = _resolver_multiplos_chamados(config, df, alertas_ativos)
    elif tipo_codigo in ('tempo_resposta_municipio', 'tempo_resposta_elevado'):
        resolvidos = _resolver_tempo_resposta(config, df, alertas_ativos)
    else:
        resolvidos = _resolver_generico(config, df, alertas_ativos)
    return resolvidos


def _resolver_multiplos_chamados(config, df, alertas_ativos):
    """Resolve alertas de múltiplos chamados quando o telefone não tem mais chamados suficientes."""
    cfg = config.get_configuracoes_dict()
    quantidade_minima = cfg.get('quantidade_minima', 3)
    coluna_telefone = cfg.get('coluna_telefone', 'Telefone')
    if coluna_telefone not in df.columns:
        return 0
    periodo_horas = config.periodo_verificacao_horas
    df_filtrado = df
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        df_cp = df.copy()
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        df_cp[config.coluna_data_filtro] = pd.to_datetime(df_cp[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df_cp[config.coluna_data_filtro].dt.tz is None:
            df_cp[config.coluna_data_filtro] = df_cp[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        df_filtrado = df_cp[df_cp[config.coluna_data_filtro] >= limite]
    telefones_contagem = df_filtrado[coluna_telefone].value_counts()
    telefones_que_acionam = set(telefones_contagem[telefones_contagem >= quantidade_minima].index.astype(str))
    resolvidos = 0
    for alerta in alertas_ativos:
        try:
            det = alerta.get_detalhes_dict()
            telefone = str(det.get('telefone', ''))
            if telefone and telefone not in telefones_que_acionam:
                alerta.status = 'resolvido'
                alerta.resolvido_em = datetime.utcnow()
                alerta.resolvido_por = 'Sistema'
                resolvidos += 1
        except Exception:
            pass
    return resolvidos


def _resolver_tempo_resposta(config, df, alertas_ativos):
    """Resolve alertas de tempo de resposta quando o município não tem mais tempo elevado."""
    cfg = config.get_configuracoes_dict()
    coluna_municipio = cfg.get('coluna_municipio', 'Município')
    tempo_maximo = cfg.get('tempo_maximo_minutos', 15)
    if coluna_municipio not in df.columns:
        return 0
    resolvidos = 0
    for alerta in alertas_ativos:
        try:
            det = alerta.get_detalhes_dict()
            municipio = det.get('municipio', '')
            if not municipio:
                continue
            df_mun = df[df[coluna_municipio].astype(str) == str(municipio)]
            if df_mun.empty:
                alerta.status = 'resolvido'
                alerta.resolvido_em = datetime.utcnow()
                alerta.resolvido_por = 'Sistema'
                resolvidos += 1
                continue
            col_inicio = cfg.get('coluna_data_inicio', 'Data ocorrência')
            col_fim = cfg.get('coluna_data_fim', 'Chegada no local')
            if col_inicio in df_mun.columns and col_fim in df_mun.columns:
                df_mun = df_mun.copy()
                df_mun[col_inicio] = pd.to_datetime(df_mun[col_inicio], errors='coerce')
                df_mun[col_fim] = pd.to_datetime(df_mun[col_fim], errors='coerce')
                diff = (df_mun[col_fim] - df_mun[col_inicio]).dt.total_seconds() / 60
                media = diff.mean()
                if pd.isna(media) or media <= tempo_maximo:
                    alerta.status = 'resolvido'
                    alerta.resolvido_em = datetime.utcnow()
                    alerta.resolvido_por = 'Sistema'
                    resolvidos += 1
        except Exception:
            pass
    return resolvidos


def _resolver_generico(config, df, alertas_ativos):
    """Resolve alertas genéricos quando valor_identificado não atende mais à condição."""
    cfg = config.get_configuracoes_dict()
    tipo_calculo = cfg.get('tipo_calculo')
    coluna_dados = cfg.get('coluna_dados')
    # diferenca_ate_agora: resolver quando a unidade não excede mais o limite
    if tipo_calculo == 'diferenca_ate_agora':
        return _resolver_diferenca_ate_agora(config, df, alertas_ativos)
    if not coluna_dados or coluna_dados not in df.columns:
        return 0
    df_filtrado = filtrar_dataframe(df, config.get_condicoes_dict(), 
        config.periodo_verificacao_horas, config.coluna_data_filtro)
    contagem_por_valor = df_filtrado[coluna_dados].value_counts()
    resolvidos = 0
    for alerta in alertas_ativos:
        try:
            det = alerta.get_detalhes_dict()
            valor_id = det.get('valor_identificado') or det.get('telefone')
            if valor_id is None:
                continue
            valor_id = str(valor_id)
            tipo_verif = det.get('tipo_verificacao', 'contar')
            valor_limite = det.get('valor_limite')
            qtd_atual = contagem_por_valor.get(valor_id, 0)
            if pd.isna(qtd_atual):
                qtd_atual = 0
            else:
                qtd_atual = int(qtd_atual)
            ainda_aciona = False
            if tipo_verif in ('contar', 'contar_repetidos', 'contem', 'igual'):
                limite = float(valor_limite) if valor_limite else 1
                ainda_aciona = qtd_atual >= limite
            elif tipo_verif == 'contar_unicos':
                limite = float(valor_limite) if valor_limite else 0
                ainda_aciona = df_filtrado[coluna_dados].nunique() >= limite
            if not ainda_aciona:
                alerta.status = 'resolvido'
                alerta.resolvido_em = datetime.utcnow()
                alerta.resolvido_por = 'Sistema'
                resolvidos += 1
        except Exception:
            pass
    return resolvidos


def _resolver_diferenca_ate_agora(config, df, alertas_ativos):
    """Resolve alertas de diferenca_ate_agora quando a unidade não excede mais o limite."""
    cfg = config.get_configuracoes_dict()
    alerta_valor = cfg.get('alerta_valor')
    coluna_unidade = cfg.get('coluna_dados')
    col_data = cfg.get('coluna_data_inicio')
    if not alerta_valor or not col_data or col_data not in df.columns:
        return 0
    df_filt = filtrar_dataframe(df, config.get_condicoes_dict(), config.periodo_verificacao_horas, config.coluna_data_filtro)
    diffs = calcular_diferenca_ate_agora(df_filt, col_data, cfg.get('unidade', 'minutos'))
    mask = diffs >= float(alerta_valor)
    if not mask.any():
        unidades_excedentes = set()
        algum_excede = False
    else:
        algum_excede = True
        if coluna_unidade and coluna_unidade in df.columns:
            unidades_excedentes = set(df_filt.loc[mask[mask].index, coluna_unidade].dropna().astype(str).unique())
        else:
            unidades_excedentes = set()
    resolvidos = 0
    for alerta in alertas_ativos:
        try:
            det = alerta.get_detalhes_dict()
            if det.get('tipo_calculo') != 'diferenca_ate_agora':
                continue
            unit_val = det.get('valor_identificado')
            if unit_val is not None:
                unit_val = str(unit_val)
                if unit_val not in unidades_excedentes:
                    alerta.status = 'resolvido'
                    alerta.resolvido_em = datetime.utcnow()
                    alerta.resolvido_por = 'Sistema'
                    resolvidos += 1
            else:
                if not algum_excede:
                    alerta.status = 'resolvido'
                    alerta.resolvido_em = datetime.utcnow()
                    alerta.resolvido_por = 'Sistema'
                    resolvidos += 1
        except Exception:
            pass
    return resolvidos


def gerar_alerta_multiplos_chamados(config, df):
    """Gera alerta para múltiplos chamados do mesmo número"""
    configuracoes = config.get_configuracoes_dict()
    quantidade_minima = configuracoes.get('quantidade_minima', 3)
    coluna_telefone = configuracoes.get('coluna_telefone', 'Telefone')
    periodo_horas = config.periodo_verificacao_horas
    
    if coluna_telefone not in df.columns:
        logger.warning(f"Coluna '{coluna_telefone}' não encontrada")
        return 0
    
    # Filtrar por período
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        
        df[config.coluna_data_filtro] = pd.to_datetime(df[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df[config.coluna_data_filtro].dt.tz is None:
            df[config.coluna_data_filtro] = df[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df[df[config.coluna_data_filtro] >= limite]
    else:
        df_filtrado = df
    
    # Contar chamados por telefone
    telefones_contagem = df_filtrado[coluna_telefone].value_counts()
    telefones_alertas = telefones_contagem[telefones_contagem >= quantidade_minima]
    
    alertas_gerados = 0
    for telefone, quantidade in telefones_alertas.items():
        # Verificar se já existe alerta ativo para este telefone
        alerta_existente = Alerta.query.filter_by(
            configuracao_alerta_id=config.id,
            status='ativo'
        ).filter(
            Alerta.detalhes.like(f'%"{telefone}"%')
        ).first()
        
        if alerta_existente:
            continue  # Já existe alerta ativo
        
        # Criar alerta
        alerta = Alerta(
            configuracao_alerta_id=config.id,
            nome_tipo=config.nome,
            icone_tipo=config.icone or 'exclamation-triangle',
            cor_tipo=config.cor or '#ff3b30',
            titulo=f'Múltiplos chamados - {telefone}',
            mensagem=f'O número {telefone} realizou {quantidade} chamado(s) nas últimas {periodo_horas} hora(s).',
            detalhes=json.dumps({
                'telefone': str(telefone),
                'quantidade': int(quantidade),
                'periodo_horas': periodo_horas
            }),
            prioridade=config.prioridade,
            origem='automatico',
            status='ativo',
            data_ocorrencia=datetime.now(brasilia_tz)
        )
        
        db.session.add(alerta)
        alertas_gerados += 1
    
    db.session.commit()
    return alertas_gerados


def gerar_alerta_tempo_resposta_municipio(config, df):
    """Gera alerta para tempo de resposta elevado por município"""
    configuracoes = config.get_configuracoes_dict()
    municipios = configuracoes.get('municipios', [])
    tempo_maximo = configuracoes.get('tempo_maximo_minutos', 15)
    coluna_municipio = configuracoes.get('coluna_municipio', 'Município')
    coluna_data_inicio = configuracoes.get('coluna_data_inicio', 'Data ocorrência')
    coluna_data_fim = configuracoes.get('coluna_data_fim', 'Chegada no local')
    periodo_horas = config.periodo_verificacao_horas
    
    if not municipios or coluna_municipio not in df.columns:
        return 0
    
    # Filtrar por período
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        
        df[config.coluna_data_filtro] = pd.to_datetime(df[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df[config.coluna_data_filtro].dt.tz is None:
            df[config.coluna_data_filtro] = df[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df[df[config.coluna_data_filtro] >= limite]
    else:
        df_filtrado = df
    
    # Filtrar por municípios
    df_filtrado = df_filtrado[df_filtrado[coluna_municipio].isin(municipios)]
    
    if df_filtrado.empty:
        return 0
    
    # Calcular tempo de resposta
    if coluna_data_inicio in df_filtrado.columns and coluna_data_fim in df_filtrado.columns:
        df_filtrado[coluna_data_inicio] = pd.to_datetime(df_filtrado[coluna_data_inicio], errors='coerce', dayfirst=True)
        df_filtrado[coluna_data_fim] = pd.to_datetime(df_filtrado[coluna_data_fim], errors='coerce', dayfirst=True)
        
        # Calcular diferença em minutos
        diferenca = (df_filtrado[coluna_data_fim] - df_filtrado[coluna_data_inicio]).dt.total_seconds() / 60
        
        # Filtrar apenas os que excedem o tempo máximo
        df_alertas = df_filtrado[diferenca > tempo_maximo]
        
        alertas_gerados = 0
        for municipio in municipios:
            df_municipio = df_alertas[df_alertas[coluna_municipio] == municipio]
            
            if df_municipio.empty:
                continue
            
            # Verificar se já existe alerta ativo para este município
            alerta_existente = Alerta.query.filter_by(
                configuracao_alerta_id=config.id,
                status='ativo'
            ).filter(
                Alerta.detalhes.like(f'%"{municipio}"%')
            ).first()
            
            if alerta_existente:
                continue
            
            quantidade = len(df_municipio)
            tempo_medio = diferenca[df_municipio.index].mean()
            
            alerta = Alerta(
                configuracao_alerta_id=config.id,
                nome_tipo=config.nome,
                icone_tipo=config.icone or 'exclamation-triangle',
                cor_tipo=config.cor or '#ff3b30',
                titulo=f'Tempo de resposta elevado - {municipio}',
                mensagem=f'{quantidade} ocorrência(s) em {municipio} com tempo de resposta acima de {tempo_maximo} minutos (média: {tempo_medio:.1f} min).',
                detalhes=json.dumps({
                    'municipio': municipio,
                    'quantidade': int(quantidade),
                    'tempo_medio': float(tempo_medio),
                    'tempo_maximo': tempo_maximo
                }),
                prioridade=config.prioridade,
                origem='automatico',
                status='ativo',
                data_ocorrencia=datetime.now(brasilia_tz)
            )
            
            db.session.add(alerta)
            alertas_gerados += 1
        
        db.session.commit()
        return alertas_gerados
    
    return 0


def gerar_alerta_clima_tempo(config):
    """Gera alerta baseado em condições climáticas (API Clima Tempo)"""
    configuracoes = config.get_configuracoes_dict()
    cidade = configuracoes.get('cidade', '')
    api_key = configuracoes.get('api_key', '')
    condicoes = configuracoes.get('condicoes', [])
    
    if not cidade or not api_key or not condicoes:
        return 0
    
    try:
        # Buscar dados da API Clima Tempo
        # Nota: Esta é uma API exemplo, pode precisar ser ajustada conforme a API real
        url = f"http://apiadvisor.climatempo.com.br/api/v1/forecast/locale/{cidade}/days/15?token={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Erro ao buscar dados do Clima Tempo: {response.status_code}")
            return 0
        
        data = response.json()
        
        # Verificar condições (exemplo simplificado)
        alertas_gerados = 0
        for dia in data.get('data', [])[:3]:  # Próximos 3 dias
            texto = dia.get('text_icon', {}).get('text', {}).get('pt', '').lower()
            
            for condicao in condicoes:
                if condicao.lower() in texto:
                    # Verificar se já existe alerta ativo
                    alerta_existente = Alerta.query.filter_by(
                        configuracao_alerta_id=config.id,
                        status='ativo'
                    ).filter(
                        Alerta.detalhes.like(f'%"{condicao}"%')
                    ).first()
                    
                    if alerta_existente:
                        continue
                    
                    data_previsao = dia.get('date_br', '')
                    alerta = Alerta(
                        configuracao_alerta_id=config.id,
                        nome_tipo=config.nome,
                        icone_tipo=config.icone or 'exclamation-triangle',
                        cor_tipo=config.cor or '#ff3b30',
                        titulo=f'Alerta climático - {condicao.title()}',
                        mensagem=f'Previsão de {condicao} para {data_previsao} em {cidade}.',
                        detalhes=json.dumps({
                            'cidade': cidade,
                            'condicao': condicao,
                            'data': data_previsao,
                            'texto': texto
                        }),
                        prioridade=config.prioridade,
                        origem='api',
                        status='ativo',
                        data_ocorrencia=datetime.now(brasilia_tz)
                    )
                    
                    db.session.add(alerta)
                    alertas_gerados += 1
                    break
        
        db.session.commit()
        return alertas_gerados
        
    except Exception as e:
        logger.error(f"Erro ao gerar alerta de clima: {e}", exc_info=True)
        return 0


def gerar_alerta_apoio_instituicoes(config, df):
    """Gera alerta para solicitações de apoio de outras instituições"""
    configuracoes = config.get_configuracoes_dict()
    instituicoes = configuracoes.get('instituicoes', [])
    coluna_apoio = configuracoes.get('coluna_apoio', 'Apoio')
    periodo_horas = config.periodo_verificacao_horas
    
    if not instituicoes or coluna_apoio not in df.columns:
        return 0
    
    # Filtrar por período
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        
        df[config.coluna_data_filtro] = pd.to_datetime(df[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df[config.coluna_data_filtro].dt.tz is None:
            df[config.coluna_data_filtro] = df[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df[df[config.coluna_data_filtro] >= limite]
    else:
        df_filtrado = df
    
    alertas_gerados = 0
    for instituicao in instituicoes:
        # Filtrar por instituição (pode ser substring)
        df_instituicao = df_filtrado[df_filtrado[coluna_apoio].astype(str).str.contains(instituicao, case=False, na=False)]
        
        if df_instituicao.empty:
            continue
        
        quantidade = len(df_instituicao)
        
        # Verificar se já existe alerta ativo
        alerta_existente = Alerta.query.filter_by(
            configuracao_alerta_id=config.id,
            status='ativo'
        ).filter(
            Alerta.detalhes.like(f'%"{instituicao}"%')
        ).first()
        
        if alerta_existente:
            continue
        
        alerta = Alerta(
            configuracao_alerta_id=config.id,
            nome_tipo=config.nome,
            icone_tipo=config.icone or 'exclamation-triangle',
            cor_tipo=config.cor or '#ff3b30',
            titulo=f'Solicitação de apoio - {instituicao}',
            mensagem=f'{quantidade} solicitação(ões) de apoio de {instituicao} nas últimas {periodo_horas} hora(s).',
            detalhes=json.dumps({
                'instituicao': instituicao,
                'quantidade': int(quantidade),
                'periodo_horas': periodo_horas
            }),
            prioridade=config.prioridade,
            origem='automatico',
            status='ativo',
            data_ocorrencia=datetime.now(brasilia_tz)
        )
        
        db.session.add(alerta)
        alertas_gerados += 1
    
    db.session.commit()
    return alertas_gerados


def gerar_alerta_alta_demanda(config, df):
    """Gera alerta para alta demanda de ocorrências"""
    configuracoes = config.get_configuracoes_dict()
    quantidade_minima = configuracoes.get('quantidade_minima', 50)
    periodo_horas = config.periodo_verificacao_horas
    
    # Filtrar por período
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        
        df[config.coluna_data_filtro] = pd.to_datetime(df[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df[config.coluna_data_filtro].dt.tz is None:
            df[config.coluna_data_filtro] = df[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df[df[config.coluna_data_filtro] >= limite]
    else:
        df_filtrado = df
    
    quantidade = len(df_filtrado)
    
    if quantidade >= quantidade_minima:
        # Verificar se já existe alerta ativo
        alerta_existente = Alerta.query.filter_by(
            configuracao_alerta_id=config.id,
            status='ativo'
        ).first()
        
        if alerta_existente:
            return 0
        
        alerta = Alerta(
            configuracao_alerta_id=config.id,
            nome_tipo=config.nome,
            icone_tipo=config.icone or 'exclamation-triangle',
            cor_tipo=config.cor or '#ff3b30',
            titulo=f'Alta demanda de ocorrências',
            mensagem=f'{quantidade} ocorrência(s) registrada(s) nas últimas {periodo_horas} hora(s).',
            detalhes=json.dumps({
                'quantidade': int(quantidade),
                'periodo_horas': periodo_horas,
                'quantidade_minima': quantidade_minima
            }),
            prioridade=config.prioridade,
            origem='automatico',
            status='ativo',
            data_ocorrencia=datetime.now(brasilia_tz)
        )
        
        db.session.add(alerta)
        db.session.commit()
        return 1
    
    return 0


def gerar_alerta_tempo_resposta_elevado(config, df):
    """Gera alerta para tempo de resposta geral elevado"""
    configuracoes = config.get_configuracoes_dict()
    tempo_maximo = configuracoes.get('tempo_maximo_minutos', 20)
    coluna_data_inicio = configuracoes.get('coluna_data_inicio', 'Data ocorrência')
    coluna_data_fim = configuracoes.get('coluna_data_fim', 'Chegada no local')
    periodo_horas = config.periodo_verificacao_horas
    
    # Filtrar por período
    if config.coluna_data_filtro and config.coluna_data_filtro in df.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=periodo_horas)
        
        df[config.coluna_data_filtro] = pd.to_datetime(df[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df[config.coluna_data_filtro].dt.tz is None:
            df[config.coluna_data_filtro] = df[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df[df[config.coluna_data_filtro] >= limite]
    else:
        df_filtrado = df
    
    if df_filtrado.empty:
        return 0
    
    # Calcular tempo de resposta
    if coluna_data_inicio in df_filtrado.columns and coluna_data_fim in df_filtrado.columns:
        df_filtrado[coluna_data_inicio] = pd.to_datetime(df_filtrado[coluna_data_inicio], errors='coerce', dayfirst=True)
        df_filtrado[coluna_data_fim] = pd.to_datetime(df_filtrado[coluna_data_fim], errors='coerce', dayfirst=True)
        
        diferenca = (df_filtrado[coluna_data_fim] - df_filtrado[coluna_data_inicio]).dt.total_seconds() / 60
        tempo_medio = diferenca.mean()
        
        if tempo_medio > tempo_maximo:
            # Verificar se já existe alerta ativo
            alerta_existente = Alerta.query.filter_by(
                configuracao_alerta_id=config.id,
                status='ativo'
            ).first()
            
            if alerta_existente:
                return 0
            
            quantidade = len(df_filtrado)
            alerta = Alerta(
                configuracao_alerta_id=config.id,
                nome_tipo=config.nome,
                icone_tipo=config.icone or 'exclamation-triangle',
                cor_tipo=config.cor or '#ff3b30',
                titulo=f'Tempo de resposta geral elevado',
                mensagem=f'Tempo médio de resposta de {tempo_medio:.1f} minutos nas últimas {periodo_horas} hora(s) ({quantidade} ocorrências).',
                detalhes=json.dumps({
                    'tempo_medio': float(tempo_medio),
                    'tempo_maximo': tempo_maximo,
                    'quantidade': int(quantidade),
                    'periodo_horas': periodo_horas
                }),
                prioridade=config.prioridade,
                origem='automatico',
                status='ativo',
                data_ocorrencia=datetime.now(brasilia_tz)
            )
            
            db.session.add(alerta)
            db.session.commit()
            return 1
    
    return 0


def gerar_alerta_generico(config, df):
    """
    Gera alerta usando lógica genérica baseada em configurações customizadas.
    Usa coluna_dados, tipo de verificação, condições de filtro, etc.
    """
    logger.info(f"Iniciando geração de alerta genérico para configuração {config.id}: {config.tipo}")
    configuracoes = config.get_configuracoes_dict()
    condicoes = config.get_condicoes_dict()
    
    logger.debug(f"Configurações: {configuracoes}")
    logger.debug(f"Condições: {condicoes}")
    
    # Obter coluna de dados principal (não obrigatória quando tipo_calculo está definido)
    tipo_calculo = configuracoes.get('tipo_calculo')
    coluna_dados = configuracoes.get('coluna_dados')
    if not tipo_calculo and (not coluna_dados or coluna_dados not in df.columns):
        logger.warning(f"Coluna de dados '{coluna_dados}' não encontrada para alerta {config.id}. Colunas disponíveis: {list(df.columns)[:10]}")
        return 0
    if coluna_dados:
        logger.info(f"Coluna de dados: {coluna_dados}")
    
    # Aplicar filtro de período primeiro
    df_filtrado = df.copy()
    logger.info(f"Dados iniciais: {len(df_filtrado)} linhas")
    
    if config.coluna_data_filtro and config.coluna_data_filtro in df_filtrado.columns:
        agora = datetime.now(brasilia_tz)
        limite = agora - timedelta(hours=config.periodo_verificacao_horas)
        logger.info(f"Filtrando por período: últimas {config.periodo_verificacao_horas}h usando coluna '{config.coluna_data_filtro}'")
        
        df_filtrado[config.coluna_data_filtro] = pd.to_datetime(df_filtrado[config.coluna_data_filtro], errors='coerce', dayfirst=True)
        if df_filtrado[config.coluna_data_filtro].dt.tz is None:
            df_filtrado[config.coluna_data_filtro] = df_filtrado[config.coluna_data_filtro].dt.tz_localize(brasilia_tz)
        
        df_filtrado = df_filtrado[df_filtrado[config.coluna_data_filtro] >= limite]
        logger.info(f"Após filtro de período: {len(df_filtrado)} linhas")
    
    # Aplicar condições de filtro (conector por condição ou legado)
    if condicoes:
        logger.info(f"Aplicando {len(condicoes)} condição(ões) de filtro")
        df_filtrado = filtrar_dataframe(df_filtrado, condicoes, filtro_ultimas_horas=None, coluna_data_filtro=None)
        logger.info(f"Após condições de filtro: {len(df_filtrado)} linhas")
    
    if df_filtrado.empty:
        logger.warning(f"Nenhum dado encontrado após filtros para alerta {config.id}")
        return 0
    
    # Aplicar contagem_por (linhas ou ocorrência)
    contagem_por = configuracoes.get('contagem_por', 'linhas')
    coluna_ocorrencia = configuracoes.get('coluna_ocorrencia')
    df_antes_dedup = df_filtrado.copy()  # mantém todas as linhas para extrair ocorrências
    if contagem_por == 'ocorrencia' and coluna_ocorrencia and coluna_ocorrencia in df_filtrado.columns:
        df_filtrado = df_filtrado.drop_duplicates(subset=[coluna_ocorrencia], keep='first')
    
    # Processar cada tipo de verificação configurado
    alertas_gerados = 0
    
    # Filtrar apenas tipos de verificação válidos
    tipos_validos = ['contar', 'contar_unicos', 'contar_repetidos', 'contem', 'nao_contem', 
                     'igual', 'diferente', 'maior_que', 'menor_que', 'maior_igual', 'menor_igual',
                     'media', 'soma', 'maximo', 'minimo', 'vazio', 'nao_vazio']
    
    verificacoes_encontradas = {k: v for k, v in configuracoes.items() if k in tipos_validos}
    logger.info(f"Tipos de verificação encontrados: {list(verificacoes_encontradas.keys())}")
    
    # Se tipo_calculo está definido (igual aos indicadores), calcular valor e verificar
    tipo_calculo = configuracoes.get('tipo_calculo')
    if tipo_calculo and tipo_calculo in ('diferenca_tempo', 'diferenca_ate_agora', 'contagem', 'media', 'soma', 'percentual_meta'):
        indicador_config = {
            'nome': config.nome,
            'condicoes': condicoes,
            'tipo_calculo': tipo_calculo,
            'coluna_data_inicio': configuracoes.get('coluna_data_inicio'),
            'coluna_data_fim': configuracoes.get('coluna_data_fim'),
            'unidade': configuracoes.get('unidade', 'minutos'),
            'filtro_ultimas_horas': config.periodo_verificacao_horas,
            'coluna_data_filtro': config.coluna_data_filtro,
            'contagem_por': configuracoes.get('contagem_por', 'linhas'),
            'coluna_ocorrencia': configuracoes.get('coluna_ocorrencia'),
        }
        if tipo_calculo == 'percentual_meta':
            indicador_config['meta_valor'] = configuracoes.get('meta_valor')
            indicador_config['meta_operador'] = configuracoes.get('meta_operador', '<=')
        resultado = calcular_indicador(indicador_config, df)
        if resultado.get('erro'):
            logger.warning(f"Erro ao calcular indicador para alerta {config.id}: {resultado.get('erro')}")
            return 0
        valor = resultado.get('valor')
        if valor is None:
            return 0
        # Verificar se alguma condição dispara o alerta
        disparou = False
        # Prioridade 1: alerta_operador e alerta_valor (nova seção dedicada no form)
        alerta_operador = configuracoes.get('alerta_operador')
        alerta_valor = configuracoes.get('alerta_valor')
        if alerta_operador is not None and alerta_valor is not None:
            try:
                limite = float(alerta_valor)
                if alerta_operador == '>=' and valor >= limite:
                    disparou = True
                elif alerta_operador == '<=' and valor <= limite:
                    disparou = True
                elif alerta_operador == '>' and valor > limite:
                    disparou = True
                elif alerta_operador == '<' and valor < limite:
                    disparou = True
                elif alerta_operador == '==' and abs(float(valor) - limite) < 1e-6:
                    disparou = True
            except (TypeError, ValueError):
                pass
        # Prioridade 2: verificacoes_encontradas (Tipo de Verificação - compatibilidade)
        if not disparou:
            for tipo_verif, valor_limite in verificacoes_encontradas.items():
                if tipo_verif in ('coluna_dados', 'contagem_por', 'coluna_ocorrencia'):
                    continue
                limite = float(valor_limite) if valor_limite is not None and str(valor_limite).strip() else None
                if tipo_verif == 'maior_que' and limite is not None and valor > limite:
                    disparou = True
                    break
                if tipo_verif == 'menor_que' and limite is not None and valor < limite:
                    disparou = True
                    break
                if tipo_verif == 'maior_igual' and limite is not None and valor >= limite:
                    disparou = True
                    break
                if tipo_verif == 'menor_igual' and limite is not None and valor <= limite:
                    disparou = True
                    break
                if tipo_verif == 'igual' and limite is not None and abs(float(valor) - limite) < 1e-6:
                    disparou = True
                    break
                if tipo_verif in ('contar', 'media', 'soma', 'maximo', 'minimo') and limite is not None and valor >= limite:
                    disparou = True
                    break
        if disparou:
            unidade_str = resultado.get('unidade', configuracoes.get('unidade', ''))
            col_inicio = configuracoes.get('coluna_data_inicio') or 'Data'
            coluna_unidade = configuracoes.get('coluna_dados')
            # diferenca_ate_agora com coluna para unidades: 1 alerta por unidade que excede
            if tipo_calculo == 'diferenca_ate_agora' and alerta_valor is not None and coluna_unidade and coluna_unidade in df.columns:
                df_filt = filtrar_dataframe(df, condicoes, config.periodo_verificacao_horas, config.coluna_data_filtro)
                col_data = configuracoes.get('coluna_data_inicio')
                unidade_calc = configuracoes.get('unidade', 'minutos')
                if col_data and col_data in df_filt.columns:
                    diffs = calcular_diferenca_ate_agora(df_filt, col_data, unidade_calc)
                    mask = diffs >= float(alerta_valor)
                    if mask.any():
                        idx_excedentes = mask[mask].index
                        df_excedentes = df_filt.loc[idx_excedentes].copy()
                        df_excedentes['_diff'] = diffs.loc[idx_excedentes].values
                        alertas_gerados = 0
                        for unit_val in df_excedentes[coluna_unidade].dropna().astype(str).unique():
                            df_unit = df_excedentes[df_excedentes[coluna_unidade].astype(str) == unit_val]
                            valor_unit = float(df_unit['_diff'].max())
                            valor_fmt = _formatar_valor_tempo(valor_unit, unidade_str or 'minutos')
                            mensagem = f"{col_inicio} há {valor_fmt}. {coluna_unidade}: {unit_val}"
                            detalhes = {'tipo_calculo': tipo_calculo, 'valor_calculado': valor_unit, 'valor_calculado_fmt': valor_fmt, 'unidade': unidade_str, 'valor_identificado': unit_val}
                            col_ocor_da = configuracoes.get('coluna_ocorrencia') or 'Ocorrência'
                            if col_ocor_da in df_unit.columns:
                                try:
                                    ocorrencias = df_unit[col_ocor_da].dropna().astype(str).tolist()
                                    if ocorrencias:
                                        detalhes['numero_ocorrencia'] = ', '.join(ocorrencias)
                                except Exception:
                                    pass
                            if not _alerta_existe_valor_identificado(config.id, unit_val):
                                alerta = Alerta(
                                    configuracao_alerta_id=config.id,
                                    nome_tipo=config.nome,
                                    icone_tipo=config.icone or 'exclamation-triangle',
                                    cor_tipo=config.cor or '#dc3545',
                                    titulo=config.tipo,
                                    mensagem=mensagem,
                                    detalhes=json.dumps(detalhes),
                                    prioridade=config.prioridade,
                                    origem='automatico',
                                    status='ativo',
                                    data_ocorrencia=datetime.now(brasilia_tz)
                                )
                                db.session.add(alerta)
                                alertas_gerados += 1
                        if alertas_gerados:
                            db.session.commit()
                            return alertas_gerados
                return 0
            # Caso único (sem coluna de unidades ou outro tipo_calculo)
            valor_fmt = _formatar_valor_tempo(valor, unidade_str or 'minutos')
            if tipo_calculo == 'diferenca_ate_agora':
                mensagem = f"{col_inicio} há {valor_fmt}."
            else:
                mensagem = f"Valor calculado: {valor_fmt}."
            detalhes = {'tipo_calculo': tipo_calculo, 'valor_calculado': valor, 'valor_calculado_fmt': valor_fmt, 'unidade': unidade_str}
            alerta_existente = Alerta.query.filter_by(configuracao_alerta_id=config.id, status='ativo').first()
            if not alerta_existente:
                alerta = Alerta(
                    configuracao_alerta_id=config.id,
                    nome_tipo=config.nome,
                    icone_tipo=config.icone or 'exclamation-triangle',
                    cor_tipo=config.cor or '#dc3545',
                    titulo=config.tipo,
                    mensagem=mensagem,
                    detalhes=json.dumps(detalhes),
                    prioridade=config.prioridade,
                    origem='automatico',
                    status='ativo',
                    data_ocorrencia=datetime.now(brasilia_tz)
                )
                db.session.add(alerta)
                db.session.commit()
                return 1
        return 0
    
    if not verificacoes_encontradas:
        logger.warning(f"Nenhum tipo de verificação válido encontrado nas configurações para alerta {config.id}")
        return 0
    
    # Verificar se existe coluna de ocorrência para incluir nos detalhes
    col_ocor = configuracoes.get('coluna_ocorrencia') or 'Ocorrência'
    coluna_ocorrencia_disponivel = col_ocor in df_filtrado.columns
    
    for chave_verificacao, valor_limite in verificacoes_encontradas.items():
        # Pular campos especiais
        if chave_verificacao in ['coluna_dados', 'contagem_por', 'coluna_ocorrencia']:
            continue
        
        # Verificar se é um tipo de verificação válido
        tipo_verificacao = chave_verificacao
        
        try:
            resultado = False
            valor_calculado = None
            mensagem_detalhes = ""
            
            if tipo_verificacao == 'contar':
                # Contar ocorrências na coluna_dados
                contagem = len(df_filtrado)
                valor_calculado = contagem
                resultado = contagem >= (float(valor_limite) if valor_limite else 0)
                mensagem_detalhes = f"Total de {contagem} ocorrência(s)"
            
            elif tipo_verificacao == 'contar_unicos':
                # Contar valores únicos
                valores_unicos = df_filtrado[coluna_dados].nunique()
                valor_calculado = valores_unicos
                resultado = valores_unicos >= (float(valor_limite) if valor_limite else 0)
                mensagem_detalhes = f"{valores_unicos} valor(es) único(s)"
            
            elif tipo_verificacao == 'contar_repetidos':
                # Gerar 1 alerta para cada valor que se repete
                contagem_por_valor = df_filtrado[coluna_dados].value_counts()
                repetidos = contagem_por_valor[contagem_por_valor > 1]
                
                if valor_limite:
                    repetidos = repetidos[repetidos >= float(valor_limite)]
                
                if len(repetidos) == 0:
                    continue
                
                # Gerar alerta para cada valor repetido
                for valor_identificado, quantidade in repetidos.items():
                    df_valor = df_filtrado[df_filtrado[coluna_dados] == valor_identificado]
                    numeros_ocorrencia = []
                    df_para_ocor = df_antes_dedup[df_antes_dedup[coluna_dados] == valor_identificado]
                    if coluna_ocorrencia_disponivel and col_ocor in df_para_ocor.columns:
                        try:
                            numeros_ocorrencia = df_para_ocor[col_ocor].dropna().astype(str).unique().tolist()
                        except Exception:
                            pass
                    numero_ocorrencia = ', '.join(numeros_ocorrencia) if numeros_ocorrencia else None
                    
                    if _alerta_existe_valor_identificado(config.id, valor_identificado):
                        continue
                    
                    titulo = config.tipo
                    mensagem = f"Valor '{valor_identificado}' aparece {int(quantidade)} vez(es) na coluna '{coluna_dados}'"
                    
                    detalhes = {
                        'tipo_verificacao': tipo_verificacao,
                        'coluna_dados': coluna_dados,
                        'valor_identificado': _normalizar_valor_identificado(valor_identificado),
                        'valor_calculado': int(quantidade),
                        'valor_limite': valor_limite,
                        'total_registros': len(df_filtrado)
                    }
                    if numero_ocorrencia:
                        detalhes['numero_ocorrencia'] = numero_ocorrencia
                    
                    alerta = Alerta(
                        configuracao_alerta_id=config.id,
                        nome_tipo=config.nome,
                        icone_tipo=config.icone or 'exclamation-triangle',
                        cor_tipo=config.cor or '#dc3545',
                        titulo=titulo,
                        mensagem=mensagem,
                        detalhes=json.dumps(detalhes),
                        prioridade=config.prioridade,
                        origem='automatico',
                        status='ativo',
                        data_ocorrencia=datetime.now(brasilia_tz)
                    )
                    
                    db.session.add(alerta)
                    alertas_gerados += 1
                    logger.info(f"Alerta gerado para valor repetido: {valor_identificado} ({quantidade}x)")
                
                continue  # Já processado, pular para próximo tipo
            
            elif tipo_verificacao == 'contem':
                # Gerar 1 alerta para cada linha que contém o valor
                if valor_limite:
                    mask = df_filtrado[coluna_dados].astype(str).str.contains(str(valor_limite), case=False, na=False)
                    df_contem = df_filtrado[mask]
                    mask_orig = df_antes_dedup[coluna_dados].astype(str).str.contains(str(valor_limite), case=False, na=False)
                    df_contem_orig = df_antes_dedup[mask_orig]
                    
                    if len(df_contem) == 0:
                        continue
                    
                    valores_unicos = df_contem[coluna_dados].unique()
                    
                    for valor_identificado in valores_unicos:
                        df_valor = df_contem[df_contem[coluna_dados] == valor_identificado]
                        df_para_ocor = df_contem_orig[df_contem_orig[coluna_dados] == valor_identificado]
                        numeros_ocorrencia = []
                        if coluna_ocorrencia_disponivel and col_ocor in df_para_ocor.columns:
                            try:
                                numeros_ocorrencia = df_para_ocor[col_ocor].dropna().astype(str).unique().tolist()
                            except Exception:
                                pass
                        numero_ocorrencia = ', '.join(numeros_ocorrencia) if numeros_ocorrencia else None
                        quantidade = len(df_valor)
                        
                        if _alerta_existe_valor_identificado(config.id, valor_identificado):
                            continue
                        
                        titulo = config.tipo
                        mensagem = f"Valor '{valor_identificado}' contém '{valor_limite}' na coluna '{coluna_dados}' ({quantidade} ocorrência(s))"
                        
                        detalhes = {
                            'tipo_verificacao': tipo_verificacao,
                            'coluna_dados': coluna_dados,
                            'valor_identificado': str(valor_identificado),
                            'valor_buscado': str(valor_limite),
                            'valor_calculado': quantidade,
                            'total_registros': len(df_filtrado)
                        }
                        if numero_ocorrencia:
                            detalhes['numero_ocorrencia'] = numero_ocorrencia
                        
                        alerta = Alerta(
                            configuracao_alerta_id=config.id,
                            nome_tipo=config.nome,
                            icone_tipo=config.icone or 'exclamation-triangle',
                            cor_tipo=config.cor or '#dc3545',
                            titulo=titulo,
                            mensagem=mensagem,
                            detalhes=json.dumps(detalhes),
                            prioridade=config.prioridade,
                            origem='automatico',
                            status='ativo',
                            data_ocorrencia=datetime.now(brasilia_tz)
                        )
                        
                        db.session.add(alerta)
                        alertas_gerados += 1
                    
                    continue
            
            elif tipo_verificacao == 'nao_contem':
                # Verificar se não contém o valor
                if valor_limite:
                    resultado = not df_filtrado[coluna_dados].astype(str).str.contains(str(valor_limite), case=False, na=False).any()
                    mensagem_detalhes = f"Valor '{valor_limite}' não encontrado"
            
            elif tipo_verificacao == 'igual':
                # Gerar 1 alerta para cada ocorrência do valor igual
                if valor_limite:
                    df_igual = df_filtrado[df_filtrado[coluna_dados].astype(str) == str(valor_limite)]
                    
                    if len(df_igual) == 0:
                        continue
                    
                    # Agrupar por número de ocorrência se disponível
                    if coluna_ocorrencia_disponivel:
                        ocorrencias_unicas = df_igual[col_ocor].unique()
                        for num_ocorrencia in ocorrencias_unicas:
                            df_ocorrencia = df_igual[df_igual[col_ocor] == num_ocorrencia]
                            primeira_linha = df_ocorrencia.iloc[0]
                            valor_identificado = str(primeira_linha[coluna_dados])
                            
                            if _alerta_existe_numero_ocorrencia(config.id, num_ocorrencia, 'igual'):
                                continue
                            
                            titulo = config.tipo
                            mensagem = f"Valor '{valor_identificado}' igual a '{valor_limite}' na coluna '{coluna_dados}'"
                            
                            detalhes = {
                                'tipo_verificacao': tipo_verificacao,
                                'coluna_dados': coluna_dados,
                                'valor_identificado': valor_identificado,
                                'valor_buscado': str(valor_limite),
                                'numero_ocorrencia': str(num_ocorrencia),
                                'total_registros': len(df_filtrado)
                            }
                            
                            alerta = Alerta(
                                configuracao_alerta_id=config.id,
                                nome_tipo=config.nome,
                                icone_tipo=config.icone or 'exclamation-triangle',
                                cor_tipo=config.cor or '#dc3545',
                                titulo=titulo,
                                mensagem=mensagem,
                                detalhes=json.dumps(detalhes),
                                prioridade=config.prioridade,
                                origem='automatico',
                                status='ativo',
                                data_ocorrencia=datetime.now(brasilia_tz)
                            )
                            
                            db.session.add(alerta)
                            alertas_gerados += 1
                    else:
                        # Sem coluna Ocorrência, gerar 1 alerta geral
                        resultado = True
                        mensagem_detalhes = f"Valor '{valor_limite}' encontrado {len(df_igual)} vez(es)"
                    
                    continue
            
            elif tipo_verificacao == 'diferente':
                # Gerar 1 alerta para cada valor diferente encontrado
                if valor_limite:
                    df_diferente = df_filtrado[df_filtrado[coluna_dados].astype(str) != str(valor_limite)]
                    df_diferente_orig = df_antes_dedup[df_antes_dedup[coluna_dados].astype(str) != str(valor_limite)]
                    
                    if len(df_diferente) == 0:
                        continue
                    
                    valores_unicos = df_diferente[coluna_dados].unique()
                    
                    for valor_identificado in valores_unicos:
                        df_valor = df_diferente[df_diferente[coluna_dados] == valor_identificado]
                        df_para_ocor = df_diferente_orig[df_diferente_orig[coluna_dados] == valor_identificado]
                        numeros_ocorrencia = []
                        if coluna_ocorrencia_disponivel and col_ocor in df_para_ocor.columns:
                            try:
                                numeros_ocorrencia = df_para_ocor[col_ocor].dropna().astype(str).unique().tolist()
                            except Exception:
                                pass
                        numero_ocorrencia = ', '.join(numeros_ocorrencia) if numeros_ocorrencia else None
                        quantidade = len(df_valor)
                        
                        if _alerta_existe_valor_identificado(config.id, valor_identificado):
                            continue
                        
                        titulo = config.tipo
                        mensagem = f"Valor '{valor_identificado}' diferente de '{valor_limite}' na coluna '{coluna_dados}' ({quantidade} ocorrência(s))"
                        
                        detalhes = {
                            'tipo_verificacao': tipo_verificacao,
                            'coluna_dados': coluna_dados,
                            'valor_identificado': str(valor_identificado),
                            'valor_buscado': str(valor_limite),
                            'valor_calculado': quantidade,
                            'total_registros': len(df_filtrado)
                        }
                        if numero_ocorrencia:
                            detalhes['numero_ocorrencia'] = numero_ocorrencia
                        
                        alerta = Alerta(
                            configuracao_alerta_id=config.id,
                            nome_tipo=config.nome,
                            icone_tipo=config.icone or 'exclamation-triangle',
                            cor_tipo=config.cor or '#dc3545',
                            titulo=titulo,
                            mensagem=mensagem,
                            detalhes=json.dumps(detalhes),
                            prioridade=config.prioridade,
                            origem='automatico',
                            status='ativo',
                            data_ocorrencia=datetime.now(brasilia_tz)
                        )
                        
                        db.session.add(alerta)
                        alertas_gerados += 1
                    
                    continue
            
            elif tipo_verificacao == 'maior_que':
                # Verificar se algum valor é maior
                if valor_limite:
                    serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                    resultado = (serie_numerica > float(valor_limite)).any()
                    valor_calculado = serie_numerica.max()
                    mensagem_detalhes = f"Valor máximo: {valor_calculado} (limite: {valor_limite})"
            
            elif tipo_verificacao == 'menor_que':
                # Verificar se algum valor é menor
                if valor_limite:
                    serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                    resultado = (serie_numerica < float(valor_limite)).any()
                    valor_calculado = serie_numerica.min()
                    mensagem_detalhes = f"Valor mínimo: {valor_calculado} (limite: {valor_limite})"
            
            elif tipo_verificacao == 'maior_igual':
                if valor_limite:
                    serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                    resultado = (serie_numerica >= float(valor_limite)).any()
                    valor_calculado = serie_numerica.max()
                    mensagem_detalhes = f"Valor máximo: {valor_calculado} (limite: {valor_limite})"
            
            elif tipo_verificacao == 'menor_igual':
                if valor_limite:
                    serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                    resultado = (serie_numerica <= float(valor_limite)).any()
                    valor_calculado = serie_numerica.min()
                    mensagem_detalhes = f"Valor mínimo: {valor_calculado} (limite: {valor_limite})"
            
            elif tipo_verificacao == 'media':
                # Calcular média
                serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                media = serie_numerica.mean()
                valor_calculado = media
                if valor_limite:
                    resultado = media >= float(valor_limite)
                    mensagem_detalhes = f"Média: {media:.2f} (limite: {valor_limite})"
                else:
                    resultado = True  # Sempre gera se não houver limite
                    mensagem_detalhes = f"Média: {media:.2f}"
            
            elif tipo_verificacao == 'soma':
                # Calcular soma
                serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                soma = serie_numerica.sum()
                valor_calculado = soma
                if valor_limite:
                    resultado = soma >= float(valor_limite)
                    mensagem_detalhes = f"Soma: {soma:.2f} (limite: {valor_limite})"
                else:
                    resultado = True
                    mensagem_detalhes = f"Soma: {soma:.2f}"
            
            elif tipo_verificacao == 'maximo':
                # Encontrar máximo
                serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                maximo = serie_numerica.max()
                valor_calculado = maximo
                if valor_limite:
                    resultado = maximo >= float(valor_limite)
                    mensagem_detalhes = f"Máximo: {maximo} (limite: {valor_limite})"
                else:
                    resultado = True
                    mensagem_detalhes = f"Máximo: {maximo}"
            
            elif tipo_verificacao == 'minimo':
                # Encontrar mínimo
                serie_numerica = pd.to_numeric(df_filtrado[coluna_dados], errors='coerce')
                minimo = serie_numerica.min()
                valor_calculado = minimo
                if valor_limite:
                    resultado = minimo <= float(valor_limite)
                    mensagem_detalhes = f"Mínimo: {minimo} (limite: {valor_limite})"
                else:
                    resultado = True
                    mensagem_detalhes = f"Mínimo: {minimo}"
            
            elif tipo_verificacao == 'vazio':
                # Verificar se há valores vazios/nulos
                vazios = df_filtrado[coluna_dados].isna().sum()
                valor_calculado = vazios
                resultado = vazios > 0
                mensagem_detalhes = f"{vazios} valor(es) vazio(s)/nulo(s)"
            
            elif tipo_verificacao == 'nao_vazio':
                # Verificar se há valores não vazios
                nao_vazios = df_filtrado[coluna_dados].notna().sum()
                valor_calculado = nao_vazios
                if valor_limite:
                    resultado = nao_vazios >= float(valor_limite)
                    mensagem_detalhes = f"{nao_vazios} valor(es) não vazio(s) (limite: {valor_limite})"
                else:
                    resultado = nao_vazios > 0
                    mensagem_detalhes = f"{nao_vazios} valor(es) não vazio(s)"
            
            # Se resultado for True, gerar alerta (para tipos que não foram processados acima)
            if resultado:
                logger.info(f"Condição atendida: {tipo_verificacao} = {valor_calculado} (limite: {valor_limite})")
                
                # Verificar se já existe alerta ativo para esta configuração e tipo de verificação
                alerta_existente = Alerta.query.filter_by(
                    configuracao_alerta_id=config.id,
                    status='ativo'
                ).filter(
                    Alerta.detalhes.like(f'%"tipo_verificacao":"{tipo_verificacao}"%')
                ).first()
                
                if alerta_existente:
                    logger.debug(f"Alerta já existe para {config.id} - {tipo_verificacao}, pulando")
                    continue  # Já existe alerta ativo
                
                # Buscar todas as ocorrências para listar
                numeros_ocorrencia = []
                if coluna_ocorrencia_disponivel and col_ocor in df_filtrado.columns:
                    try:
                        numeros_ocorrencia = df_filtrado[col_ocor].dropna().astype(str).tolist()
                    except Exception:
                        pass
                numero_ocorrencia = ', '.join(numeros_ocorrencia) if numeros_ocorrencia else None
                primeira_linha = df_filtrado.iloc[0]
                valor_identificado = str(primeira_linha[coluna_dados]) if coluna_dados in primeira_linha else None
                
                # Criar mensagem do alerta
                titulo = config.tipo
                if valor_identificado:
                    titulo = config.tipo
                mensagem = f"{tipo_verificacao.replace('_', ' ').title()} na coluna '{coluna_dados}'. {mensagem_detalhes}."
                
                detalhes = {
                    'tipo_verificacao': tipo_verificacao,
                    'coluna_dados': coluna_dados,
                    'valor_limite': valor_limite,
                    'valor_calculado': valor_calculado,
                    'total_registros': len(df_filtrado)
                }
                if numero_ocorrencia:
                    detalhes['numero_ocorrencia'] = numero_ocorrencia
                if valor_identificado:
                    detalhes['valor_identificado'] = valor_identificado
                
                alerta = Alerta(
                    configuracao_alerta_id=config.id,
                    nome_tipo=config.nome,
                    icone_tipo=config.icone or 'exclamation-triangle',
                    cor_tipo=config.cor or '#dc3545',
                    titulo=titulo,
                    mensagem=mensagem,
                    detalhes=json.dumps(detalhes),
                    prioridade=config.prioridade,
                    origem='automatico',
                    status='ativo',
                    data_ocorrencia=datetime.now(brasilia_tz)
                )
                
                db.session.add(alerta)
                alertas_gerados += 1
                logger.info(f"Alerta genérico gerado: {config.tipo} - {tipo_verificacao}")
        
        except Exception as e:
            logger.error(f"Erro ao processar verificação {tipo_verificacao} para alerta {config.id}: {e}", exc_info=True)
            continue
    
    if alertas_gerados > 0:
        db.session.commit()
    
    return alertas_gerados
