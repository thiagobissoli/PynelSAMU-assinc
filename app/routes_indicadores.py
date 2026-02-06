"""
Rotas para configuração e visualização de indicadores customizados
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Indicador
from app.calculo_indicadores import calcular_indicador, calcular_todos_indicadores
from app.indicadores import carregar_dados as carregar_dados_indicadores
import json
import logging

logger = logging.getLogger(__name__)

bp_indicadores = Blueprint('indicadores', __name__, url_prefix='/indicadores')


def _parse_float_safe(s):
    """Converte string para float ou None. Aceita: 15, 1.5, 1,5, 1:30 (min:seg)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace(',', '.')
    if ':' in s:
        parts = s.split(':', 1)
        try:
            min_part = float(parts[0].strip())
            seg_part = float(parts[1].strip()) if len(parts) > 1 else 0
            return min_part + seg_part / 60
        except (TypeError, ValueError):
            return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


@bp_indicadores.route('/api/ordem/<int:id>', methods=['PATCH'])
def api_update_ordem(id):
    """Atualiza apenas a ordem do indicador (edição inline)."""
    indicador = Indicador.query.get_or_404(id)
    data = request.get_json(silent=True) or {}
    ordem = data.get('ordem')
    if ordem is None:
        return jsonify({'success': False, 'error': 'ordem obrigatória'}), 400
    try:
        ordem = int(ordem)
        if ordem < 0:
            ordem = 0
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'ordem deve ser número inteiro'}), 400
    indicador.ordem = ordem
    db.session.commit()
    return jsonify({'success': True, 'ordem': indicador.ordem})


@bp_indicadores.route('/api/coluna-valores')
def coluna_valores():
    """Retorna valores distintos da planilha para a coluna informada (query: coluna=NomeColuna)."""
    coluna = (request.args.get('coluna') or '').strip().strip('\ufeff')  # BOM e espaços
    logger.info(f"coluna_valores: coluna={coluna!r}")
    if not coluna:
        logger.info("coluna_valores: coluna vazia, retornando []")
        return jsonify([])
    try:
        df = carregar_dados_indicadores()
        if df is None:
            logger.warning("coluna_valores: planilha não carregada (df is None)")
            return jsonify([])
        # Normalizar nomes de coluna (BOM / espaços)
        colunas_norm = {c.strip().strip('\ufeff'): c for c in df.columns}
        col_real = colunas_norm.get(coluna) or (coluna if coluna in df.columns else None)
        if col_real is None:
            logger.warning(f"coluna_valores: coluna {coluna!r} não encontrada. Amostra: {list(df.columns)[:20]}")
            return jsonify([])
        vals = df[col_real].dropna().astype(str).str.strip()
        vals = vals[vals != ''].unique().tolist()
        vals = sorted(vals)
        logger.info(f"coluna_valores: coluna={coluna!r} -> {len(vals)} valores distintos")
        return jsonify(vals)
    except Exception as e:
        logger.exception(f"coluna_valores coluna={coluna!r}: {e}")
        return jsonify([])


@bp_indicadores.route('/config')
def config():
    """Página de configuração de indicadores"""
    indicadores = Indicador.query.order_by(Indicador.ordem, Indicador.nome).all()
    
    # Carregar colunas disponíveis para referência
    df = carregar_dados_indicadores()
    colunas = df.columns.tolist() if df is not None else []
    
    # Min/max para gradiente de cor nas colunas Janela e Período
    vals_janela = [i.filtro_ultimas_horas for i in indicadores if i.filtro_ultimas_horas is not None]
    vals_periodo = [i.grafico_ultimas_horas for i in indicadores if i.grafico_habilitado and i.grafico_ultimas_horas is not None]
    min_janela = min(vals_janela) if vals_janela else None
    max_janela = max(vals_janela) if vals_janela else None
    min_periodo = min(vals_periodo) if vals_periodo else None
    max_periodo = max(vals_periodo) if vals_periodo else None
    
    return render_template('indicadores/config.html',
        indicadores=indicadores, colunas=colunas,
        min_janela=min_janela, max_janela=max_janela,
        min_periodo=min_periodo, max_periodo=max_periodo)


