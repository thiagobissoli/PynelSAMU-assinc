import pandas as pd
import os
from datetime import datetime

try:
    import pytz
    BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')
except Exception:
    BRASILIA_TZ = None


def formatar_data_hora_sao_paulo(valor, fmt='%d/%m/%Y %H:%M:%S'):
    """Converte datetime (armazenado em UTC/naive) para horário de São Paulo e formata.
    Usar em toda exibição de data/hora no sistema.
    """
    if valor is None:
        return ''
    if isinstance(valor, str):
        return valor
    if not hasattr(valor, 'strftime'):
        return str(valor)
    try:
        if BRASILIA_TZ is None:
            return valor.strftime(fmt)
        dt = valor
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        else:
            dt = dt.astimezone(pytz.utc)
        return dt.astimezone(BRASILIA_TZ).strftime(fmt)
    except Exception:
        return valor.strftime(fmt)


def formatar_tempo(minutos):
    """Formata minutos em formato HH:MM:SS"""
    if minutos is None or pd.isna(minutos):
        return "00:00:00"
    total_segundos = int(minutos * 60)
    horas, segundos_restantes = divmod(total_segundos, 3600)
    minutos, segundos = divmod(segundos_restantes, 60)
    return f"{horas:02}:{minutos:02}:{segundos:02}"


def formatar_tempo_exibicao(valor, unidade='minutos'):
    """Formata diferença de tempo conforme a Unidade do indicador.
    - minutos → MM:SS (ex: 90.5 min → 90:30)
    - segundos → "XX seg" (ex: 125 → "125 seg")
    - horas → HH:MM:SS (ex: 1.5 h → 01:30:00)
    """
    if valor is None:
        return "00:00" if (unidade or '').lower() != 'segundos' else "0 seg"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "00:00" if (unidade or '').lower() != 'segundos' else "0 seg"
    if pd.isna(v):
        return "00:00" if (unidade or '').lower() != 'segundos' else "0 seg"
    u = (unidade or 'minutos').strip().lower()
    if u == 'segundos':
        return f"{int(round(v))} seg"
    if u == 'horas' or u == 'dias':
        # horas ou dias → HH:MM:SS h (dias: valor em dias convertido para total de horas)
        mult = 3600 if u == 'horas' else 86400
        total_seg = int(round(v * mult))
        total_seg = max(0, total_seg)
        h, rest = divmod(total_seg, 3600)
        m, s = divmod(rest, 60)
        return f"{h:02d}:{m:02d}:{s:02d} h"
    # minutos → MM:SS min
    total_seg = int(round(v * 60))
    total_seg = max(0, total_seg)
    m, s = divmod(total_seg, 60)
    return f"{m:02d}:{s:02d} min"


def formatar_valor_indicador(valor, tipo_calculo='diferenca_tempo', unidade='minutos'):
    """Formata valor para exibição conforme tipo do indicador.
    - diferenca_tempo: conforme Unidade (minutos→MM:SS, segundos→"XX seg", horas→HH:MM:SS)
    - contagem: inteiro
    - percentual_meta (porcentagem): uma casa decimal
    - demais (soma, media, etc.): uma casa decimal
    """
    if valor is None:
        return '--'
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return '--'
    if pd.isna(v):
        return '--'
    if tipo_calculo == 'diferenca_tempo':
        return formatar_tempo_exibicao(v, unidade or 'minutos')
    if tipo_calculo == 'contagem':
        return str(int(round(v)))
    if unidade and unidade.strip().lower() in ('ocorrências', 'regulações', 'empenhos'):
        return str(int(round(v)))
    if tipo_calculo == 'percentual_meta':
        return f"{v:.1f}"
    # soma, media e demais: uma casa decimal
    return f"{v:.1f}"

def obter_caminho_arquivo():
    """Retorna o caminho do arquivo convertido"""
    return os.path.abspath("download/convertido_tabela.xlsx")

def obter_caminho_arquivo_historico():
    """Retorna o caminho do arquivo histórico"""
    return os.path.abspath("download/historico.xlsx")

def buscar_arquivos_xls(diretorio):
    """Retorna uma lista de arquivos .xls no diretório especificado"""
    if not os.path.exists(diretorio):
        return []
    return [arquivo for arquivo in os.listdir(diretorio) if arquivo.endswith(".xls")]

def deletar_arquivos_xls(diretorio):
    """Deleta todos os arquivos .xls no diretório especificado"""
    arquivos_deletados = []
    if not os.path.exists(diretorio):
        return arquivos_deletados
    for arquivo in os.listdir(diretorio):
        if arquivo.endswith(".xls"):
            caminho_arquivo = os.path.join(diretorio, arquivo)
            try:
                os.remove(caminho_arquivo)
                arquivos_deletados.append(arquivo)
            except Exception:
                pass
    return arquivos_deletados
