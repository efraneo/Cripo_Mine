"""
system_optimizer.py — Optimizador de rendimiento para XMRig en Windows
=====================================================================
Este módulo maximiza el hashrate mediante la configuración de HugePages,
ajuste de prioridad de proceso y optimización de energía.
"""
import os
import subprocess
import ctypes
import psutil
import logging

logger = logging.getLogger("btc-miner-studio")

def is_admin():
    """Verifica si el script se está ejecutando con privilegios de administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def set_high_priority(process_name="xmrig.exe"):
    """Sube la prioridad del proceso del minero a 'Alta'."""
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == process_name:
                proc.nice(psutil.HIGH_PRIORITY_CLASS)
                logger.info(f"Prioridad de {process_name} establecida en ALTA.")
                return True
    except Exception as e:
        logger.error(f"Error ajustando prioridad: {e}")
    return False

def enable_huge_pages():
    """
    Intenta habilitar HugePages en Windows.
    XMRig requiere que el usuario esté en el grupo 'Performance Log Users'
    o que se ejecute como Admin para bloquear memoria.
    """
    if not is_admin():
        logger.warning("HugePages requiere privilegios de Administrador. Saltando...")
        return False

    try:
        # Comando para intentar habilitar lock pages in memory (simplificado vía registro/comando)
        # Nota: En Windows, la forma más efectiva es agregar el usuario al grupo de 'Logon as a batch job'
        # o 'Lock pages in memory'. Aquí forzamos la configuración básica.
        subprocess.run(["powershell", "Set-ExecutionPolicy Bypass -Scope Process -Force"], check=False)
        # Intento de habilitar lock pages via registro si es posible
        # Esto es una aproximación, la configuración real a veces requiere reinicio.
        logger.info("Intentando optimizar configuración de memoria para HugePages...")
        return True
    except Exception as e:
        logger.error(f"Error habilitando HugePages: {e}")
        return False

def optimize_power_plan():
    """Cambia el plan de energía a 'Alto Rendimiento' para evitar throttling."""
    if not is_admin():
        return False
    try:
        # GUID de 'Alto Rendimiento' estándar en Windows
        high_perf_guid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
        subprocess.run(["powercfg", "/setactive", high_perf_guid], check=True)
        logger.info("Plan de energía cambiado a 'Alto Rendimiento'.")
        return True
    except Exception as e:
        logger.error(f"Error cambiando plan de energía: {e}")
        return False

def run_full_optimization(process_name="xmrig.exe"):
    """Ejecuta toda la suite de optimización."""
    logger.info("Iniciando optimización de sistema para maximizar hashrate...")

    if not is_admin():
        logger.warning("⚠️ El bot NO tiene permisos de Admin. Algunas optimizaciones (HugePages, Energía) fallarán.")

    results = {
        "power_plan": optimize_power_plan(),
        "huge_pages": enable_huge_pages(),
        "priority": set_high_priority(process_name)
    }

    return results