@bp_indicadores.route('/create', methods=['GET', 'POST'])
def create():
    """Criar novo indicador"""
    if request.method == 'POST':
        try:
            # Dados básicos
            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()
            tipo_calculo = request.form.get('tipo_calculo', 'diferenca_tempo')
            coluna_data_inicio = request.form.get('coluna_data_inicio', '').strip() or None
            coluna_data_fim = request.form.get('coluna_data_fim', '').strip() or None
            unidade = request.form.get('unidade', 'minutos').strip()
            ordem = int(request.form.get('ordem', 0) or 0)
            ativo = request.form.get('ativo') == 'on'
            
            # Filtro de tempo
            filtro_ultimas_horas = request.form.get('filtro_ultimas_horas', '').strip()
            filtro_ultimas_horas = int(filtro_ultimas_horas) if filtro_ultimas_horas else None
            coluna_data_filtro = request.form.get('coluna_data_filtro', '').strip() or None
            
            # Contabilizar: linhas vs por ocorrência
            contagem_por = (request.form.get('contagem_por', '') or 'linhas').strip().lower()
            contagem_por = contagem_por if contagem_por in ('linhas', 'ocorrencia') else 'linhas'
            coluna_ocorrencia = request.form.get('coluna_ocorrencia', '').strip() or None
            
            # Meta (% que atinge a meta)
            meta_valor = request.form.get('meta_valor', '').strip()
            meta_valor = float(meta_valor) if meta_valor and meta_valor.replace('.', '', 1).replace('-', '', 1).isdigit() else None
            meta_operador = (request.form.get('meta_operador', '') or '<=').strip()
            if meta_operador not in ('<=', '>='):
                meta_operador = '<='
            
            # Configuração de gráfico
            grafico_habilitado = request.form.get('grafico_habilitado') == 'on'
            grafico_ultimas_horas = request.form.get('grafico_ultimas_horas', '').strip()
            grafico_ultimas_horas = int(grafico_ultimas_horas) if grafico_ultimas_horas else None
            grafico_intervalo_minutos = request.form.get('grafico_intervalo_minutos', '60').strip()
            grafico_intervalo_minutos = int(grafico_intervalo_minutos) if grafico_intervalo_minutos else 60
            grafico_historico_habilitado = request.form.get('grafico_historico_habilitado') == 'on'
            grafico_historico_cor = (request.form.get('grafico_historico_cor', '') or '#6c757d').strip()
            historico_dados = {}
            for mes in range(1, 13):
                mes_key = f'{mes:02d}'
                historico_dados[mes_key] = {}
                for h in range(24):
                    key = f'historico_m{mes_key}_h{h:02d}'
                    val = request.form.get(key, '').strip()
                    if val:
                        try:
                            historico_dados[mes_key][f'{h:02d}'] = float(val)
                        except (TypeError, ValueError):
                            pass
            
            # Configuração de tendência
            tendencia_inversa = request.form.get('tendencia_inversa') == 'on'
            cor_subida = (request.form.get('cor_subida', '') or '#28a745').strip()  # Verde padrão
            cor_descida = (request.form.get('cor_descida', '') or '#dc3545').strip()  # Vermelho padrão
            
            if not nome:
                flash('O nome do indicador é obrigatório!', 'danger')
                df = carregar_dados_indicadores()
                colunas = df.columns.tolist() if df is not None else []
                return render_template('indicadores/form.html', modo='create', colunas=colunas)
            
            # Processar condições: usar índices presentes no form (mais robusto que só num_condicoes)
            condicoes = []
            indices = set()
            for key in request.form:
                if key.startswith('condicao_') and key.endswith('_coluna'):
                    try:
                        idx = int(key.replace('condicao_', '').replace('_coluna', ''))
                        indices.add(idx)
                    except ValueError:
                        pass
            for i in sorted(indices):
                coluna = request.form.get(f'condicao_{i}_coluna', '').strip()
                operador = request.form.get(f'condicao_{i}_operador', '==').strip()
                valor = request.form.get(f'condicao_{i}_valor', '').strip()
                conector = (request.form.get(f'condicao_{i}_conector') or 'and').strip().lower()
                if conector not in ('and', 'or', 'if'):
                    conector = 'and'
                if coluna:
                    condicoes.append({'coluna': coluna, 'operador': operador, 'valor': valor, 'conector': conector})
            
            # Criar indicador
            indicador = Indicador(
                nome=nome,
                descricao=descricao,
                tipo_calculo=tipo_calculo,
                coluna_data_inicio=coluna_data_inicio,
                coluna_data_fim=coluna_data_fim,
                unidade=unidade,
                ordem=ordem,
                ativo=ativo,
                filtro_ultimas_horas=filtro_ultimas_horas,
                coluna_data_filtro=coluna_data_filtro,
                contagem_por=contagem_por,
                coluna_ocorrencia=coluna_ocorrencia if contagem_por == 'ocorrencia' else None,
                meta_valor=meta_valor if tipo_calculo == 'percentual_meta' else None,
                meta_operador=meta_operador if tipo_calculo == 'percentual_meta' else None,
                grafico_habilitado=grafico_habilitado,
                grafico_ultimas_horas=grafico_ultimas_horas,
                grafico_intervalo_minutos=grafico_intervalo_minutos,
                grafico_historico_habilitado=grafico_historico_habilitado,
                grafico_historico_cor=grafico_historico_cor,
                grafico_historico_dados=json.dumps(historico_dados) if any(historico_dados.get(f'{m:02d}', {}) for m in range(1, 13)) else None,
                grafico_meta_habilitado=request.form.get('grafico_meta_habilitado') == 'on',
                grafico_meta_valor=_parse_float_safe(request.form.get('grafico_meta_valor', '')) if request.form.get('grafico_meta_habilitado') == 'on' else None,
                grafico_meta_cor=(request.form.get('grafico_meta_cor', '') or '#ffc107').strip(),
                grafico_meta_estilo=(request.form.get('grafico_meta_estilo', '') or 'dashed').strip()[:20],
                tendencia_inversa=tendencia_inversa,
                cor_subida=cor_subida,
                cor_descida=cor_descida,
                condicoes=json.dumps(condicoes) if condicoes else None
            )
            
            db.session.add(indicador)
            db.session.commit()
            
            flash('Indicador criado com sucesso!', 'success')
            return redirect(url_for('indicadores.config'))
            
        except Exception as e:
            logger.error(f"Erro ao criar indicador: {e}", exc_info=True)
            flash(f'Erro ao criar indicador: {str(e)}', 'danger')
            df = carregar_dados_indicadores()
            colunas = df.columns.tolist() if df is not None else []
            return render_template('indicadores/form.html', modo='create', colunas=colunas)
    
    # GET - mostrar formulário
    df = carregar_dados_indicadores()
    colunas = df.columns.tolist() if df is not None else []
    return render_template('indicadores/form.html', modo='create', colunas=colunas)


