"""
Utilitários Selenium para automação de download
"""

import os
import shutil
import time
import logging
import pandas as pd
import platform
import stat
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from datetime import datetime, timedelta
import pytz
import psutil

from app.utils import buscar_arquivos_xls
from app.download_utils import (
    validar_credenciais_samu,
    XPathManager,
    validar_login,
    TimeoutConfig,
    ler_arquivo_excel_seguro,
    salvar_historico_seguro,
    limpar_arquivo_xls_seguro
)

logger = logging.getLogger(__name__)
brasilia_tz = pytz.timezone('America/Sao_Paulo')

# Flag global para controlar modo headless
HEADLESS_MODE = os.getenv("SELENIUM_HEADLESS", "true").lower() in ("1", "true", "yes")


def current_time_brasilia():
    """Retorna hora atual em timezone de Brasília"""
    return datetime.now(brasilia_tz)


def corrigir_permissoes_chromedriver_macos(driver_path):
    """Corrige permissões do ChromeDriver no macOS"""
    if platform.system() != "Darwin":
        return True
    
    if not driver_path or not os.path.exists(driver_path):
        return False
    
    try:
        # Remover atributos de quarentena
        try:
            subprocess.run(["xattr", "-cr", driver_path], 
                         stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, 
                         timeout=2, check=False)
        except:
            try:
                subprocess.run(["xattr", "-d", "com.apple.quarantine", driver_path], 
                             stderr=subprocess.DEVNULL, timeout=2, check=False)
            except:
                pass
        
        # Configurar permissões de execução
        os.chmod(driver_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        return True
    except Exception as e:
        logger.warning(f"Erro ao corrigir permissões do ChromeDriver: {e}")
        return False


def _path_servico_sem_espacos(driver_path):
    """Se o caminho tem espaço, copia para um path sem espaço. No macOS evita /tmp (SIGKILL -9)."""
    if not driver_path or not os.path.exists(driver_path):
        return driver_path
    if " " not in driver_path:
        return driver_path
    # Usar diretório no home (evita /tmp onde o macOS pode matar o processo com -9)
    base = os.path.expanduser("~/.pynel_samu")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception as e:
        logger.warning(f"Não foi possível criar {base}: {e}")
        return driver_path
    dest = os.path.join(base, "chromedriver")
    try:
        # Remover cópia antiga para evitar arquivo corrompido ou bloqueado
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError as e:
                logger.warning(f"Removendo chromedriver antigo: {e}")
        shutil.copy2(driver_path, dest)
        os.chmod(dest, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        if platform.system() == "Darwin":
            corrigir_permissoes_chromedriver_macos(dest)
        logger.info(f"ChromeDriver copiado para path sem espaço: {dest}")
        return dest
    except Exception as e:
        logger.warning(f"Não foi possível copiar chromedriver para path sem espaço: {e}")
        return driver_path


def configurar_navegador():
    """Configura o navegador Selenium"""
    diretorio_download = os.getenv("DOWNLOAD_DIR", os.path.abspath("download"))
    
    if not os.path.exists(diretorio_download):
        os.makedirs(diretorio_download, exist_ok=True)
        logger.info(f"Diretório de download criado: {diretorio_download}")
    
    logger.info(f"Configurando navegador (headless={HEADLESS_MODE})")

    chrome_options = Options()
    if HEADLESS_MODE:
        chrome_options.add_argument("--headless=new")
    else:
        chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    chrome_prefs = {
        "download.default_directory": diretorio_download,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "safebrowsing.disable_download_protection": True,
        "profile.default_content_settings.popups": 0,
        "profile.content_settings.exceptions.automatic_downloads.*.setting": 1
    }
    chrome_options.add_experimental_option("prefs", chrome_prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    use_wdm = os.getenv("USE_WDM", "true").lower() in ("true", "1", "yes")
    chrome_bin = os.getenv("CHROME_BIN")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    
    if chrome_bin and os.path.exists(chrome_bin):
        chrome_options.binary_location = chrome_bin
        logger.info(f"Usando Chrome/Chromium: {chrome_bin}")
    
    servico = None
    
    # Preferir webdriver-manager quando USE_WDM=true para garantir driver compatível com o Chrome instalado.
    # O cache em ~/.wdm pode ter driver antigo (ex.: 142) enquanto o Chrome já está em 144.
    if use_wdm:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            os.environ["WDM_LOCAL"] = "1"
            driver_path = ChromeDriverManager().install()
            logger.info(f"ChromeDriver (compatível com Chrome instalado): {driver_path}")
            corrigir_permissoes_chromedriver_macos(driver_path)
            servico = Service(_path_servico_sem_espacos(driver_path))
        except Exception as e:
            logger.error(f"ERRO ao instalar ChromeDriver via webdriver-manager: {e}")
            raise
    elif chromedriver_path and os.path.exists(chromedriver_path):
        servico = Service(_path_servico_sem_espacos(chromedriver_path))
        logger.info(f"Usando ChromeDriver do sistema: {chromedriver_path}")
    else:
        # Fallback: cache manual ou caminhos do sistema
        wdm_cache_path = os.path.expanduser("~/.wdm/drivers/chromedriver")
        cached_driver = None
        if os.path.exists(wdm_cache_path):
            try:
                for root, dirs, files in os.walk(wdm_cache_path):
                    for file in files:
                        if file == "chromedriver" or file == "chromedriver.exe":
                            cached_driver = os.path.join(root, file)
                            break
                    if cached_driver:
                        break
            except Exception:
                pass
        if cached_driver and os.path.exists(cached_driver):
            logger.info(f"Usando ChromeDriver do cache: {cached_driver}")
            corrigir_permissoes_chromedriver_macos(cached_driver)
            servico = Service(_path_servico_sem_espacos(cached_driver))
        else:
            caminhos_driver = ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver"]
            for caminho in caminhos_driver:
                if os.path.exists(caminho):
                    servico = Service(_path_servico_sem_espacos(caminho))
                    logger.info(f"Usando ChromeDriver: {caminho}")
                    break
            if servico is None:
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    os.environ["WDM_LOCAL"] = "1"
                    driver_path = ChromeDriverManager().install()
                    corrigir_permissoes_chromedriver_macos(driver_path)
                    servico = Service(_path_servico_sem_espacos(driver_path))
                except Exception as e:
                    logger.error(f"ERRO ao instalar ChromeDriver: {e}")
                    raise
    
    if servico is None:
        raise RuntimeError("Não foi possível configurar o ChromeDriver")
    
    driver_path = servico.path if hasattr(servico, 'path') else None
    if driver_path and os.path.exists(driver_path) and platform.system() == "Darwin":
        corrigir_permissoes_chromedriver_macos(driver_path)
    
    try:
        navegador = webdriver.Chrome(service=servico, options=chrome_options)
        logger.info("Navegador Chrome criado com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao criar navegador Chrome: {e}")
        raise
    
    try:
        navegador.execute_cdp_cmd("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": diretorio_download
        })
        logger.info(f"Diretório de download configurado: {diretorio_download}")
    except Exception as e:
        logger.warning(f"Erro ao configurar download via CDP: {e}")
    
    return navegador


def processar_arquivos_baixados(arquivo_especifico=None):
    """Processa os arquivos baixados convertendo para convertido_tabela.xlsx"""
    diretorio = os.getenv("DOWNLOAD_DIR", os.path.abspath('download'))
    
    if not os.path.exists(diretorio):
        logger.error(f"Diretório de download não existe: {diretorio}")
        return False
    
    if arquivo_especifico:
        caminho_arquivo = os.path.join(diretorio, arquivo_especifico)
        if not os.path.exists(caminho_arquivo):
            logger.warning(f"⚠️  Arquivo não encontrado: {arquivo_especifico}")
            return False
        
        logger.info(f"[NORMAL] Processando: {arquivo_especifico}")
        
        try:
            data = pd.read_excel(caminho_arquivo, engine='xlrd', skiprows=5)
            new_file_path = os.path.join(diretorio, 'convertido_tabela.xlsx')
            data.to_excel(new_file_path, index=False, engine='openpyxl')
            logger.info(f"[NORMAL] ✅ Arquivo convertido: {new_file_path}")
            
            try:
                os.remove(caminho_arquivo)
                logger.info(f"[NORMAL] 🗑️  Arquivo .xls deletado")
            except Exception as e:
                logger.warning(f"⚠️  Erro ao deletar: {e}")
            
            try:
                from app.cache_indicadores import invalidate_cache
                invalidate_cache()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao converter: {e}")
            return False
    
    arquivos_encontrados = buscar_arquivos_xls(diretorio)
    
    if not arquivos_encontrados:
        logger.warning("Nenhum arquivo .xls encontrado")
        return False
    
    arquivo = arquivos_encontrados[0]
    logger.info(f"[NORMAL] Processando: {arquivo}")
    caminho_arquivo = os.path.join(diretorio, arquivo)

    if os.path.exists(caminho_arquivo):
        try:
            data = pd.read_excel(caminho_arquivo, engine='xlrd', skiprows=5)
            new_file_path = os.path.join(diretorio, 'convertido_tabela.xlsx')
            data.to_excel(new_file_path, index=False, engine='openpyxl')
            logger.info(f"[NORMAL] ✅ Arquivo convertido")
            
            try:
                os.remove(caminho_arquivo)
            except Exception as e:
                logger.warning(f"⚠️  Erro ao deletar: {e}")
            
            try:
                from app.cache_indicadores import invalidate_cache
                invalidate_cache()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao converter: {e}")
            return False
    
    return False


def processar_arquivo_historico(arquivo_especifico=None):
    """Processa o arquivo histórico baixado"""
    diretorio = os.getenv("DOWNLOAD_DIR", os.path.abspath('download'))
    
    if not os.path.exists(diretorio):
        logger.error(f"❌ Diretório não existe: {diretorio}")
        return False
    
    if arquivo_especifico:
        caminho_arquivo = os.path.join(diretorio, arquivo_especifico)
        if not os.path.exists(caminho_arquivo):
            logger.warning(f"⚠️  Arquivo não encontrado: {arquivo_especifico}")
            arquivo_especifico = None
    
    if not arquivo_especifico:
        arquivos_encontrados = buscar_arquivos_xls(diretorio)
        if not arquivos_encontrados:
            logger.warning("⚠️  Nenhum arquivo .xls encontrado")
            return False
        arquivo = arquivos_encontrados[0]
        caminho_arquivo = os.path.join(diretorio, arquivo)
    else:
        arquivo = arquivo_especifico
        caminho_arquivo = os.path.join(diretorio, arquivo)

    try:
        logger.info(f"[HIST] Lendo arquivo: {caminho_arquivo}")
        data = ler_arquivo_excel_seguro(caminho_arquivo, skiprows=5)
        
        if data is None or data.empty:
            logger.error(f"❌ Arquivo vazio ou inválido")
            return False
        
        logger.info(f"[HIST] ✅ Dados validados ({len(data)} linhas)")
        
        new_file_path_historico = salvar_historico_seguro(data, diretorio, 'historico.xlsx')
        
        if new_file_path_historico is None:
            logger.error(f"❌ Falha ao salvar histórico")
            return False
        
        logger.info(f"[HIST] ✅ Arquivo salvo: {new_file_path_historico}")
        
        if limpar_arquivo_xls_seguro(caminho_arquivo):
            logger.info(f"[HIST] 🗑️  Arquivo .xls deletado")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao processar histórico: {str(e)}")
        return False


def baixar_arquivo_sistema(dias_atras=1, data_inicio=None, data_fim=None):
    """
    Baixa arquivo do sistema SAMU
    
    Args:
        dias_atras: Número de dias para buscar
        data_inicio: Data de início no formato DD/MM/YYYY (opcional)
        data_fim: Data de fim no formato DD/MM/YYYY (opcional)
    
    Returns:
        bool: True se sucesso, False caso contrário
    """
    navegador = None
    diretorio = os.getenv("DOWNLOAD_DIR", os.path.abspath('download'))
    
    if not os.path.exists(diretorio):
        os.makedirs(diretorio, exist_ok=True)
    
    try:
        if data_inicio and data_fim:
            logger.info(f"Download (período: {data_inicio} a {data_fim})")
        else:
            agora = current_time_brasilia()
            data_inicio = (agora - timedelta(days=dias_atras)).strftime("%d/%m/%Y")
            data_fim = agora.strftime("%d/%m/%Y")
            logger.info(f"Download (período: {dias_atras} dias)")
        
        navegador = configurar_navegador()
        wait_login = WebDriverWait(navegador, 60)
        wait_nav = WebDriverWait(navegador, 60)
        wait_report = WebDriverWait(navegador, 60)
        
        logger.info("Acessando sistema SAMU...")
        navegador.get("https://gestao-es.vskysamu.com.br/vskymanagement/login.jsf")
        
        username = os.getenv("SAMU_USERNAME", "")
        password = os.getenv("SAMU_PASSWORD", "")
        
        if not username or not password:
            logger.error("Credenciais não configuradas!")
            return False
        
        logger.info("Realizando login...")
        
        username_field = wait_login.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="it_username"]')))
        username_field.click()
        time.sleep(1)
        username_field.clear()
        username_field.send_keys(username)
        
        password_field = wait_login.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="it_password"]')))
        password_field.click()
        time.sleep(1)
        password_field.clear()
        password_field.send_keys(password)
        time.sleep(1)
        
        login_button = wait_login.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="j_idt9"]/input[2]')))
        login_button.click()
        time.sleep(5)
        
        try:
            wait_login.until(lambda driver: driver.current_url != "https://gestao-es.vskysamu.com.br/vskymanagement/login.jsf")
            logger.info("Login realizado com sucesso")
        except TimeoutException:
            logger.warning("Timeout ao aguardar login")
            time.sleep(3)
        
        logger.info("Navegando para relatórios...")
        
        # Aguardar página carregar completamente
        time.sleep(5)
        
        # Estratégia 1: Tentar usar XPathManager com fallback
        menu_encontrado = False
        try:
            from app.download_utils import XPathManager
            menu_element = XPathManager.tentar_encontrar_elemento(
                navegador, wait_nav, 'menu_element', timeout=20
            )
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_element)
            time.sleep(2)
            try:
                menu_element.click()
                menu_encontrado = True
                logger.info("Menu principal clicado (XPathManager)")
            except:
                navegador.execute_script("arguments[0].click();", menu_element)
                menu_encontrado = True
                logger.info("Menu principal clicado (JavaScript)")
        except Exception as e:
            logger.debug(f"XPathManager falhou: {e}")
        
        # Estratégia 2: Tentar múltiplos XPaths alternativos
        if not menu_encontrado:
            xpaths_menu = [
                '//*[@id="j_idt35:j_idt58"]',
                '//a[contains(@class, "menu")]',
                '//div[contains(@class, "menu")]//a[1]',
                '//ul[@id="menu_bar"]//a[contains(text(), "Relatórios")]',
                '//a[contains(text(), "Relatórios")]',
                '//*[contains(@id, "menu")]',
            ]
            
            for xpath in xpaths_menu:
                try:
                    menu_element = WebDriverWait(navegador, 5).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_element)
                    time.sleep(2)
                    try:
                        menu_element.click()
                        menu_encontrado = True
                        logger.info(f"Menu encontrado com XPath alternativo")
                        break
                    except:
                        navegador.execute_script("arguments[0].click();", menu_element)
                        menu_encontrado = True
                        logger.info(f"Menu clicado via JavaScript")
                        break
                except:
                    continue
        
        if not menu_encontrado:
            logger.warning("Menu principal não encontrado, tentando navegar diretamente para relatórios")
        
        time.sleep(3)
        
        # Navegar para submenu de relatórios
        submenu_encontrado = False
        xpaths_submenu = [
            '//*[@id="menu_bar"]/ul/li[2]/a/span[2]',
            '//a[contains(text(), "Relatórios")]',
            '//ul[@id="menu_bar"]//a[contains(text(), "Relatórios")]',
            '//li[contains(@class, "menu")]//a[contains(text(), "Relatórios")]',
            '//*[contains(@id, "menu")]//a[contains(text(), "Relatórios")]',
        ]
        
        for xpath in xpaths_submenu:
            try:
                menu_item = WebDriverWait(navegador, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", menu_item)
                time.sleep(2)
                menu_item.click()
                submenu_encontrado = True
                logger.info(f"Submenu encontrado")
                break
            except:
                continue
        
        if not submenu_encontrado:
            logger.warning("Submenu não encontrado, tentando continuar...")
        
        time.sleep(2)
        
        # Navegar para relatório de ocorrências
        relatorio_encontrado = False
        xpaths_relatorio = [
            '//*[@id="menu_bar"]/ul/li[2]/ul/li[2]/a',
            '//a[contains(text(), "Ocorrências")]',
            '//a[contains(text(), "Relatório") and contains(text(), "Ocorrência")]',
            '//ul[@id="menu_bar"]//a[contains(text(), "Ocorrências")]',
            '//*[@id="menu_bar"]/ul/li[2]/ul/li[2]/ul/li[14]/a/span',
            '//a[contains(@href, "ocorrencia") or contains(@href, "relatorio")]',
        ]
        
        for xpath in xpaths_relatorio:
            try:
                elemento = WebDriverWait(navegador, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                elemento.click()
                relatorio_encontrado = True
                logger.info(f"Relatório encontrado")
                time.sleep(2)
                break
            except:
                continue
        
        # Se encontrou o primeiro nível, tentar o segundo
        if relatorio_encontrado:
            time.sleep(1)
            xpaths_relatorio_final = [
                '//*[@id="menu_bar"]/ul/li[2]/ul/li[2]/ul/li[14]/a/span',
                '//a[contains(text(), "Ocorrências")]',
                '//span[contains(text(), "Ocorrências")]',
            ]
            for xpath in xpaths_relatorio_final:
                try:
                    elemento = WebDriverWait(navegador, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    elemento.click()
                    logger.info(f"Relatório final selecionado")
                    time.sleep(1)
                    break
                except:
                    continue
        
        if not relatorio_encontrado:
            logger.error("Erro ao navegar para relatório de ocorrências")
            # Tentar uma última vez com timeout maior
            try:
                wait_report.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="menu_bar"]/ul/li[2]/ul/li[2]/a'))).click()
                time.sleep(1)
                wait_report.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="menu_bar"]/ul/li[2]/ul/li[2]/ul/li[14]/a/span'))).click()
                logger.info("Relatório de ocorrências selecionado (última tentativa)")
                relatorio_encontrado = True
            except TimeoutException:
                logger.error("Falha definitiva ao navegar para relatório")
                # Capturar screenshot para debug
                try:
                    screenshot_path = os.path.join(diretorio, 'erro_navegacao.png')
                    navegador.save_screenshot(screenshot_path)
                    logger.info(f"Screenshot salvo em: {screenshot_path}")
                except Exception as e:
                    logger.debug(f"Erro ao salvar screenshot: {e}")
                return False
        
        logger.info(f"Período: {data_inicio} a {data_fim}")
        time.sleep(2)
        
        campo_inicio = navegador.find_element(By.XPATH, '//*[@id="frm_relatorios:itDataInicial_input"]')
        campo_inicio.clear()
        campo_inicio.send_keys(data_inicio)
        time.sleep(1)
        
        campo_fim = navegador.find_element(By.XPATH, '//*[@id="frm_relatorios:itDataFinal_input"]')
        campo_fim.clear()
        campo_fim.send_keys(data_fim)
        time.sleep(2)
        
        try:
            botao_confirmar = WebDriverWait(navegador, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="frm_relatorios:j_idt230"]'))
            )
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_confirmar)
            time.sleep(0.5)
            botao_confirmar.click()
        except TimeoutException:
            pass
        
        botao_validar = wait_report.until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="frm_relatorios:bt_validar_campos"]/span[2]')
        ))
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_validar)
        time.sleep(0.5)
        
        try:
            botao_validar.click()
        except ElementClickInterceptedException:
            navegador.execute_script("arguments[0].click();", botao_validar)
        
        logger.info("Download iniciado")
        time.sleep(3)
        
        try:
            navegador.execute_cdp_cmd("Browser.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": diretorio
            })
        except:
            pass
        
        logger.info("Aguardando download...")
        
        arquivo_normal = None
        tempo_inicio = time.time()
        timeout_espera = 90
        
        while time.time() - tempo_inicio < timeout_espera:
            try:
                arquivos_xls = [f for f in os.listdir(diretorio) if f.endswith('.xls') and not f.endswith('.crdownload')]
                if arquivos_xls:
                    arquivo_normal = arquivos_xls[0]
                    logger.info(f"✅ Arquivo encontrado: {arquivo_normal}")
                    time.sleep(2)
                    break
                time.sleep(1)
            except:
                time.sleep(1)
        
        if arquivo_normal:
            logger.info("Download concluído!")
            processar_arquivos_baixados(arquivo_especifico=arquivo_normal)
            return True
        else:
            logger.error("Download não foi concluído")
            return False
        
    except Exception as e:
        logger.error(f"❌ Erro ao baixar arquivo: {e}", exc_info=True)
        return False
    finally:
        if navegador:
            fechar_navegador(navegador)


def fechar_navegador(navegador):
    """Fecha o navegador de forma segura"""
    try:
        if navegador:
            navegador.quit()
            logger.info("Navegador encerrado")
    except Exception as e:
        logger.warning(f"Erro ao fechar navegador: {e}")
    
    time.sleep(2)
    
    try:
        current_process = psutil.Process()
        for proc in current_process.children(recursive=True):
            try:
                proc_name = proc.name().lower()
                if "chrome" in proc_name or "chromedriver" in proc_name:
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        logger.warning(f"Erro ao limpar processos: {e}")
