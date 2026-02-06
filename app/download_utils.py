"""
Utilitários para Download Histórico - Melhorias e Validações
Implementa retry, validação, limpeza segura e health checks
"""

import os
import time
import logging
import pandas as pd
from functools import wraps
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')


# ============================================================================
# 1. VALIDAÇÃO DE CREDENCIAIS (Melhoria #1)
# ============================================================================

def validar_credenciais_samu():
    """Valida se credenciais SAMU estão configuradas"""
    username = os.getenv("SAMU_USERNAME", "").strip()
    password = os.getenv("SAMU_PASSWORD", "").strip()
    
    if not username or not password:
        logger.error("❌ CREDENCIAIS SAMU NÃO CONFIGURADAS!")
        logger.error("   Configure as variáveis de ambiente:")
        logger.error("   - SAMU_USERNAME")
        logger.error("   - SAMU_PASSWORD")
        return False
    
    logger.info("✅ Credenciais SAMU validadas")
    return True


# ============================================================================
# 2. RETRY COM EXPONENTIAL BACKOFF (Melhoria #5)
# ============================================================================

def retry_exponential(max_attempts=3, base_delay=2, max_delay=60):
    """
    Decorator para retry com exponential backoff
    
    Args:
        max_attempts: Número máximo de tentativas
        base_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    last_exception = e
                    
                    if attempt >= max_attempts:
                        logger.error(f"❌ Falha após {max_attempts} tentativas: {str(e)}")
                        raise
                    
                    # Calcular delay com exponential backoff
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(f"⚠️  Tentativa {attempt}/{max_attempts} falhou. Aguardando {delay}s...")
                    time.sleep(delay)
            
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


# ============================================================================
# 3. XPATHs COM FALLBACK (Melhoria #2)
# ============================================================================

class XPathManager:
    """Gerencia XPaths com alternativas para cada elemento"""
    
    XPATHS = {
        'username_field': [
            '//*[@id="it_username"]',
            '//input[@name="username"]',
            '//input[@type="text"][1]',
        ],
        'password_field': [
            '//*[@id="it_password"]',
            '//input[@name="password"]',
            '//input[@type="password"]',
        ],
        'login_button': [
            '//*[@id="j_idt9"]/input[2]',
            '//input[@type="submit"][@value="Login"]',
            '//button[contains(text(), "Login")]',
        ],
        'menu_element': [
            '//*[@id="j_idt35:j_idt58"]',
            '//a[@class="menu-principal"]',
            '//div[@class="menu"]//a[1]',
        ],
        'menu_item': [
            '//*[@id="menu_bar"]/ul/li[2]/a/span[2]',
            '//a[contains(text(), "Relatórios")]',
            '//li[@data-menu="reports"]//a',
        ],
    }
    
    @staticmethod
    def tentar_encontrar_elemento(driver, wait, element_key, timeout=10):
        """Tenta encontrar elemento usando XPaths com fallback"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        
        xpaths = XPathManager.XPATHS.get(element_key, [])
        
        for i, xpath in enumerate(xpaths, 1):
            try:
                logger.debug(f"  Tentativa {i}/{len(xpaths)}: {element_key}")
                elemento = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                logger.info(f"✅ Elemento encontrado: {element_key} (tentativa {i})")
                return elemento
            except Exception as e:
                if i < len(xpaths):
                    logger.debug(f"    XPath {i} falhou, tentando próximo...")
                else:
                    logger.error(f"❌ Elemento não encontrado: {element_key} ({str(e)})")
                    raise
        
        raise TimeoutError(f"Elemento {element_key} não encontrado após todas as tentativas")


# ============================================================================
# 4. VALIDAÇÃO DE LOGIN (Melhoria #3)
# ============================================================================

def validar_login(driver, wait, timeout=10):
    """Valida se login foi bem-sucedido"""
    login_url = "https://gestao-es.vskysamu.com.br/vskymanagement/login.jsf"
    
    try:
        # Verificar se saiu da página de login
        wait.until(lambda d: d.current_url != login_url)
        
        # Verificar se página principal carregou (elemento específico)
        time.sleep(2)
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        
        # Tentar encontrar elemento que só existe após login
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "dashboard")), timeout=5)
            logger.info("✅ Login validado com sucesso (dashboard encontrado)")
            return True
        except:
            # Fallback: apenas verificar URL mudou
            logger.info("✅ Login validado (URL alterada)")
            return True
            
    except Exception as e:
        logger.error(f"❌ Validação de login falhou: {str(e)}")
        return False


# ============================================================================
# 6. LEITURA COM ENGINE AUTOMÁTICO (Melhoria #6)
# ============================================================================

def ler_arquivo_excel_seguro(caminho_arquivo, skiprows=5):
    """
    Lê arquivo Excel com engine automático e validação
    
    Args:
        caminho_arquivo: Caminho do arquivo .xls ou .xlsx
        skiprows: Número de linhas a pular
    
    Returns:
        DataFrame validado ou None se falhar
    """
    try:
        logger.info(f"📖 Lendo arquivo: {caminho_arquivo}")
        
        # Tentar com engine automático (detecta formato)
        try:
            data = pd.read_excel(caminho_arquivo, skiprows=skiprows)
        except:
            # Fallback para xlrd (compatibilidade com .xls antigo)
            logger.debug("  Tentando com engine='xlrd'...")
            data = pd.read_excel(caminho_arquivo, engine='xlrd', skiprows=skiprows)
        
        # VALIDAÇÃO #8: Verificar se DataFrame é válido
        if data is None or data.empty:
            logger.error(f"❌ Arquivo vazio ou inválido: {caminho_arquivo}")
            return None
        
        logger.info(f"✅ Arquivo lido com sucesso ({len(data)} linhas)")
        return data
        
    except Exception as e:
        logger.error(f"❌ Erro ao ler arquivo Excel: {str(e)}", exc_info=True)
        return None