@bp_indicadores.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    """Editar indicador existente"""
    indicador = Indicador.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Atualizar dados
            indicador.nome = request.form.get('nome', '').strip()
            indicador.descricao = request.form.get('descricao', '').strip()
            indicador.tipo_calculo = request.form.get('tipo_calculo', 'diferenca_tempo')
            indicador.coluna_data_inicio = request.form.get('coluna_data_inicio', '').strip() or None
            indicador.coluna_data_fim = request.form.get('coluna_data_fim', '').strip() or None
            indicador.unidade = request.form.get('unidade', 'minutos').strip()
            indicador.ordem = int(request.form.get('ordem', 0) or 0)
            indicador.ativo = request.form.get('ativo') == 'on'
            
            # Filtro de tempo
            filtro_ultimas_horas = request.form.get('filtro_ultimas_horas', '').strip()
            indicador.filtro_ultimas_horas = int(filtro_ultimas_horas) if filtro_ultimas_horas else None
            indicador.coluna_data_filtro = request.form.get('coluna_data_filtro', '').strip() or None
            
            # Contabilizar: linhas vs por ocorrência
            contagem_por = (request.form.get('contagem_por', '') or 'linhas').strip().lower()
            indicador.contagem_por = contagem_por if contagem_por in ('linhas', 'ocorrencia') else 'linhas'
            indicador.coluna_ocorrencia = request.form.get('coluna_ocorrencia', '').strip() or None
            if indicador.contagem_por != 'ocorrencia':
                indicador.coluna_ocorrencia = None
            
            # Meta (% que atinge a meta)
            meta_valor = request.form.get('meta_valor', '').strip()
            meta_valor = float(meta_valor) if meta_valor and meta_valor.replace('.', '', 1).replace('-', '', 1).isdigit() else None
            meta_operador = (request.form.get('meta_operador', '') or '<=').strip()
            if meta_operador not in ('<=', '>='):
                meta_operador = '<='
            if indicador.tipo_calculo == 'percentual_meta':
                indicador.meta_valor = meta_valor
                indicador.meta_operador = meta_operador
            else:
                indicador.meta_valor = None
                indicador.meta_operador = None
            
            # Configuração de gráfico
            indicador.grafico_habilitado = request.form.get('grafico_habilitado') == 'on'
            grafico_ultimas_horas = request.form.get('grafico_ultimas_horas', '').strip()
            indicador.grafico_ultimas_horas = int(grafico_ultimas_horas) if grafico_ultimas_horas else None
            grafico_intervalo_minutos = request.form.get('grafico_intervalo_minutos', '60').strip()
            indicador.grafico_intervalo_minutos = int(grafico_intervalo_minutos) if grafico_intervalo_minutos else 60
            indicador.grafico_historico_habilitado = request.form.get('grafico_historico_habilitado') == 'on'
            indicador.grafico_historico_cor = (request.form.get('grafico_historico_cor', '') or '#6c757d').strip()
            historico_dados = {}
            for mes in range(1, 13):
                mes_key = f'{mes:02d}'
                historico_dados[mes_key] = {}
                for h in range(24):
                    key = f'historico_m{mes_key}_h{h:02d}'
                    val = request.form.get(key, '').strip()
                    if val:
                        try:
                            historico_dados[mes_key][f'{h:02d}'] = float(val)
                        except (TypeError, ValueError):
                            pass
            indicador.grafico_historico_dados = json.dumps(historico_dados) if any(historico_dados.get(f'{m:02d}', {}) for m in range(1, 13)) else None
            indicador.grafico_meta_habilitado = request.form.get('grafico_meta_habilitado') == 'on'
            indicador.grafico_meta_valor = _parse_float_safe(request.form.get('grafico_meta_valor', '')) if indicador.grafico_meta_habilitado else None
            indicador.grafico_meta_cor = (request.form.get('grafico_meta_cor', '') or '#ffc107').strip()
            indicador.grafico_meta_estilo = (request.form.get('grafico_meta_estilo', '') or 'dashed').strip()[:20]
            
            # Configuração de tendência
            indicador.tendencia_inversa = request.form.get('tendencia_inversa') == 'on'
            indicador.cor_subida = (request.form.get('cor_subida', '') or '#28a745').strip()
            indicador.cor_descida = (request.form.get('cor_descida', '') or '#dc3545').strip()
            
            if not indicador.nome:
                flash('O nome do indicador é obrigatório!', 'danger')
                df = carregar_dados_indicadores()
                colunas = df.columns.tolist() if df is not None else []
                return render_template('indicadores/form.html', modo='edit', indicador=indicador, colunas=colunas)
            
            # Processar condições: usar índices presentes no form (mais robusto que só num_condicoes)
            condicoes = []
            indices = set()
            for key in request.form:
                if key.startswith('condicao_') and key.endswith('_coluna'):
                    try:
                        idx = int(key.replace('condicao_', '').replace('_coluna', ''))
                        indices.add(idx)
                    except ValueError:
                        pass
            for i in sorted(indices):
                coluna = request.form.get(f'condicao_{i}_coluna', '').strip()
                operador = request.form.get(f'condicao_{i}_operador', '==').strip()
                valor = request.form.get(f'condicao_{i}_valor', '').strip()
                conector = (request.form.get(f'condicao_{i}_conector') or 'and').strip().lower()
                if conector not in ('and', 'or', 'if'):
                    conector = 'and'
                if coluna:
                    condicoes.append({'coluna': coluna, 'operador': operador, 'valor': valor, 'conector': conector})
            indicador.condicoes = json.dumps(condicoes) if condicoes else None
            
            db.session.commit()
            
            flash('Indicador atualizado com sucesso!', 'success')
            return redirect(url_for('indicadores.config'))
            
        except Exception as e:
            logger.error(f"Erro ao editar indicador: {e}", exc_info=True)
            db.session.rollback()
            flash(f'Erro ao atualizar indicador: {str(e)}', 'danger')
            df = carregar_dados_indicadores()
            colunas = df.columns.tolist() if df is not None else []
            indicador = Indicador.query.get(id)
            return render_template('indicadores/form.html', modo='edit', indicador=indicador, colunas=colunas)
    
    # GET - mostrar formulário
    df = carregar_dados_indicadores()
    colunas = df.columns.tolist() if df is not None else []
    return render_template('indicadores/form.html', modo='edit', indicador=indicador, colunas=colunas)


