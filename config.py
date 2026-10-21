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
"""
import os

# ---------------------------------------------------------------------------
# Directorios base
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
METRICS_FILE = os.path.join(DATA_DIR, "metrics.json")

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
]
