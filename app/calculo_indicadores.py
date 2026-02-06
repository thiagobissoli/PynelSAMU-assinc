"""
Sistema de cálculo dinâmico de indicadores baseado em configurações
"""

import pandas as pd
import logging
from datetime import datetime, timedelta
import pytz
from app.indicadores import carregar_dados as carregar_dados_indicadores
from app.models import Indicador

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')


def aplicar_condicao(df, coluna, operador, valor):
    """
    Aplica uma condição de filtro ao DataFrame
    
    Args:
        df: DataFrame
        coluna: Nome da coluna
        operador: Operador (==, !=, >, <, >=, <=, in, contains, startswith, endswith)
        valor: Valor para comparação
    
    Returns:
        Series booleana com os resultados
    """
    if coluna not in df.columns:
        logger.warning(f"Coluna '{coluna}' não encontrada no DataFrame")
        return pd.Series([False] * len(df), index=df.index)
    
    serie = df[coluna]
    
    try:
        if operador == '==':
            return serie == valor
        elif operador == '!=':
            return serie != valor
        elif operador == '>':
            return pd.to_numeric(serie, errors='coerce') > float(valor)
        elif operador == '<':
            return pd.to_numeric(serie, errors='coerce') < float(valor)
        elif operador == '>=':
            return pd.to_numeric(serie, errors='coerce') >= float(valor)
        elif operador == '<=':
            return pd.to_numeric(serie, errors='coerce') <= float(valor)
        elif operador == 'in':
            if isinstance(valor, list):
                return serie.isin(valor)
            else:
                return serie.isin([valor])
        elif operador == 'not in':
            if isinstance(valor, list):
                return ~serie.isin(valor)
            else:
                return ~serie.isin([valor])
        elif operador == 'contains':
            return serie.astype(str).str.contains(str(valor), case=False, na=False)
        elif operador == 'not contains':
            return ~serie.astype(str).str.contains(str(valor), case=False, na=False)
        elif operador == 'startswith':
            return serie.astype(str).str.startswith(str(valor), na=False)
        elif operador == 'endswith':
            return serie.astype(str).str.endswith(str(valor), na=False)
        elif operador == 'is null':
            return serie.isna()
        elif operador == 'is not null':
            return serie.notna()
        else:
            logger.warning(f"Operador '{operador}' não reconhecido, usando ==")
            return serie == valor
    except Exception as e:
        logger.error(f"Erro ao aplicar condição {coluna} {operador} {valor}: {e}")
        return pd.Series([False] * len(df), index=df.index)


def filtrar_ultimas_horas(df, coluna_data, horas):
    """
    Filtra DataFrame para incluir apenas registros das últimas X horas
    
    Args:
        df: DataFrame
        coluna_data: Nome da coluna de data/hora
        horas: Número de horas para filtrar
    
    Returns:
        DataFrame filtrado
    """
    if coluna_data not in df.columns:
        logger.warning(f"Coluna de data '{coluna_data}' não encontrada")
        return df
    
    try:
        # Criar cópia para evitar SettingWithCopyWarning
        df = df.copy()
        
        # Converter para datetime
        df[coluna_data] = pd.to_datetime(df[coluna_data], errors='coerce')
        
        # Remover timezone se presente para evitar erros de comparação
        if df[coluna_data].dt.tz is not None:
            df[coluna_data] = df[coluna_data].dt.tz_localize(None)
        
        # Calcular data limite (agora - X horas) usando datetime naive
        agora = datetime.now()
        data_limite = agora - timedelta(hours=horas)
        
        # Converter para pd.Timestamp para compatibilidade
        data_limite_ts = pd.Timestamp(data_limite)
        
        # Filtrar
        mask = df[coluna_data] >= data_limite_ts
        return df[mask]
    except Exception as e:
        logger.error(f"Erro ao filtrar últimas {horas} horas: {e}")
        return df


