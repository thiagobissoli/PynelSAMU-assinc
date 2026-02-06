"""
Cache de indicadores calculados por dashboard.
Calcula uma vez no backend e entrega para todas as telas.
"""

import os
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache: {(dashboard_id, mode): {"indicadores": [...], "arquivo_mtime": float, "timestamp": datetime}}
_cache = {}
# Cache de gráficos: {indicador_id: {"resp": ..., "arquivo_mtime": float}}
_cache_grafico = {}
_lock = threading.Lock()
CACHE_TTL_SECONDS = 300  # 5 min - invalida se dados antigos


def _get_arquivo_mtime():
    """Retorna mtime do arquivo de dados ou 0 se não existir."""
    caminho = os.path.abspath("download/convertido_tabela.xlsx")
    if os.path.exists(caminho):
        try:
            return os.path.getmtime(caminho)
        except OSError:
            pass
    return 0


def invalidate_cache():
    """Invalida todo o cache (chamar quando download concluir)."""
    with _lock:
        _cache.clear()
        _cache_grafico.clear()
        logger.info("Cache de indicadores e gráficos invalidado")


def get_or_calc_indicadores(dashboard, mode):
    """
    Obtém indicadores do cache ou calcula se inválido.
    
    Args:
        dashboard: instância Dashboard
        mode: 'lista' ou 'widgets'
    
    Returns:
        list: indicadores_calculados
    """
    from app.calculo_indicadores import calcular_indicador, calcular_variacao_percentual
    
    arquivo_mtime = _get_arquivo_mtime()
    cache_key = (dashboard.id, mode)
    
    with _lock:
        entry = _cache.get(cache_key)
        if entry and entry.get("arquivo_mtime") == arquivo_mtime:
            age = (datetime.utcnow() - entry.get("timestamp", datetime.min)).total_seconds()
            if age < CACHE_TTL_SECONDS:
                logger.debug(f"Cache hit: dashboard={dashboard.id} mode={mode}")
                return entry["indicadores"]
    
    # Cache miss ou inválido - calcular
    logger.info(f"Calculando indicadores: dashboard={dashboard.id} mode={mode}")
    
    indicadores_calculados = []
    for indicador in dashboard.indicadores:
        if not indicador.ativo:
            continue
        resultado = calcular_indicador(indicador)
        resultado["id"] = indicador.id
        resultado["nome_completo"] = indicador.nome
        resultado["descricao"] = indicador.descricao
        resultado["tipo_calculo"] = indicador.tipo_calculo
        resultado["grafico_habilitado"] = indicador.grafico_habilitado
        resultado["grafico_ultimas_horas"] = indicador.grafico_ultimas_horas
        resultado["grafico_intervalo_minutos"] = indicador.grafico_intervalo_minutos
        resultado["filtro_ultimas_horas"] = indicador.filtro_ultimas_horas
        resultado["ordem"] = indicador.ordem
        resultado["tendencia_inversa"] = indicador.tendencia_inversa
        resultado["cor_subida"] = indicador.cor_subida or "#34c759"
        resultado["cor_descida"] = indicador.cor_descida or "#ff3b30"
        
        variacao = calcular_variacao_percentual(indicador)
        resultado["variacao_percentual"] = variacao.get("variacao_percentual")
        resultado["tendencia"] = variacao.get("tendencia", "neutra")
        
        if mode == "widgets":
            resultado["grafico_historico_habilitado"] = indicador.grafico_historico_habilitado
            resultado["grafico_historico_cor"] = indicador.grafico_historico_cor or "#6c757d"
            resultado["grafico_meta_habilitado"] = indicador.grafico_meta_habilitado
            resultado["grafico_meta_cor"] = indicador.grafico_meta_cor or "#ffc107"
            resultado["grafico_meta_estilo"] = indicador.grafico_meta_estilo or "dashed"
        
        indicadores_calculados.append(resultado)
    
    indicadores_calculados.sort(key=lambda x: x.get("ordem", 999))
    
    if mode == "widgets":
        widgets_config = {w.indicador_id: w.to_dict() for w in dashboard.widgets_config}
        for r in indicadores_calculados:
            ind_id = r["id"]
            if ind_id in widgets_config:
                cfg = widgets_config[ind_id]
                r["widget_coluna_span"] = cfg.get("coluna_span", 1)
                r["widget_linha_span"] = cfg.get("linha_span", 1)
                r["widget_grafico_altura"] = cfg.get("grafico_altura", 80)
                r["widget_ordem"] = cfg.get("ordem", r.get("ordem", 999))
            else:
                r["widget_coluna_span"] = 1
                r["widget_linha_span"] = 1
                r["widget_grafico_altura"] = 80
                r["widget_ordem"] = r.get("ordem", 999)
        indicadores_calculados.sort(key=lambda x: x.get("widget_ordem", 999))
    
    with _lock:
        _cache[cache_key] = {
            "indicadores": indicadores_calculados,
            "arquivo_mtime": arquivo_mtime,
            "timestamp": datetime.utcnow(),
        }
    
    return indicadores_calculados


def get_or_calc_grafico(indicador):
    """
    Obtém dados do gráfico do cache ou calcula se inválido.
    
    Args:
        indicador: instância Indicador
    
    Returns:
        dict ou list: resposta JSON do gráfico (dados, ou {atual, historico, meta})
    """
    from app.calculo_indicadores import gerar_dados_grafico
    
    arquivo_mtime = _get_arquivo_mtime()
    cache_key = indicador.id
    
    with _lock:
        entry = _cache_grafico.get(cache_key)
        if entry and entry.get("arquivo_mtime") == arquivo_mtime:
            logger.debug(f"Cache hit gráfico: indicador={cache_key}")
            return entry["resp"]
    
    # Cache miss - calcular
    logger.info(f"Calculando gráfico: indicador={cache_key}")
    horas = indicador.grafico_ultimas_horas or 24
    intervalo = indicador.grafico_intervalo_minutos or 60
    dados = gerar_dados_grafico(indicador, horas=horas, intervalo_minutos=intervalo)
    
    tem_historico = indicador.grafico_historico_habilitado and indicador.grafico_historico_dados
    tem_meta = indicador.grafico_meta_habilitado and indicador.grafico_meta_valor is not None
    
    if tem_historico or tem_meta:
        resp = {'atual': dados}
        if tem_historico:
            from datetime import datetime
            mes_atual = datetime.now().month
            hist = indicador.get_historico_dados_mes(mes_atual)
            valores_historico = []
            for d in dados:
                label = d.get('label', '')
                hora = label.split(':')[0] if ':' in label else (label[:2].zfill(2) if len(label) >= 2 else '')
                val = hist.get(hora)
                valores_historico.append(float(val) if val is not None else None)
            resp['historico'] = valores_historico
            resp['historico_cor'] = indicador.grafico_historico_cor or '#6c757d'
        if tem_meta:
            resp['meta'] = [float(indicador.grafico_meta_valor)] * len(dados)
            resp['meta_cor'] = indicador.grafico_meta_cor or '#ffc107'
            resp['meta_estilo'] = indicador.grafico_meta_estilo or 'dashed'
    else:
        resp = dados
    
    with _lock:
        _cache_grafico[cache_key] = {"resp": resp, "arquivo_mtime": arquivo_mtime}
    
    return resp
