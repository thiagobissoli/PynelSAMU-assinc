"""
Módulo para geração de indicadores a partir dos dados baixados.
Inclui cache em memória do DataFrame para evitar releitura repetida do disco.
"""

import os
import threading
import pandas as pd
import logging
from datetime import datetime
from app.utils import obter_caminho_arquivo, obter_caminho_arquivo_historico, formatar_tempo

logger = logging.getLogger(__name__)

# ── Cache do DataFrame em memória ──────────────────────────────────────────
# Evita reler o Excel do disco a cada chamada (maior gargalo de performance).
# Invalidação automática pelo mtime do arquivo.
_df_cache = {
    "df": None,
    "mtime": 0,
    "caminho": None,
}
_df_lock = threading.Lock()


def carregar_dados():
    """Carrega os dados do arquivo convertido, com cache em memória.
    
    O DataFrame é cacheado enquanto o arquivo não for modificado (verificado
    pelo mtime). Isso evita chamar pd.read_excel() dezenas de vezes por
    ciclo de dashboard.
    """
    caminho = obter_caminho_arquivo()
    
    if not os.path.exists(caminho):
        logger.warning(f"Arquivo não encontrado: {caminho}")
        return None
    
    try:
        mtime_atual = os.path.getmtime(caminho)
    except OSError:
        mtime_atual = 0
    
    with _df_lock:
        # Cache hit: mesmo arquivo, mesmo mtime
        if (
            _df_cache["df"] is not None
            and _df_cache["caminho"] == caminho
            and _df_cache["mtime"] == mtime_atual
        ):
            logger.debug(f"DataFrame cache hit ({len(_df_cache['df'])} linhas)")
            return _df_cache["df"]
    
    # Cache miss: ler do disco (fora do lock para não bloquear)
    try:
        df = pd.read_excel(caminho, engine='openpyxl')
        logger.info(f"Dados carregados do disco: {len(df)} linhas")
        
        with _df_lock:
            _df_cache["df"] = df
            _df_cache["mtime"] = mtime_atual
            _df_cache["caminho"] = caminho
        
        return df
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        return None


# ── Cache do DataFrame histórico em memória ──────────────────────────────
_df_hist_cache = {
    "df": None,
    "mtime": 0,
    "caminho": None,
}
_df_hist_lock = threading.Lock()


def invalidar_cache_df():
    """Força invalidação do cache do DataFrame (chamar após novo download)."""
    with _df_lock:
        _df_cache["df"] = None
        _df_cache["mtime"] = 0
        _df_cache["caminho"] = None
    with _df_hist_lock:
        _df_hist_cache["df"] = None
        _df_hist_cache["mtime"] = 0
        _df_hist_cache["caminho"] = None
    logger.info("Cache do DataFrame e histórico invalidado")


def carregar_dados_historico():
    """Carrega os dados do arquivo histórico, com cache em memória.
    
    OTIMIZAÇÃO: mesma estratégia de cache do carregar_dados() para
    evitar reler o Excel histórico do disco repetidamente.
    """
    caminho = obter_caminho_arquivo_historico()
    
    if not os.path.exists(caminho):
        logger.warning(f"Arquivo histórico não encontrado: {caminho}")
        return None
    
    try:
        mtime_atual = os.path.getmtime(caminho)
    except OSError:
        mtime_atual = 0
    
    with _df_hist_lock:
        if (
            _df_hist_cache["df"] is not None
            and _df_hist_cache["caminho"] == caminho
            and _df_hist_cache["mtime"] == mtime_atual
        ):
            logger.debug(f"DataFrame histórico cache hit ({len(_df_hist_cache['df'])} linhas)")
            return _df_hist_cache["df"]
    
    try:
        df = pd.read_excel(caminho, engine='openpyxl')
        logger.info(f"Dados históricos carregados do disco: {len(df)} linhas")
        
        with _df_hist_lock:
            _df_hist_cache["df"] = df
            _df_hist_cache["mtime"] = mtime_atual
            _df_hist_cache["caminho"] = caminho
        
        return df
    except Exception as e:
        logger.error(f"Erro ao carregar dados históricos: {e}")
        return None