def filtrar_dataframe(df, condicoes, filtro_ultimas_horas=None, coluna_data_filtro=None, operador_condicoes='and'):
    """
    Filtra o DataFrame baseado em uma lista de condições.
    Cada condição pode ter 'conector' (and/or/if) indicando como combina com a anterior.
    Formato: [{"coluna": "...", "operador": "==", "valor": "...", "conector": "and"}, ...]
    A primeira condição usa conector='and' por padrão (sem efeito).
    """
    df_filtrado = df.copy()
    
    if filtro_ultimas_horas and coluna_data_filtro:
        df_filtrado = filtrar_ultimas_horas(df_filtrado, coluna_data_filtro, filtro_ultimas_horas)
    
    if condicoes:
        # Suporte a conector por condição (novo) ou operador_condicoes global (legado)
        tem_conector = any(c.get('conector') for c in condicoes if c.get('coluna'))
        
        if tem_conector:
            # Avaliar com conector por condição
            condicoes_validas = []
            for c in condicoes:
                col = c.get('coluna')
                if not col:
                    continue
                condicoes_validas.append({
                    'coluna': col,
                    'operador': c.get('operador', '=='),
                    'valor': c.get('valor'),
                    'conector': (c.get('conector') or 'and').lower()
                })
            if not condicoes_validas:
                return df_filtrado
            
            result = aplicar_condicao(df_filtrado, condicoes_validas[0]['coluna'],
                                     condicoes_validas[0]['operador'], condicoes_validas[0]['valor'])
            for i in range(1, len(condicoes_validas)):
                c = condicoes_validas[i]
                mask = aplicar_condicao(df_filtrado, c['coluna'], c['operador'], c['valor'])
                op = c['conector'] if c['conector'] in ('and', 'or', 'if') else 'and'
                if op == 'or':
                    result = result | mask
                elif op == 'if':
                    result = (~mask) | (mask & result)
                else:
                    result = result & mask
            df_filtrado = df_filtrado[result]
        else:
            # Legado: operador único para todas
            condicoes_validas = [(c.get('coluna'), c.get('operador', '=='), c.get('valor')) for c in condicoes if c.get('coluna')]
            if not condicoes_validas:
                return df_filtrado
            op = (operador_condicoes or 'and').lower()
            if op == 'or':
                mask_total = pd.Series([False] * len(df_filtrado), index=df_filtrado.index)
                for coluna, operador, valor in condicoes_validas:
                    mask_total = mask_total | aplicar_condicao(df_filtrado, coluna, operador, valor)
                df_filtrado = df_filtrado[mask_total]
            elif op == 'if':
                col1, op1, val1 = condicoes_validas[0]
                mask_gate = aplicar_condicao(df_filtrado, col1, op1, val1)
                mask_resto = pd.Series([True] * len(df_filtrado), index=df_filtrado.index)
                for coluna, operador, valor in condicoes_validas[1:]:
                    mask_resto = mask_resto & aplicar_condicao(df_filtrado, coluna, operador, valor)
                mask_final = (~mask_gate) | (mask_gate & mask_resto)
                df_filtrado = df_filtrado[mask_final]
            else:
                for coluna, operador, valor in condicoes_validas:
                    mask = aplicar_condicao(df_filtrado, coluna, operador, valor)
                    df_filtrado = df_filtrado[mask]
    
    return df_filtrado


def calcular_diferenca_ate_agora(df, coluna_data, unidade='minutos', tz=None):
    """
    Calcula a diferença entre a coluna de data e o horário atual (agora).
    Útil para: tempo desde chegada no hospital, tempo em atendimento, etc.
    
    Args:
        df: DataFrame filtrado
        coluna_data: Nome da coluna de data (ex: Chegada no hospital)
        unidade: 'segundos', 'minutos', 'horas', 'dias'
        tz: timezone (ex: pytz.timezone('America/Sao_Paulo'))
    
    Returns:
        Series com as diferenças em relação a agora (agora - data)
    """
    if coluna_data not in df.columns:
        logger.warning(f"Coluna de data não encontrada: {coluna_data}")
        return pd.Series(dtype=float)
    
    col_dt = pd.to_datetime(df[coluna_data], errors='coerce')
    col_dt = col_dt.dropna()
    if col_dt.empty:
        return pd.Series(dtype=float)
    
    if tz is None:
        tz = brasilia_tz
    agora = datetime.now(tz)
    if col_dt.dt.tz is not None:
        col_dt = col_dt.dt.tz_convert(tz)
    else:
        col_dt = col_dt.dt.tz_localize(tz, ambiguous='infer')
    
    diferenca = pd.Timestamp(agora) - col_dt
    
    if unidade == 'segundos':
        return diferenca.dt.total_seconds()
    elif unidade == 'minutos':
        return diferenca.dt.total_seconds() / 60
    elif unidade == 'horas':
        return diferenca.dt.total_seconds() / 3600
    elif unidade == 'dias':
        return diferenca.dt.total_seconds() / 86400
    else:
        return diferenca.dt.total_seconds() / 60