# ============================================================================
# 7. LIMPEZA SEGURA DE ARQUIVOS (Melhoria #7 e #8)
# ============================================================================

def salvar_historico_seguro(data, diretorio, nome_arquivo='historico.xlsx'):
    """
    Salva arquivo histórico de forma segura com validação
    
    Args:
        data: DataFrame a ser salvo
        diretorio: Diretório de destino
        nome_arquivo: Nome do arquivo
    
    Returns:
        Caminho do arquivo ou None se falhar
    """
    if data is None or data.empty:
        logger.error("❌ Dados vazios, não salvando arquivo")
        return None
    
    try:
        caminho_novo = os.path.join(diretorio, nome_arquivo)
        
        # ✅ SOLUÇÃO: Salvar com extensão .xlsx primeiro, depois renomear
        # Isso evita o erro "Invalid extension for engine: 'tmp'"
        caminho_temp_xlsx = os.path.join(diretorio, f"_temp_{nome_arquivo}")
        
        logger.debug(f"  Salvando arquivo temporário: {caminho_temp_xlsx}")
        # Salvar diretamente com extensão .xlsx (openpyxl aceita)
        data.to_excel(caminho_temp_xlsx, index=False, engine='openpyxl')
        logger.debug(f"  Arquivo temporário criado: {caminho_temp_xlsx}")
        
        # Verificar integridade (tentar ler de volta)
        try:
            pd.read_excel(caminho_temp_xlsx, nrows=1, engine='openpyxl')
            logger.debug(f"  Arquivo temporário validado com sucesso")
        except Exception as e:
            logger.error(f"❌ Arquivo temporário corrompido: {str(e)}")
            try:
                if os.path.exists(caminho_temp_xlsx):
                    os.remove(caminho_temp_xlsx)
            except:
                pass
            return None
        
        # Renomear para arquivo final (operação atômica)
        if os.path.exists(caminho_novo):
            logger.debug(f"  Removendo arquivo antigo: {caminho_novo}")
            os.remove(caminho_novo)
        
        os.rename(caminho_temp_xlsx, caminho_novo)
        logger.info(f"✅ Arquivo salvo com sucesso: {caminho_novo}")
        return caminho_novo
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar arquivo: {str(e)}", exc_info=True)
        # Limpar arquivo temporário se existir
        try:
            if os.path.exists(caminho_temp_xlsx):
                os.remove(caminho_temp_xlsx)
        except:
            pass
        return None


def limpar_arquivo_xls_seguro(caminho_arquivo):
    """Remove arquivo .xls com tratamento de erro"""
    try:
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
            logger.info(f"🗑️  Arquivo deletado: {os.path.basename(caminho_arquivo)}")
            return True
    except Exception as e:
        logger.error(f"❌ Erro ao deletar arquivo {caminho_arquivo}: {str(e)}")
    
    return False


# ============================================================================
# 9. GERENCIADOR DE CONTEXTO PARA CHROME (Melhoria #9)
# ============================================================================

class ChromeDriverManager:
    """Gerencia ChromeDriver com limpeza automática"""
    
    def __init__(self, driver):
        self.driver = driver
    
    def __enter__(self):
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Limpeza automática ao sair do contexto"""
        if self.driver:
            try:
                logger.info("[CHROME] Encerrando navegador...")
                self.driver.quit()
                logger.info("[CHROME] Navegador encerrado com sucesso")
            except Exception as e:
                logger.error(f"[CHROME] Erro ao encerrar navegador: {str(e)}")
            finally:
                # Forçar limpeza de processos Chrome órfãos
                import psutil
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if 'chromedriver' in proc.info['name'].lower():
                            logger.debug(f"  Limpando processo: {proc.info['pid']}")
                            proc.kill()
                except:
                    pass


# ============================================================================
# TIMEOUTS ESPECÍFICOS (Melhoria #4)
# ============================================================================

class TimeoutConfig:
    """Configuração de timeouts por tipo de elemento"""
    
    LOGIN = 30  # Elementos de login
    NAVIGATION = 20  # Navegação de menus
    DOWNLOAD = 120  # Aguardar download
    REPORT = 60  # Processamento de relatórios
    ELEMENT = 10  # Elementos genéricos
    
    @staticmethod
    def get_timeout(element_type='element'):
        """Retorna timeout apropriado para tipo de elemento"""
        timeouts = {
            'login': TimeoutConfig.LOGIN,
            'navigation': TimeoutConfig.NAVIGATION,
            'download': TimeoutConfig.DOWNLOAD,
            'report': TimeoutConfig.REPORT,
            'element': TimeoutConfig.ELEMENT,
        }
        return timeouts.get(element_type, TimeoutConfig.ELEMENT)
