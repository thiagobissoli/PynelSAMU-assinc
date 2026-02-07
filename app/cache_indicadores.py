"""
Cache de indicadores calculados por dashboard.
Calcula uma vez no backend e entrega para todas as telas.

Otimizações de performance:
- DataFrame é carregado UMA VEZ e compartilhado entre todos os cálculos
- Cache de gráficos em batch (todos de um dashboard de uma só vez)
- Cálculo PARALELO de indicadores e gráficos via ThreadPoolExecutor
- Invalidação inteligente por mtime do arquivo
"""

import os
import threading
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    # Também invalidar cache do DataFrame em memória
    try:
        from app.indicadores import invalidar_cache_df
        invalidar_cache_df()
    except ImportError:
        pass


def get_or_calc_indicadores(dashboard, mode):
    """
    Obtém indicadores do cache ou calcula se inválido.
    
    OTIMIZAÇÃO: carrega o DataFrame UMA VEZ e passa para todos os cálculos,
    evitando N releituras do disco.
    
    Args:
        dashboard: instância Dashboard
        mode: 'lista' ou 'widgets'
    
    Returns:
        list: indicadores_calculados
    """
    from app.calculo_indicadores import calcular_indicador, calcular_variacao_percentual
    from app.indicadores import carregar_dados as carregar_dados_indicadores
    
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
    
    # OTIMIZAÇÃO CRÍTICA: carregar DataFrame UMA VEZ para todos os indicadores
    df = carregar_dados_indicadores()
    
    # Filtrar apenas indicadores ativos
    indicadores_ativos = [ind for ind in dashboard.indicadores if ind.ativo]
    
    def _calcular_um_indicador(indicador):
        """Calcula um indicador + variação. Função isolada para execução paralela."""
        resultado = calcular_indicador(indicador, df=df)
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
        
        variacao = calcular_variacao_percentual(indicador, df=df)
        resultado["variacao_percentual"] = variacao.get("variacao_percentual")
        resultado["tendencia"] = variacao.get("tendencia", "neutra")
        
        if mode == "widgets":
            resultado["grafico_historico_habilitado"] = indicador.grafico_historico_habilitado
            resultado["grafico_historico_cor"] = indicador.grafico_historico_cor or "#6c757d"
            resultado["grafico_meta_habilitado"] = indicador.grafico_meta_habilitado
            resultado["grafico_meta_cor"] = indicador.grafico_meta_cor or "#ffc107"
            resultado["grafico_meta_estilo"] = indicador.grafico_meta_estilo or "dashed"
        
        return resultado
    
    # OTIMIZAÇÃO: calcular TODOS os indicadores em PARALELO
    # Cada cálculo é independente e pandas libera o GIL nas operações em C,
    # então threads oferecem ganho real de performance.
    indicadores_calculados = []
    if len(indicadores_ativos) <= 2:
        # Poucos indicadores: overhead do pool não compensa
        for indicador in indicadores_ativos:
            indicadores_calculados.append(_calcular_um_indicador(indicador))
    else:
        # Muitos indicadores: calcular em paralelo
        max_workers = min(len(indicadores_ativos), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_calcular_um_indicador, ind): ind.id
                for ind in indicadores_ativos
            }
            for future in as_completed(futures):
                try:
                    resultado = future.result()
                    indicadores_calculados.append(resultado)
                except Exception as e:
                    ind_id = futures[future]
                    logger.error(f"Erro ao calcular indicador {ind_id}: {e}")
                    indicadores_calculados.append({
                        "id": ind_id,
                        "nome": f"Indicador {ind_id}",
                        "erro": str(e),
                    })
    
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


def _build_grafico_resp(indicador, dados):
    """Monta resposta do gráfico com séries de histórico e meta quando habilitados."""
    tem_historico = indicador.grafico_historico_habilitado and indicador.grafico_historico_dados
    tem_meta = indicador.grafico_meta_habilitado and indicador.grafico_meta_valor is not None
    
    if tem_historico or tem_meta:
        resp = {'atual': dados}
        if tem_historico:
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
    
    return resp


def get_or_calc_grafico(indicador, df=None):
    """
    Obtém dados do gráfico do cache ou calcula se inválido.
    
    Args:
        indicador: instância Indicador
        df: DataFrame compartilhado (opcional, evita releitura)
    
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
    dados = gerar_dados_grafico(indicador, horas=horas, intervalo_minutos=intervalo, df=df)
    
    resp = _build_grafico_resp(indicador, dados)
    
    with _lock:
        _cache_grafico[cache_key] = {"resp": resp, "arquivo_mtime": arquivo_mtime}
    
    return resp


def get_or_calc_graficos_batch(indicadores_ids):
    """
    Calcula gráficos de MÚLTIPLOS indicadores em uma única chamada.
    
    OTIMIZAÇÃO: carrega o DataFrame UMA VEZ e calcula todos os gráficos,
    em vez de N requests HTTP separados do frontend.
    
    Args:
        indicadores_ids: lista de IDs de indicadores
    
    Returns:
        dict: {indicador_id: resposta_grafico, ...}
    """
    from app.calculo_indicadores import gerar_dados_grafico
    from app.models import Indicador
    from app.indicadores import carregar_dados as carregar_dados_indicadores
    
    arquivo_mtime = _get_arquivo_mtime()
    resultados = {}
    ids_para_calcular = []
    
    # Verificar quais já estão em cache
    with _lock:
        for ind_id in indicadores_ids:
            entry = _cache_grafico.get(ind_id)
            if entry and entry.get("arquivo_mtime") == arquivo_mtime:
                resultados[ind_id] = entry["resp"]
            else:
                ids_para_calcular.append(ind_id)
    
    if not ids_para_calcular:
        logger.debug(f"Batch gráficos: todos {len(indicadores_ids)} em cache")
        return resultados
    
    # Carregar DataFrame UMA VEZ para todos os gráficos pendentes
    logger.info(f"Batch gráficos: calculando {len(ids_para_calcular)} de {len(indicadores_ids)}")
    df = carregar_dados_indicadores()
    
    # Carregar indicadores do banco
    indicadores = Indicador.query.filter(Indicador.id.in_(ids_para_calcular)).all()
    indicadores_map = {ind.id: ind for ind in indicadores}
    
    def _calcular_um_grafico(ind_id):
        """Calcula gráfico de um indicador. Função isolada para execução paralela."""
        indicador = indicadores_map.get(ind_id)
        if not indicador:
            return ind_id, []
        
        horas = indicador.grafico_ultimas_horas or 24
        intervalo = indicador.grafico_intervalo_minutos or 60
        dados = gerar_dados_grafico(indicador, horas=horas, intervalo_minutos=intervalo, df=df)
        
        resp = _build_grafico_resp(indicador, dados)
        
        with _lock:
            _cache_grafico[ind_id] = {"resp": resp, "arquivo_mtime": arquivo_mtime}
        
        return ind_id, resp
    
    # OTIMIZAÇÃO: calcular gráficos em PARALELO
    if len(ids_para_calcular) <= 2:
        for ind_id in ids_para_calcular:
            gid, gresp = _calcular_um_grafico(ind_id)
            resultados[gid] = gresp
    else:
        max_workers = min(len(ids_para_calcular), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_calcular_um_grafico, ind_id): ind_id
                for ind_id in ids_para_calcular
            }
            for future in as_completed(futures):
                try:
                    gid, gresp = future.result()
                    resultados[gid] = gresp
                except Exception as e:
                    fid = futures[future]
                    logger.error(f"Erro ao calcular gráfico {fid}: {e}")
                    resultados[fid] = []
    
    return resultados