def calcular_diferenca_tempo(df, coluna_inicio, coluna_fim, unidade='minutos'):
    """
    Calcula a diferença de tempo entre duas colunas de data
    
    Args:
        df: DataFrame filtrado
        coluna_inicio: Nome da coluna de data inicial
        coluna_fim: Nome da coluna de data final
        unidade: 'segundos', 'minutos', 'horas', 'dias'
    
    Returns:
        Series com as diferenças calculadas
    """
    if coluna_inicio not in df.columns or coluna_fim not in df.columns:
        logger.warning(f"Colunas de data não encontradas: {coluna_inicio}, {coluna_fim}")
        return pd.Series(dtype=float)
    
    # Converter para datetime (variáveis locais para evitar SettingWithCopyWarning)
    col_inicio = pd.to_datetime(df[coluna_inicio], errors='coerce')
    col_fim = pd.to_datetime(df[coluna_fim], errors='coerce')
    diferenca = col_fim - col_inicio
    
    # Converter para unidade desejada
    if unidade == 'segundos':
        return diferenca.dt.total_seconds()
    elif unidade == 'minutos':
        return diferenca.dt.total_seconds() / 60
    elif unidade == 'horas':
        return diferenca.dt.total_seconds() / 3600
    elif unidade == 'dias':
        return diferenca.dt.total_seconds() / 86400
    else:
        return diferenca.dt.total_seconds() / 60  # Default: minutos