def gerar_indicadores_gerais(df):
    """Gera indicadores gerais a partir dos dados"""
    if df is None or df.empty:
        return {}
    
    try:
        from app.utils import formatar_data_hora_sao_paulo
        indicadores = {
            'total_ocorrencias': len(df),
            'data_processamento': formatar_data_hora_sao_paulo(datetime.utcnow()),
        }
        
        # Tentar identificar colunas comuns
        colunas = df.columns.tolist()
        
        # Contar por tipo de ocorrência (se houver coluna de tipo)
        colunas_tipo = [c for c in colunas if 'tipo' in c.lower() or 'ocorrencia' in c.lower()]
        if colunas_tipo:
            tipo_col = colunas_tipo[0]
            indicadores['por_tipo'] = df[tipo_col].value_counts().to_dict()
        
        # Contar por status (se houver)
        colunas_status = [c for c in colunas if 'status' in c.lower() or 'situacao' in c.lower()]
        if colunas_status:
            status_col = colunas_status[0]
            indicadores['por_status'] = df[status_col].value_counts().to_dict()
        
        # Estatísticas de tempo (se houver colunas de tempo)
        colunas_tempo = [c for c in colunas if 'tempo' in c.lower() or 'duracao' in c.lower()]
        if colunas_tempo:
            tempo_col = colunas_tempo[0]
            try:
                # Tentar converter para numérico
                tempos = pd.to_numeric(df[tempo_col], errors='coerce')
                tempos_validos = tempos.dropna()
                if not tempos_validos.empty:
                    indicadores['tempo_medio'] = formatar_tempo(tempos_validos.mean())
                    indicadores['tempo_minimo'] = formatar_tempo(tempos_validos.min())
                    indicadores['tempo_maximo'] = formatar_tempo(tempos_validos.max())
            except:
                pass
        
        # Estatísticas por data (se houver coluna de data)
        colunas_data = [c for c in colunas if 'data' in c.lower() or 'date' in c.lower()]
        if colunas_data:
            data_col = colunas_data[0]
            try:
                # OTIMIZAÇÃO: usar variável local em vez de modificar DataFrame cacheado in-place
                col_dt = pd.to_datetime(df[data_col], errors='coerce')
                mask_valido = col_dt.notna()
                col_dt_valido = col_dt[mask_valido]
                if not col_dt_valido.empty:
                    datas_formatadas = col_dt_valido.dt.date
                    indicadores['por_data'] = datas_formatadas.value_counts().to_dict()
                    indicadores['data_mais_recente'] = str(col_dt_valido.max().date())
                    indicadores['data_mais_antiga'] = str(col_dt_valido.min().date())
            except:
                pass
        
        return indicadores
    except Exception as e:
        logger.error(f"Erro ao gerar indicadores: {e}")
        return {'erro': str(e)}


def gerar_resumo_dados(df):
    """Gera um resumo dos dados"""
    if df is None or df.empty:
        return {
            'total_linhas': 0,
            'total_colunas': 0,
            'colunas': [],
            'amostra': []
        }
    
    return {
        'total_linhas': len(df),
        'total_colunas': len(df.columns),
        'colunas': df.columns.tolist(),
        'amostra': df.head(10).to_dict('records') if len(df) > 0 else []
    }


def obter_estatisticas_coluna(df, coluna):
    """Obtém estatísticas de uma coluna específica"""
    if df is None or coluna not in df.columns:
        return None
    
    try:
        serie = df[coluna]
        stats = {
            'nome': coluna,
            'tipo': str(serie.dtype),
            'total': len(serie),
            'nulos': serie.isna().sum(),
            'unicos': serie.nunique(),
        }
        
        # Se for numérico, adicionar estatísticas
        if pd.api.types.is_numeric_dtype(serie):
            stats['media'] = float(serie.mean()) if not serie.empty else None
            stats['mediana'] = float(serie.median()) if not serie.empty else None
            stats['minimo'] = float(serie.min()) if not serie.empty else None
            stats['maximo'] = float(serie.max()) if not serie.empty else None
        
        # Valores mais frequentes
        if not serie.empty:
            top_values = serie.value_counts().head(10).to_dict()
            stats['top_valores'] = {str(k): int(v) for k, v in top_values.items()}
        
        return stats
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas da coluna {coluna}: {e}")
        return None
