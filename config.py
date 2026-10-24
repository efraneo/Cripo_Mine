"""
config.py — Configuración central del BTC Miner Studio
=======================================================
Carga las variables definidas en .streamlit/secrets.toml, define el catálogo
de pools conocidos y utilidades de formato.

NOMBRES DE VARIABLES DE SECRETS (cópialas en .streamlit/secrets.toml):

    BINANCE_API_KEY        → Clave API de Binance (permiso "Lectura")
    BINANCE_API_SECRET     → Secreto API de Binance
    BTC_PAYOUT_ADDRESS     → Dirección BTC donde quieres recibir el minado
                             (puede ser la dirección de depósito de Binance)
    POOL_URL               → URL stratum del pool (stratum+tcp://host:puerto)
    POOL_USER              → Usuario del pool (si vacío se usa BTC_PAYOUT_ADDRESS)
    POOL_PASSWORD          → Contraseña del pool (casi siempre "x")
    WORKER_NAME            → Nombre del worker (ej: "cpu01")
    MINER_MODE             → python | bench | demo | external
    EXTERNAL_MINER_PATH    → Ruta al binario externo (ej: /usr/bin/xmrig)
    EXTERNAL_MINER_ARGS    → Argumentos extra opcionales para el binario
    CPU_THREADS            → Nº de hilos de CPU para el minero Python
    AUTO_REFRESH_SECONDS   → Segundos entre refrescos del dashboard
    F2POOL_ACCOUNT         → (opcional) cuenta de F2Pool para ver estadísticas
    NICEHASH_API_KEY       → (opcional) clave API NiceHash
    NICEHASH_API_SECRET    → (opcional) secreto API NiceHash
    NICEHASH_ORG_ID        → (opcional) ID de organización NiceHash

V2 — INTERVENCIÓN AGRESIVA (motor multi-pool + Telegram + pagos):

    TELEGRAM_BOT_TOKEN     → Token del bot (BotFather) para alertas/control
    TELEGRAM_CHAT_ID       → Tu chat_id de Telegram
    WALLET_XMR             → Wallet Monero (MoneroOcean / SupportXMR)
    AGGRESSIVE_MODE        → true = motor agresivo con failover
    FAILOVER_MINUTES       → Min sin shares antes de saltar de pool (12)
    ROTATE_MINUTES         → Rotación preventiva cada N min (0 = off)
    CPU_TEMP_MAX           → Pausa térmica automática (85 °C)
    DAILY_SUMMARY_HOUR     → Hora del resumen diario por Telegram (20)
    PAYOUT_ALERT_MIN_BTC   → Balance que dispara aviso de payout (0.0005)

V3.5 — PRUEBA DE GANANCIAS:

    EVIDENCIA_CADA_HORAS   → Cada cuántas horas el bot manda a Telegram
                             la prueba de ganancias (6; 0 = desactivado)

V3.7 — LA HIDRA (agresividad restaurada, 5 cabezas):

    HIDRA_ACTIVA           → true = las 5 cabezas despiertas (true)
    HIDRA_CAIDA_PCT        → % de caída del hashrate que activa la
                             auto-reparación de la VIGÍA (35)
    HIDRA_DEFENDER         → true = el ESCUDO agrega solo las exclusiones
                             de Windows Defender para xmrig (true)
"""
import os
import tempfile