def calcular_indicador(indicador_config, df=None):
    """
    Calcula um indicador baseado em sua configuração
    
    Args:
        indicador_config: Instância do modelo Indicador ou dicionário
        df: DataFrame (se None, carrega do arquivo)
    
    Returns:
        Dicionário com os resultados do cálculo
    """
    if df is None:
        df = carregar_dados_indicadores()
        if df is None:
            return {'erro': 'Não foi possível carregar os dados'}
    
    # Converter para dicionário se for modelo
    if isinstance(indicador_config, Indicador):
        config = indicador_config.to_dict()
    else:
        config = indicador_config
    
    nome = config.get('nome', 'Indicador')
    condicoes = config.get('condicoes', [])
    tipo_calculo = config.get('tipo_calculo', 'diferenca_tempo')
    coluna_data_inicio = config.get('coluna_data_inicio')
    coluna_data_fim = config.get('coluna_data_fim')
    unidade = config.get('unidade', 'minutos')
    filtro_ultimas_horas = config.get('filtro_ultimas_horas')
    coluna_data_filtro = config.get('coluna_data_filtro')
    contagem_por = config.get('contagem_por') or 'linhas'
    coluna_ocorrencia = config.get('coluna_ocorrencia')
    meta_valor = config.get('meta_valor')
    meta_operador = (config.get('meta_operador') or '<=').strip()
    
    # Filtrar DataFrame (conector por condição ou legado)
    df_filtrado = filtrar_dataframe(df, condicoes, filtro_ultimas_horas, coluna_data_filtro)
    
    # Por ocorrência: deduplicar por coluna antes de contar/calcular
    if contagem_por == 'ocorrencia' and coluna_ocorrencia and coluna_ocorrencia in df_filtrado.columns:
        df_filtrado = df_filtrado.drop_duplicates(subset=[coluna_ocorrencia], keep='first')
    
    if df_filtrado.empty:
        return {
            'nome': nome,
            'valor': None,
            'total_registros': 0,
            'registros_filtrados': 0,
            'erro': 'Nenhum registro encontrado após aplicar filtros'
        }
    
    # Calcular indicador baseado no tipo
    resultado = {
        'nome': nome,
        'tipo_calculo': tipo_calculo,
        'total_registros': len(df),
        'registros_filtrados': len(df_filtrado),
    }
    
    try:
        if tipo_calculo == 'diferenca_tempo':
            if not coluna_data_inicio or not coluna_data_fim:
                resultado['erro'] = 'Colunas de data não especificadas'
                return resultado
            
            diferencas = calcular_diferenca_tempo(df_filtrado, coluna_data_inicio, coluna_data_fim, unidade)
            diferencas_validas = diferencas.dropna()
            
            if diferencas_validas.empty:
                resultado['erro'] = 'Nenhuma diferença de tempo válida encontrada'
                return resultado
            
            resultado['valor'] = float(diferencas_validas.mean())
            resultado['minimo'] = float(diferencas_validas.min())
            resultado['maximo'] = float(diferencas_validas.max())
            resultado['mediana'] = float(diferencas_validas.median())
            resultado['unidade'] = unidade
            
        elif tipo_calculo == 'diferenca_ate_agora':
            if not coluna_data_inicio:
                resultado['erro'] = 'Coluna de data não especificada (tempo desde quando?)'
                return resultado
            
            diferencas = calcular_diferenca_ate_agora(df_filtrado, coluna_data_inicio, unidade)
            diferencas_validas = diferencas.dropna()
            
            if diferencas_validas.empty:
                resultado['erro'] = 'Nenhuma data válida encontrada na coluna'
                return resultado
            
            resultado['valor'] = float(diferencas_validas.max())
            resultado['minimo'] = float(diferencas_validas.min())
            resultado['maximo'] = float(diferencas_validas.max())
            resultado['mediana'] = float(diferencas_validas.median())
            resultado['unidade'] = unidade
            
        elif tipo_calculo == 'contagem':
            resultado['valor'] = len(df_filtrado)
            resultado['unidade'] = config.get('unidade') or 'ocorrências'
            # Min/Max: mínimo e máximo das contagens por período (mesma lógica do gráfico)
            try:
                horas_grafico = config.get('grafico_ultimas_horas') or 12
                intervalo_min = config.get('grafico_intervalo_minutos') or 60
                dados_grafico = gerar_dados_grafico(indicador_config, horas=horas_grafico, intervalo_minutos=intervalo_min, df=df)
                valores_contagem = [d['valor'] for d in dados_grafico if d.get('valor') is not None]
                if valores_contagem:
                    resultado['minimo'] = int(min(valores_contagem))
                    resultado['maximo'] = int(max(valores_contagem))
            except Exception as e:
                logger.debug('Min/max contagem não calculado: %s', e)
            
        elif tipo_calculo == 'soma':
            if not coluna_data_fim:
                resultado['erro'] = 'Coluna para soma não especificada'
                return resultado
            
            serie = pd.to_numeric(df_filtrado[coluna_data_fim], errors='coerce')
            serie_valida = serie.dropna()
            
            if serie_valida.empty:
                resultado['erro'] = 'Nenhum valor numérico válido encontrado'
                return resultado
            
            resultado['valor'] = float(serie_valida.sum())
            resultado['unidade'] = unidade
            
        elif tipo_calculo == 'media':
            if not coluna_data_fim:
                resultado['erro'] = 'Coluna para média não especificada'
                return resultado
            
            serie = pd.to_numeric(df_filtrado[coluna_data_fim], errors='coerce')
            serie_valida = serie.dropna()
            
            if serie_valida.empty:
                resultado['erro'] = 'Nenhum valor numérico válido encontrado'
                return resultado
            
            resultado['valor'] = float(serie_valida.mean())
            resultado['minimo'] = float(serie_valida.min())
            resultado['maximo'] = float(serie_valida.max())
            resultado['mediana'] = float(serie_valida.median())
            resultado['unidade'] = unidade
            
        elif tipo_calculo == 'percentual_meta':
            if not coluna_data_inicio or not coluna_data_fim:
                resultado['erro'] = 'Colunas de data não especificadas para % que atinge a meta'
                return resultado
            if meta_valor is None:
                resultado['erro'] = 'Valor da meta não especificado'
                return resultado
            unidade_medida = unidade if unidade and unidade != '%' else 'minutos'
            diferencas = calcular_diferenca_tempo(df_filtrado, coluna_data_inicio, coluna_data_fim, unidade_medida)
            diferencas_validas = diferencas.dropna()
            if diferencas_validas.empty:
                resultado['erro'] = 'Nenhuma diferença de tempo válida para calcular % na meta'
                return resultado
            op = meta_operador if meta_operador in ('<=', '>=') else '<='
            if op == '<=':
                dentro = (diferencas_validas <= float(meta_valor)).sum()
            else:
                dentro = (diferencas_validas >= float(meta_valor)).sum()
            total = len(diferencas_validas)
            resultado['valor'] = round(100.0 * dentro / total, 2) if total else None
            resultado['unidade'] = '%'
            
        else:
            resultado['erro'] = f'Tipo de cálculo "{tipo_calculo}" não implementado'
            
    except Exception as e:
        logger.error(f"Erro ao calcular indicador {nome}: {e}", exc_info=True)
        resultado['erro'] = str(e)
    
    return resultado


