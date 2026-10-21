# ⛏️ BTC Miner Studio

App de minería de Bitcoin con **Python + Streamlit**: minero stratum nativo,
métricas **reales en tiempo real** (hashrate, shares, dificultad, red global,
precio) y recepción automática en **tu Binance** a través de tu dirección de
depósito.

> ⚠️ **Honestidad ante todo**: minar BTC con CPU es *simbólico* (la red corre a
> ~700 EH/s; una CPU da ~0.1–2 MH/s). Esta app te da el **pipeline completo y
> funcional** — protocolo Stratum real, shares reales en pools reales, stats
> reales de red y conexión con Binance — para que la uses, la aprendas y la
> escales cuando quieras (modo binario externo con XMRig/cpuminer).

---

## 📁 Estructura (todos los archivos < 600 líneas)

| Archivo | Qué hace |
|---|---|
| `app.py` | Dashboard Streamlit: panel en vivo, red, Binance, historial, ayuda |
| `stratum_miner.py` | Minero Stratum V1 SHA-256 nativo (pool / bench / demo) |
| `miner_manager.py` | Gestor de binario externo (XMRig / cpuminer-opt) con parsing de logs |
| `binance_api.py` | Cliente Binance: dirección de depósito, balances, depósitos, precio |
| `pool_stats.py` | Red real (mempool.space), precio, APIs de F2Pool/NiceHash, rentabilidad |
| `ui_components.py` | KPIs y gráficos Plotly en tiempo real |
| `state_store.py` | Persistencia de métricas/eventos/shares (JSON) |
| `config.py` | Secrets, catálogo de pools y utilidades |
| `.streamlit/secrets.toml.example` | Plantilla de claves |

## 🚀 Puesta en marcha

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edita secrets.toml con tu dirección BTC y (opcional) tus claves Binance
streamlit run app.py
```

## 🔑 Variables de secrets (cópialas en `.streamlit/secrets.toml`)

| Variable | Para qué sirve |
|---|---|
| `BINANCE_API_KEY` | Clave API de Binance (permiso **solo lectura**) |
| `BINANCE_API_SECRET` | Secreto de la API key de Binance |
| `BTC_PAYOUT_ADDRESS` | Tu dirección BTC (puede ser la de depósito de Binance) |
| `POOL_URL` | URL stratum del pool (ej: `stratum+tcp://public-pool.io:21496`) |
| `POOL_USER` | Usuario del pool (si vacío usa `BTC_PAYOUT_ADDRESS`) |
| `POOL_PASSWORD` | Contraseña del pool (`x` en casi todos) |
| `WORKER_NAME` | Nombre del worker (ej: `cpu01`) |
| `MINER_MODE` | `python` \| `bench` \| `demo` \| `external` |
| `EXTERNAL_MINER_PATH` | Ruta del binario externo (ej: `/usr/bin/xmrig`) |
| `EXTERNAL_MINER_ARGS` | Argumentos extra del binario |
| `CPU_THREADS` | Hilos de CPU del minero Python (1–8) |
| `AUTO_REFRESH_SECONDS` | Segundos entre refrescos del panel (mín. 2) |
| `F2POOL_ACCOUNT` | Opcional: cuenta F2Pool para stats vía API |
| `NICEHASH_API_KEY` | Opcional: API key NiceHash |
| `NICEHASH_API_SECRET` | Opcional: secreto NiceHash |
| `NICEHASH_ORG_ID` | Opcional: Organization ID NiceHash |

## 🏦 Cómo llega el BTC a tu Binance (lo más seguro)

1. En la app, pestaña **Binance** → *Obtener mi dirección de depósito vía API*.
2. Pulsa *Usar como usuario del pool* (o ponla en `BTC_PAYOUT_ADDRESS`).
3. Inicia el minero: el pool paga **directo a tu dirección de Binance** → los
   sats aparecen en tu cuenta sin retiros por API.
4. La app te muestra el balance y el historial de depósitos en vivo.

> 🔒 Con este diseño tu API key **solo necesita permiso de lectura**. Nunca
> actives el permiso de retiro para esta app, y si puedes, restringe la key por
> IP en el panel de Binance.