# ---------------------------------------------------------------------------
# Directorios base
# IMPORTANTE (Streamlit Community Cloud): monta el repo en /mount/src con
# sistema de archivos DE SOLO LECTURA. Si no se puede crear/escribir data/,
# logs/ o bin/ junto al código, se hace fallback automático a /tmp
# (el único lugar escribible en la nube de Streamlit).
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _ensure_dir(path: str) -> str:
    """Crea `path` y verifica escritura real; si el FS es de solo lectura
    devuelve una ruta equivalente y escribible bajo /tmp."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except Exception:
        pass
    alt = os.path.join(tempfile.gettempdir(), "btc_miner_studio",
                       os.path.basename(path.rstrip("/\\")) or "data")
    try:
        os.makedirs(alt, exist_ok=True)
    except Exception:
        alt = tempfile.gettempdir()
    return alt


DATA_DIR = _ensure_dir(os.path.join(BASE_DIR, "data"))
LOG_DIR = _ensure_dir(os.path.join(BASE_DIR, "logs"))
BIN_DIR = _ensure_dir(os.path.join(BASE_DIR, "bin"))
# El daemon (run_miner.py) escribe sus métricas en otro archivo para no
# pisar las del modo python del dashboard:
METRICS_FILE = os.environ.get(
    "MINER_METRICS_FILE", os.path.join(DATA_DIR, "metrics.json"))

# ---------------------------------------------------------------------------
# Valores por defecto (se sobreescriben con .streamlit/secrets.toml)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "BINANCE_API_KEY": "",
    "BINANCE_API_SECRET": "",
    "BTC_PAYOUT_ADDRESS": "",
    "POOL_URL": "stratum+tcp://public-pool.io:21496",
    "POOL_USER": "",
    "POOL_PASSWORD": "x",
    "WORKER_NAME": "cpu01",
    "MINER_MODE": "python",      # python | bench | demo | external
    "EXTERNAL_MINER_PATH": "",
    "EXTERNAL_MINER_ARGS": "",
    "CPU_THREADS": 2,
    "AUTO_REFRESH_SECONDS": 5,
    "F2POOL_ACCOUNT": "",
    "NICEHASH_API_KEY": "",
    "NICEHASH_API_SECRET": "",
    "NICEHASH_ORG_ID": "",
    # --- v2: intervención agresiva -------------------------------------
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "WALLET_XMR": "",
    "AGGRESSIVE_MODE": True,
    "FAILOVER_MINUTES": 12,
    "ROTATE_MINUTES": 0,
    "CPU_TEMP_MAX": 85.0,
    "DAILY_SUMMARY_HOUR": 20,
    "PAYOUT_ALERT_MIN_BTC": 0.0005,
    # --- v3.5: prueba de ganancias --------------------------------------
    "EVIDENCIA_CADA_HORAS": 6,
    # --- v3.7: LA HIDRA ---------------------------------------------------
    "HIDRA_ACTIVA": True,
    "HIDRA_CAIDA_PCT": 35.0,
    "HIDRA_DEFENDER": True,
}


def load_secrets() -> dict:
    """Une los secrets de Streamlit con los valores por defecto, sin explotar
    si no existe secrets.toml (útil también fuera de Streamlit)."""
    cfg = dict(DEFAULTS)
    try:
        import streamlit as st
        try:
            sec = dict(st.secrets)  # type: ignore[attr-defined]
        except Exception:
            sec = {}
        for k, v in sec.items():
            if k in DEFAULTS:
                cfg[k] = v
    except Exception:
        pass
    # Tipos numéricos seguros
    try:
        cfg["CPU_THREADS"] = max(1, int(cfg["CPU_THREADS"]))
    except Exception:
        cfg["CPU_THREADS"] = 2
    try:
        cfg["AUTO_REFRESH_SECONDS"] = max(2, int(cfg["AUTO_REFRESH_SECONDS"]))
    except Exception:
        cfg["AUTO_REFRESH_SECONDS"] = 5
    # v2: tipos de los nuevos secrets
    for _k in ("FAILOVER_MINUTES", "ROTATE_MINUTES", "CPU_TEMP_MAX",
               "DAILY_SUMMARY_HOUR", "PAYOUT_ALERT_MIN_BTC",
               "EVIDENCIA_CADA_HORAS", "HIDRA_CAIDA_PCT"):
        try:
            cfg[_k] = float(cfg[_k])
        except Exception:
            pass
    cfg["AGGRESSIVE_MODE"] = str(cfg.get("AGGRESSIVE_MODE", True)).lower() \
        not in ("0", "false", "no", "off")
    return cfg


# ---------------------------------------------------------------------------
# Catálogo de pools conocidos (pago en BTC)
# Fuentes: solo.ckpool.org, public-pool.io, 69pool, kano.is, f2pool, viabtc
# ---------------------------------------------------------------------------
POOL_CATALOG = [
    {
        "nombre": "Public Pool — solo, lowdiff (IDEAL para CPU)",
        "url": "stratum+tcp://public-pool.io:21496",
        "usuario": "tu dirección BTC (o wallet.worker)",
        "nota": "Open source, sin registro, dificultad mínima muy baja: verás "
                "shares aceptados aunque tu hashrate sea pequeño.",
    },
    {
        "nombre": "Solo CKPool — solo mining, sin registro",
        "url": "stratum+tcp://stratum.ckpool.org:3333",
        "usuario": "tu dirección BTC",
        "nota": "Sin registro, pass ignorado. Diff mínima 10,000: con CPU "
                "quizá no veas shares, pero sigue siendo válido (lotería).",
    },
    {
        "nombre": "69Pool — solo público, fee 0.69%",
        "url": "stratum+tcp://solo.69pool.org:3333",
        "usuario": "tu dirección BTC",
        "nota": "Alternativa solo sin registro ni esquemas de pago.",
    },
    {
        "nombre": "Kano.is — PPLNS, vardiff bajo",
        "url": "stratum+tcp://kano.is:3333",
        "usuario": "dirección BTC.worker",
        "nota": "Pool tradicional con dificultad adaptativa baja.",
    },
    {
        "nombre": "F2Pool — PPS+ (requiere cuenta)",
        "url": "stratum+tcp://btc.f2pool.com:3333",
        "usuario": "cuenta_f2pool.worker01",
        "nota": "Pagos estables; crea cuenta en f2pool.com. API de stats "
                "disponible en la pestaña 'Red y Pool'.",
    },
    {
        "nombre": "ViaBTC — PPS (requiere cuenta)",
        "url": "stratum+tcp://btc.viabtc.io:3333",
        "usuario": "cuenta_viabtc.worker01",
        "nota": "Uno de los pools más grandes; requiere cuenta.",
    },
    {
        "nombre": "NiceHash — vende hash y paga en BTC",
        "url": "stratum+tcp://sha256.apply.nicehash.com:3334",
        "usuario": "tu_dirección_BTC",
        "nota": "NiceHash te paga por el hash vendido (no es solo-mining). "
                "Configura retiro automático a Binance en su panel.",
    },
    {
        "nombre": "unMineable — RandomX pagando en BTC (MOTOR AGRESIVO v2)",
        "url": "rx.unmineable.com:3333",
        "usuario": "BTC:<tu_dirección_BTC>.<worker> (o tu alias)",
        "nota": "Endpoint RandomX oficial 2026 (alt: stratum+ssl://rx."
                "unmineable.com:443). Mina con XMRig y convierte a BTC "
                "automáticamente: el pago llega a tu dirección de Binance. "
                "Umbral real vía API (~0.00075 BTC), ajustable en Addresses.",
    },
    {
        "nombre": "MoneroOcean — auto-cambio de algoritmo (paga XMR)",
        "url": "gulf.moneroocean.stream:10128",
        "usuario": "tu wallet Monero",
        "nota": "Con el fork XMRig-MO prueba 13+ algoritmos y se queda con "
                "el más rentable para tu CPU. Paga XMR: Binance NO acepta "
                "XMR desde 2024-02 (delisting), usa wallet propia.",
    },
    {
        "nombre": "SupportXMR — pool veterano Monero (respaldo, paga XMR)",
        "url": "pool.supportxmr.com:3333",
        "usuario": "tu wallet Monero",
        "nota": "Estable desde 2016, vardiff bajo ideal para CPUs pequeñas. "
                "Es el tercer objetivo del failover agresivo.",
    },
]


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------
def format_hashrate(h: float) -> str:
    """Convierte H/s en texto legible (kH/s, MH/s, GH/s...)."""
    try:
        h = float(h)
    except Exception:
        return "—"
    if h <= 0:
        return "0 H/s"
    unidades = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"]
    i = 0
    while h >= 1000.0 and i < len(unidades) - 1:
        h /= 1000.0
        i += 1
    return f"{h:,.2f} {unidades[i]}"


def format_btc(x: float) -> str:
    """Formatea cantidades BTC con 8 decimales."""
    try:
        x = float(x)
    except Exception:
        return "—"
    if abs(x) > 0 and abs(x) < 1e-8:
        return "0.00000000 BTC"
    return f"{x:,.8f} BTC"


def format_usd(x: float) -> str:
    try:
        return f"USD {float(x):,.2f}"
    except Exception:
        return "—"


def format_uptime(seconds: float) -> str:
    try:
        s = int(seconds)
    except Exception:
        return "—"
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# ---------------------------------------------------------------------------
# Documentación de secrets para la pestaña de ayuda
# ---------------------------------------------------------------------------
SECRETS_HELP = [
    ("BINANCE_API_KEY", "Clave API de Binance. Crea en Binance → Perfil → Gestión API. "
                        "Activa SOLO permiso de lectura (no necesitas retiros)."),
    ("BINANCE_API_SECRET", "Secreto correspondiente a la API key de Binance. Guárdalo "
                           "solo en secrets.toml, nunca en el código."),
    ("BTC_PAYOUT_ADDRESS", "Dirección Bitcoin donde recibes el minado. Recomendado: la "
                           "dirección de depósito BTC de tu Binance (pestaña Binance)."),
    ("POOL_URL", "URL stratum del pool. Ej: stratum+tcp://public-pool.io:21496"),
    ("POOL_USER", "Usuario del pool. Si lo dejas vacío se usa BTC_PAYOUT_ADDRESS."),
    ("POOL_PASSWORD", "Contraseña del pool. En pools públicos casi siempre es 'x'."),
    ("WORKER_NAME", "Nombre del worker que aparecerá en el pool. Ej: cpu01"),
    ("MINER_MODE", "Modo de arranque: python (minero nativo), bench (solo benchmark "
                   "local), demo (simulación), external (binario tipo XMRig)."),
    ("EXTERNAL_MINER_PATH", "Ruta completa del binario externo. Ej: /usr/bin/xmrig o "
                            "C:\\miners\\xmrig.exe"),
    ("EXTERNAL_MINER_ARGS", "Argumentos extra opcionales para el binario externo."),
    ("CPU_THREADS", "Hilos de CPU que usará el minero Python. Empieza con 1-2."),
    ("AUTO_REFRESH_SECONDS", "Intervalo de refresco del dashboard en vivo (mín. 2s)."),
    ("F2POOL_ACCOUNT", "Opcional: tu cuenta F2Pool para consultar estadísticas vía API."),
    ("NICEHASH_API_KEY", "Opcional: API key NiceHash (api.nicehash.com → API Management)."),
    ("NICEHASH_API_SECRET", "Opcional: secreto API NiceHash."),
    ("NICEHASH_ORG_ID", "Opcional: Organization ID de NiceHash."),
    # v2 — intervención agresiva
    ("TELEGRAM_BOT_TOKEN", "Token del bot de Telegram (créalo con @BotFather "
                           "/newbot). Habilita alertas instantáneas y "
                           "control remoto (/pausar /reanudar /apagar)."),
    ("TELEGRAM_CHAT_ID", "Tu chat_id de Telegram. Envía /start a tu bot y "
                         "usa el botón '¿Cuál es mi chat_id?' del dashboard."),
    ("WALLET_XMR", "Wallet Monero para MoneroOcean/SupportXMR (cobro en "
                   "XMR). DÉJALA VACÍA si no quieres wallet Monero: el "
                   "motor minará solo unMineable y cobra en BTC (ideal "
                   "para Binance, que NO acepta depósitos XMR)."),
    ("AGGRESSIVE_MODE", "true = daemon con motor agresivo multi-pool y "
                        "failover automático."),
    ("FAILOVER_MINUTES", "Minutos sin shares aceptados antes de saltar de "
                         "pool (default 12)."),
    ("ROTATE_MINUTES", "Rotación preventiva de pools cada N minutos "
                       "(0 = desactivada)."),
    ("CPU_TEMP_MAX", "Temperatura CPU (°C) que dispara la pausa térmica "
                     "automática (default 85)."),
    ("DAILY_SUMMARY_HOUR", "Hora local (0-23) del resumen diario por "
                           "Telegram (default 20)."),
    ("PAYOUT_ALERT_MIN_BTC", "Balance en el pool (BTC) que dispara el aviso "
                             "'payout en camino' por Telegram."),
    ("EVIDENCIA_CADA_HORAS", "Cada cuántas horas el daemon manda a Telegram "
                             "la PRUEBA DE GANANCIAS (saldo del pool, % del "
                             "umbral y BTC/día proyectado). 0 = apagado."),
    # v3.7 — LA HIDRA
    ("HIDRA_ACTIVA", "true = LA HIDRA (5 cabezas) vigila y optimiza el "
                     "minado: config óptima de xmrig, escudo Defender, "
                     "resurrección del binario, vigilancia de hashrate."),
    ("HIDRA_CAIDA_PCT", "% de caída del hashrate (respecto al récord) que "
                        "dispara la auto-reparación de la VIGÍA (default 35)."),
    ("HIDRA_DEFENDER", "true = el ESCUDO agrega solo las exclusiones de "
                       "Windows Defender para xmrig (carpeta + .exe + "
                       "proceso) y restaura lo cuarentenado."),
]