def calcular_variacao_percentual(indicador_config, df=None):
    """
    Calcula a variação percentual de um indicador comparando o valor atual
    com o valor de 1 hora atrás.
    
    Args:
        indicador_config: Instância do modelo Indicador ou dicionário
        df: DataFrame (se None, carrega do arquivo)
    
    Returns:
        Dicionário com variação percentual e tendência
    """
    if df is None:
        df = carregar_dados_indicadores()
        if df is None:
            return {'variacao_percentual': None, 'tendencia': None}
    
    # Converter para dicionário se for modelo
    if isinstance(indicador_config, Indicador):
        config = indicador_config.to_dict()
        tendencia_inversa = indicador_config.tendencia_inversa
    else:
        config = indicador_config
        tendencia_inversa = config.get('tendencia_inversa', False)
    
    condicoes = config.get('condicoes', [])
    tipo_calculo = config.get('tipo_calculo', 'diferenca_tempo')
    coluna_data_inicio = config.get('coluna_data_inicio')
    coluna_data_fim = config.get('coluna_data_fim')
    unidade = config.get('unidade', 'minutos')
    filtro_ultimas_horas = config.get('filtro_ultimas_horas') or 2
    coluna_data_filtro = config.get('coluna_data_filtro')
    contagem_por = config.get('contagem_por') or 'linhas'
    coluna_ocorrencia = config.get('coluna_ocorrencia')
    meta_valor = config.get('meta_valor')
    meta_operador = (config.get('meta_operador') or '<=').strip()
    unidade_medida = unidade if unidade and unidade != '%' else 'minutos'
    
    def _dedup_se_ocorrencia(d):
        if contagem_por == 'ocorrencia' and coluna_ocorrencia and coluna_ocorrencia in d.columns:
            return d.drop_duplicates(subset=[coluna_ocorrencia], keep='first')
        return d
    
    agora = datetime.now()
    uma_hora_atras = agora - timedelta(hours=1)
    
    # Calcular valor ATUAL (janela terminando agora)
    df_atual = df.copy()
    if coluna_data_filtro and coluna_data_filtro in df_atual.columns:
        df_atual[coluna_data_filtro] = pd.to_datetime(df_atual[coluna_data_filtro], errors='coerce')
        if df_atual[coluna_data_filtro].dt.tz is not None:
            df_atual[coluna_data_filtro] = df_atual[coluna_data_filtro].dt.tz_localize(None)
        
        inicio_janela_atual = agora - timedelta(hours=filtro_ultimas_horas)
        mask_atual = (df_atual[coluna_data_filtro] >= inicio_janela_atual) & (df_atual[coluna_data_filtro] <= agora)
        df_atual = df_atual[mask_atual]
    
    df_atual = filtrar_dataframe(df_atual, condicoes)
    df_atual = _dedup_se_ocorrencia(df_atual)
    
    # Calcular valor de 1 HORA ATRÁS (janela terminando 1 hora atrás)
    df_anterior = df.copy()
    if coluna_data_filtro and coluna_data_filtro in df_anterior.columns:
        df_anterior[coluna_data_filtro] = pd.to_datetime(df_anterior[coluna_data_filtro], errors='coerce')
        if df_anterior[coluna_data_filtro].dt.tz is not None:
            df_anterior[coluna_data_filtro] = df_anterior[coluna_data_filtro].dt.tz_localize(None)
        
        inicio_janela_anterior = uma_hora_atras - timedelta(hours=filtro_ultimas_horas)
        mask_anterior = (df_anterior[coluna_data_filtro] >= inicio_janela_anterior) & (df_anterior[coluna_data_filtro] <= uma_hora_atras)
        df_anterior = df_anterior[mask_anterior]
    
    df_anterior = filtrar_dataframe(df_anterior, condicoes)
    df_anterior = _dedup_se_ocorrencia(df_anterior)
    
    # Calcular valores
    valor_atual = None
    valor_anterior = None
    
    try:
        if tipo_calculo == 'diferenca_tempo' and coluna_data_inicio and coluna_data_fim:
            if not df_atual.empty:
                dif_atual = calcular_diferenca_tempo(df_atual, coluna_data_inicio, coluna_data_fim, unidade)
                dif_atual = dif_atual.dropna()
                if not dif_atual.empty:
                    valor_atual = float(dif_atual.mean())
            
            if not df_anterior.empty:
                dif_anterior = calcular_diferenca_tempo(df_anterior, coluna_data_inicio, coluna_data_fim, unidade)
                dif_anterior = dif_anterior.dropna()
                if not dif_anterior.empty:
                    valor_anterior = float(dif_anterior.mean())
                    
        elif tipo_calculo == 'contagem':
            valor_atual = len(df_atual) if not df_atual.empty else 0
            valor_anterior = len(df_anterior) if not df_anterior.empty else 0
            
        elif tipo_calculo in ['soma', 'media'] and coluna_data_fim:
            if not df_atual.empty and coluna_data_fim in df_atual.columns:
                serie = pd.to_numeric(df_atual[coluna_data_fim], errors='coerce').dropna()
                if not serie.empty:
                    valor_atual = float(serie.sum() if tipo_calculo == 'soma' else serie.mean())
            
            if not df_anterior.empty and coluna_data_fim in df_anterior.columns:
                serie = pd.to_numeric(df_anterior[coluna_data_fim], errors='coerce').dropna()
                if not serie.empty:
                    valor_anterior = float(serie.sum() if tipo_calculo == 'soma' else serie.mean())
        
        elif tipo_calculo == 'percentual_meta' and coluna_data_inicio and coluna_data_fim and meta_valor is not None:
            op = meta_operador if meta_operador in ('<=', '>=') else '<='
            for d, dest in [(df_atual, 'atual'), (df_anterior, 'valor_anterior')]:
                if d.empty:
                    continue
                dif = calcular_diferenca_tempo(d, coluna_data_inicio, coluna_data_fim, unidade_medida).dropna()
                if dif.empty:
                    continue
                dentro = (dif <= float(meta_valor)).sum() if op == '<=' else (dif >= float(meta_valor)).sum()
                total = len(dif)
                v = round(100.0 * dentro / total, 2) if total else None
                if dest == 'atual':
                    valor_atual = v
                else:
                    valor_anterior = v
    
    except Exception as e:
        logger.error(f"Erro ao calcular variação: {e}", exc_info=True)
        return {'variacao_percentual': None, 'tendencia': None, 'erro': str(e)}
    
    # Calcular variação percentual
    if valor_atual is not None and valor_anterior is not None and valor_anterior != 0:
        variacao = ((valor_atual - valor_anterior) / abs(valor_anterior)) * 100
        
        # Determinar tendência
        # Se tendencia_inversa = True (menor é melhor), tendência positiva quando valor diminui
        if tendencia_inversa:
            tendencia = 'positiva' if valor_atual < valor_anterior else ('negativa' if valor_atual > valor_anterior else 'neutra')
        else:
            tendencia = 'positiva' if valor_atual > valor_anterior else ('negativa' if valor_atual < valor_anterior else 'neutra')
        
        return {
            'variacao_percentual': round(variacao, 1),
            'tendencia': tendencia,
            'valor_atual': valor_atual,
            'valor_anterior': valor_anterior
        }
    
    return {'variacao_percentual': None, 'tendencia': 'neutra'}