## 🌊 Pools soportados (pago en BTC)

| Pool | URL stratum | Registro | Ideal para |
|---|---|---|---|
| **Public Pool** | `stratum+tcp://public-pool.io:21496` | No | CPU/mineros pequeños (lowdiff) |
| **Solo CKPool** | `stratum+tcp://stratum.ckpool.org:3333` | No | Lotería solo-mining (diff mín. 10k) |
| **69Pool** | `stratum+tcp://solo.69pool.org:3333` | No | Solo público (fee 0.69%) |
| **Kano.is** | `stratum+tcp://kano.is:3333` | Sí | PPLNS con vardiff bajo |
| **F2Pool** | `stratum+tcp://btc.f2pool.com:3333` | Sí | Pagos estables PPS+ |
| **ViaBTC** | `stratum+tcp://btc.viabtc.io:3333` | Sí | Pool grande con app propia |
| **NiceHash** | `stratum+tcp://sha256.apply.nicehash.com:3334` | Sí | Vender hash y recibir BTC |

## ⚙️ Modo binario externo (hash real)

1. Descarga el minero:
   - XMRig (CPU/GPU, RandomX→Monero y SHA-256): https://github.com/xmrig/xmrig/releases
   - cpuminer-opt (SHA-256 en CPU): https://github.com/JayDDee/cpuminer-opt
2. En secrets: `MINER_MODE = "external"` y `EXTERNAL_MINER_PATH = "/ruta/xmrig"`.
3. La app genera el `config.json` de XMRig automáticamente, lo lanza, lee su
   salida en vivo y muestra hashrate/shares en el dashboard.

## 🧪 Modos del motor

- **`python`** — Minero stratum escrito en Python puro: se conecta al pool,
  recibe trabajos, calcula double-SHA256 con N hilos y envía shares reales.
- **`bench`** — Mide el hashrate de tu CPU sin conectarse a nada.
- **`demo`** — Datos sintéticos para ver el dashboard funcionando.
- **`external`** — Controla XMRig/cpuminer como subproceso con parsing de logs.

## 📊 Métricas que verás (todas reales)

- Hashrate en vivo (H/s) con gráfico temporal
- Shares aceptados/rechazados y % de aceptación (gauge)
- Dificultad asignada por el pool (vardiff)
- **Hashrate y dificultad de la red BTC global** (mempool.space)
- Precio BTC/USDT en vivo (Binance → CoinGecko)
- Rentabilidad honesta: BTC/día, USD/día, probabilidad de bloque, años esperados
- Balance spot y depósitos de tu Binance
- Log de eventos y tabla de shares descargable en CSV

## 🐛 Solución de problemas

| Problema | Solución |
|---|---|
| `Pool rechazó la autorización` | Verifica que `POOL_USER` sea una dirección BTC **válida** |
| No veo shares en solo.ckpool | Su diff mínima es 10,000: usa **Public Pool** con CPU |
| `Faltan BINANCE_API_KEY` | Rellena secrets.toml o usa el modo simulado |
| Latencia/401 en Binance | Revisa claves y whitelist de IP del panel de Binance |
| El minero externo no arranca | Revisa `EXTERNAL_MINER_PATH` (ruta absoluta) |
| Demasiado CPU al minar | Baja `CPU_THREADS` a 1 o usa el modo bench |

## 🔗 Infraestructura y repos de referencia

- Stratum en Python (referencia): https://github.com/ricmoo/nightminer
- Public Pool (servidor open source): https://github.com/benjamin-wilson/public-pool
- ckpool (el servidor de solo.ckpool): https://github.com/ckolivas/ckpool
- XMRig: https://github.com/xmrig/xmrig
- cpuminer-opt: https://github.com/JayDDee/cpuminer-opt
- mempool.space API: https://mempool.space/docs/api/rest
- Binance API docs: https://developers.binance.com/docs
- NiceHash API docs: https://www.nicehash.com/docs

## ⚖️ Nota legal/energética

Minar consume electricidad. Calcula tu costo kWh antes de dejar la máquina
hasheando toda la noche. El software se entrega tal cual, con fines educativos
y de prueba de concepto.