@bp_indicadores.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    """Deletar indicador"""
    indicador = Indicador.query.get_or_404(id)
    
    try:
        db.session.delete(indicador)
        db.session.commit()
        flash('Indicador deletado com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao deletar indicador: {e}", exc_info=True)
        flash(f'Erro ao deletar indicador: {str(e)}', 'danger')
    
    return redirect(url_for('indicadores.config'))


@bp_indicadores.route('/duplicate/<int:id>')
def duplicate(id):
    """Duplicar indicador, adicionando ' copy' ao nome"""
    original = Indicador.query.get_or_404(id)
    try:
        copia = Indicador(
            nome=(original.nome or '').strip() + ' copy',
            descricao=original.descricao,
            coluna_calculo=original.coluna_calculo,
            coluna_data_inicio=original.coluna_data_inicio,
            coluna_data_fim=original.coluna_data_fim,
            tipo_calculo=original.tipo_calculo or 'diferenca_tempo',
            condicoes=original.condicoes,
            unidade=original.unidade,
            filtro_ultimas_horas=original.filtro_ultimas_horas,
            coluna_data_filtro=original.coluna_data_filtro,
            contagem_por=original.contagem_por or 'linhas',
            coluna_ocorrencia=original.coluna_ocorrencia,
            meta_valor=original.meta_valor,
            meta_operador=original.meta_operador or '<=',
            grafico_habilitado=original.grafico_habilitado,
            grafico_ultimas_horas=original.grafico_ultimas_horas,
            grafico_intervalo_minutos=original.grafico_intervalo_minutos or 60,
            grafico_historico_habilitado=original.grafico_historico_habilitado,
            grafico_historico_cor=original.grafico_historico_cor or '#6c757d',
            grafico_historico_dados=original.grafico_historico_dados,
            grafico_meta_habilitado=original.grafico_meta_habilitado,
            grafico_meta_valor=original.grafico_meta_valor,
            grafico_meta_cor=original.grafico_meta_cor or '#ffc107',
            grafico_meta_estilo=original.grafico_meta_estilo or 'dashed',
            tendencia_inversa=original.tendencia_inversa,
            cor_subida=original.cor_subida or '#28a745',
            cor_descida=original.cor_descida or '#dc3545',
            ordem=original.ordem + 1,
            ativo=original.ativo,
        )
        db.session.add(copia)
        db.session.commit()
        flash('Indicador duplicado com sucesso!', 'success')
    except Exception as e:
        logger.error(f"Erro ao duplicar indicador: {e}", exc_info=True)
        flash(f'Erro ao duplicar indicador: {str(e)}', 'danger')
    return redirect(url_for('indicadores.config'))


@bp_indicadores.route('/painel')
def painel():
    """Painel com todos os indicadores calculados"""
    resultados = calcular_todos_indicadores()
    
    # Adicionar informações de gráfico e cores aos resultados
    indicadores = Indicador.query.filter_by(ativo=True).all()
    indicadores_dict = {ind.id: ind for ind in indicadores}
    
    for resultado in resultados:
        ind_id = resultado.get('id')
        if ind_id and ind_id in indicadores_dict:
            ind = indicadores_dict[ind_id]
            resultado['grafico_habilitado'] = ind.grafico_habilitado
            resultado['grafico_ultimas_horas'] = ind.grafico_ultimas_horas
            resultado['grafico_intervalo_minutos'] = ind.grafico_intervalo_minutos
            resultado['cor_subida'] = ind.cor_subida
            resultado['cor_descida'] = ind.cor_descida
            resultado['tendencia_inversa'] = ind.tendencia_inversa
    
    indicadores_com_grafico = {ind.id: ind for ind in indicadores if ind.grafico_habilitado}
    return render_template('indicadores/painel.html', resultados=resultados, indicadores_com_grafico=indicadores_com_grafico)


@bp_indicadores.route('/calcular/<int:id>')
def calcular(id):
    """Calcular um indicador específico (API)"""
    indicador = Indicador.query.get_or_404(id)
    resultado = calcular_indicador(indicador)
    return jsonify(resultado)


@bp_indicadores.route('/testar', methods=['POST'])
def testar():
    """Testar cálculo de indicador antes de salvar (API)"""
    try:
        data = request.get_json()
        
        # Criar indicador temporário para teste
        indicador_temp = {
            'nome': data.get('nome', 'Teste'),
            'tipo_calculo': data.get('tipo_calculo', 'diferenca_tempo'),
            'coluna_data_inicio': data.get('coluna_data_inicio'),
            'coluna_data_fim': data.get('coluna_data_fim'),
            'unidade': data.get('unidade', 'minutos'),
            'condicoes': data.get('condicoes', []),
            'filtro_ultimas_horas': data.get('filtro_ultimas_horas'),
            'coluna_data_filtro': data.get('coluna_data_filtro')
        }
        
        resultado = calcular_indicador(indicador_temp)
        return jsonify(resultado)
        
    except Exception as e:
        logger.error(f"Erro ao testar indicador: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 400


@bp_indicadores.route('/grafico/<int:id>')
def grafico(id):
    """Retorna dados do gráfico de um indicador (API) - usa cache."""
    indicador = Indicador.query.get_or_404(id)
    from app.cache_indicadores import get_or_calc_grafico
    resp = get_or_calc_grafico(indicador)
    return jsonify(resp)