def calcular_todos_indicadores(df=None):
    """
    Calcula todos os indicadores ativos configurados
    
    Args:
        df: DataFrame (se None, carrega do arquivo)
    
    Returns:
        Lista de dicionários com os resultados
    """
    indicadores = Indicador.query.filter_by(ativo=True).order_by(Indicador.ordem).all()
    
    resultados = []
    for indicador in indicadores:
        resultado = calcular_indicador(indicador, df)
        resultado['id'] = indicador.id  # Adicionar ID para referência
        resultados.append(resultado)
    
    return resultados


def gerar_dados_grafico(indicador_config, horas=12, intervalo_minutos=60, df=None):
    """
    Gera dados históricos para gráfico de um indicador.
    
    Cada ponto do gráfico representa a MÉDIA calculada sobre uma janela de tempo
    baseada no filtro_ultimas_horas do indicador. Isso gera gráficos mais estáveis e fiéis.
    
    Args:
        indicador_config: Instância do modelo Indicador ou dicionário
        horas: Número total de horas para o gráfico (padrão: 12)
        intervalo_minutos: Intervalo em minutos entre cada ponto do gráfico (padrão: 60)
        df: DataFrame (se None, carrega do arquivo)
    
    Returns:
        Lista de dicionários com dados do gráfico
    """
    if df is None:
        df = carregar_dados_indicadores()
        if df is None:
            return []
    
    # Converter para dicionário se for modelo
    if isinstance(indicador_config, Indicador):
        config = indicador_config.to_dict()
    else:
        config = indicador_config
    
    # Obter configurações
    condicoes = config.get('condicoes', [])
    tipo_calculo = config.get('tipo_calculo', 'diferenca_tempo')
    coluna_data_inicio = config.get('coluna_data_inicio')
    coluna_data_fim = config.get('coluna_data_fim')
    unidade = config.get('unidade', 'minutos')
    coluna_data_filtro = config.get('coluna_data_filtro') or coluna_data_inicio
    contagem_por = config.get('contagem_por') or 'linhas'
    coluna_ocorrencia = config.get('coluna_ocorrencia')
    meta_valor = config.get('meta_valor')
    meta_operador = (config.get('meta_operador') or '<=').strip()
    unidade_medida = unidade if (unidade and unidade != '%') else 'minutos'
    
    # IMPORTANTE: Usar o filtro_ultimas_horas do indicador como janela de média
    # Cada ponto do gráfico será a média dos dados das últimas X horas
    janela_media_horas = config.get('filtro_ultimas_horas') or 2  # Padrão: 2 horas
    
    # Calcular data inicial (agora - X horas do gráfico)
    # Usar datetime naive (sem timezone) para compatibilidade com pandas
    agora = datetime.now()
    data_inicial = agora - timedelta(hours=horas)
    
    # Alinhar a horários "redondos" para legenda do eixo X (ex: 1:00, 2:00 ou 1:00, 1:30, 2:00)
    if intervalo_minutos > 0 and intervalo_minutos <= 60:
        min_align = (data_inicial.minute // intervalo_minutos) * intervalo_minutos
        data_inicial = data_inicial.replace(minute=min_align, second=0, microsecond=0)
    
    # Aplicar apenas as condições de filtro (sem filtro de tempo, pois vamos fazer janelas móveis)
    df_base = filtrar_dataframe(df.copy(), condicoes, filtro_ultimas_horas=None, coluna_data_filtro=None)
    
    if df_base.empty:
        return []
    
    # Converter coluna de data para datetime se necessário
    if coluna_data_filtro and coluna_data_filtro in df_base.columns:
        df_base[coluna_data_filtro] = pd.to_datetime(df_base[coluna_data_filtro], errors='coerce')
        # Remover timezone se presente para evitar erros de comparação
        if df_base[coluna_data_filtro].dt.tz is not None:
            df_base[coluna_data_filtro] = df_base[coluna_data_filtro].dt.tz_localize(None)
        # Remover linhas com data inválida
        df_base = df_base.dropna(subset=[coluna_data_filtro])
    else:
        logger.warning(f"Coluna de data '{coluna_data_filtro}' não encontrada para gráfico")
        return []
    
    if df_base.empty:
        return []
    
    # Gerar pontos do gráfico com média móvel
    # Incluir o próximo intervalo no eixo X (ex: às 08:06 já mostrar 09:00)
    limite_exibicao = agora + timedelta(minutes=intervalo_minutos)
    dados_grafico = []
    ponto_atual = data_inicial
    
    while ponto_atual <= limite_exibicao:
        valor = None
        registros = 0
        
        # Para CONTAGEM: usar o intervalo do gráfico como janela (contagem por período)
        # Para OUTROS: usar a média móvel configurada
        if tipo_calculo == 'contagem':
            # Contagem: janela = intervalo entre pontos do gráfico
            janela_fim = ponto_atual
            janela_inicio = ponto_atual - timedelta(minutes=intervalo_minutos)
        else:
            # Outros tipos: janela = média móvel configurada
            janela_fim = ponto_atual
            janela_inicio = ponto_atual - timedelta(hours=janela_media_horas)
        
        # Filtrar dados dentro da janela (usando pd.Timestamp para compatibilidade)
        janela_inicio_ts = pd.Timestamp(janela_inicio)
        janela_fim_ts = pd.Timestamp(janela_fim)
        
        mask = (df_base[coluna_data_filtro] >= janela_inicio_ts) & (df_base[coluna_data_filtro] <= janela_fim_ts)
        df_janela = df_base[mask]
        if contagem_por == 'ocorrencia' and coluna_ocorrencia and coluna_ocorrencia in df_janela.columns:
            df_janela = df_janela.drop_duplicates(subset=[coluna_ocorrencia], keep='first')
        registros = len(df_janela)
        
        # Calcular valor do indicador para esta janela
        if not df_janela.empty:
            if tipo_calculo == 'diferenca_tempo' and coluna_data_inicio and coluna_data_fim:
                # Média móvel de X horas para diferença de tempo
                diferencas = calcular_diferenca_tempo(df_janela, coluna_data_inicio, coluna_data_fim, unidade)
                diferencas_validas = diferencas.dropna()
                if not diferencas_validas.empty:
                    valor = float(diferencas_validas.mean())
                    
            elif tipo_calculo == 'contagem':
                # Contagem direta no intervalo (total por hora)
                valor = len(df_janela)
                
            elif tipo_calculo == 'media' and coluna_data_fim:
                if coluna_data_fim in df_janela.columns:
                    serie = pd.to_numeric(df_janela[coluna_data_fim], errors='coerce')
                    serie_valida = serie.dropna()
                    if not serie_valida.empty:
                        valor = float(serie_valida.mean())
                        
            elif tipo_calculo == 'soma' and coluna_data_fim:
                if coluna_data_fim in df_janela.columns:
                    serie = pd.to_numeric(df_janela[coluna_data_fim], errors='coerce')
                    serie_valida = serie.dropna()
                    if not serie_valida.empty:
                        valor = float(serie_valida.sum())
            
            elif tipo_calculo == 'percentual_meta' and coluna_data_inicio and coluna_data_fim and meta_valor is not None:
                op = meta_operador if meta_operador in ('<=', '>=') else '<='
                dif = calcular_diferenca_tempo(df_janela, coluna_data_inicio, coluna_data_fim, unidade_medida).dropna()
                if not dif.empty:
                    dentro = (dif <= float(meta_valor)).sum() if op == '<=' else (dif >= float(meta_valor)).sum()
                    total = len(dif)
                    valor = round(100.0 * dentro / total, 2) if total else None
        
        # label: fim do período (para histórico). display_label: horário atual se período em andamento
        label_hora = ponto_atual.strftime('%H:%M')
        display_label = agora.strftime('%H:%M') if ponto_atual > agora else label_hora
        dados_grafico.append({
            'timestamp': ponto_atual.strftime('%Y-%m-%d %H:%M:%S'),
            'label': label_hora,
            'display_label': display_label,
            'valor': valor,
            'registros_janela': registros
        })
        
        # Avançar para o próximo ponto
        ponto_atual = ponto_atual + timedelta(minutes=intervalo_minutos)
    
    janela_info = f"intervalo {intervalo_minutos}min" if tipo_calculo == 'contagem' else f"média móvel {janela_media_horas}h"
    logger.info(f"Gráfico gerado: {len(dados_grafico)} pontos, {janela_info}, intervalo de {intervalo_minutos}min")
    
    return dados_grafico
