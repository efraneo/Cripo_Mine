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

## 🚀 V2 — INTERVENCIÓN AGRESIVA (nuevo)

**El diagnóstico**: si minaste BTC directo (SHA-256) con CPU un día entero y
no salió nada, es matemática, no mala suerte: la red BTC corre a cientos de
EH/s y una CPU a ~0.5 MH/s (probabilidad de bloque ≈ 1 en billones). El
modo `python` queda como laboratorio/lotería educativa.

**La intervención** (pestaña **Motor agresivo** del dashboard, motor
`aggressive_engine.py` como daemon 24/7): la CPU pasa a minar **RandomX**
(donde sí es competitiva) y el pipeline rota entre 3 objetivos con FAILOVER
automático:

| # | Objetivo | Pool | Algoritmo | Pago |
|---|----------|------|-----------|------|
| 1 | unMineable | `rx.unmineable.com:3333` (alt SSL `:443`) | rx/0 | **BTC directo a tu dirección de Binance** |
| 2 | MoneroOcean | `gulf.moneroocean.stream:10128` | auto (13+ algos, fork XMRig-MO) | XMR a tu wallet |
| 3 | SupportXMR | `pool.supportxmr.com:3333` | rx/0 | XMR (respaldo veterano) |

- **Descarga automática de XMRig**: el daemon baja solo el binario
  precompilado (fork MoneroOcean v6.26.0-mo5 desde
  `github.com/MoneroOcean/xmrig_setup`; fallback: xmrig oficial 6.26.0
  estático). No instalas nada a mano.
- **Failover**: sin shares aceptados en `FAILOVER_MINUTES`, proceso muerto
  o pool sin respuesta → cambia de objetivo y registra el motivo.
- **Telegram** (`telegram_bot.py`): alertas de arranque/failover/depósitos
  y CONTROL REMOTO: `/estado` `/pausar` `/reanudar` `/cambiar` `/ganancias`.
- **Vigilante de pagos** (`payout_manager.py`): detecta depósitos BTC en tu
  Binance vía API y avisa al instante con su valor en USD; monitorea balance
  en unMineable y MoneroOcean y avisa "payout en camino" al cruzar el umbral.
- **Vigilante** (`vigilante.py`): pausa térmica automática (CPU_TEMP_MAX),
  alerta de caída de internet y resumen diario.
- **Pipeline a Binance**: el pool paga a tu dirección de depósito → el BTC
  aparece en tu cuenta sin que toques nada (tu API key de Binance sigue
  siendo SOLO de lectura).

⚠️ **Nota importante**: Binance eliminó XMR (2024-02-20): NUNCA uses XMR
como dirección de pago en pools que van a Binance. Por eso unMineable paga
en BTC. El XMR de MoneroOcean/SupportXMR va a tu wallet propia.

⚠️ **Antivirus (Windows)**: XMRig suele dar falso positivo. Excluye la
carpeta `bin/` en Windows Defender o descarga el binario manualmente desde
el repo oficial y pon la ruta en `EXTERNAL_MINER_PATH`.

Expectativa honesta: laptop moderna ≈ **USD 0.02–0.15/día** en RandomX.
No es una fortuna, pero es flujo REAL, continuo, y llega a Binance solo.

---

## 📁 Estructura (todos los archivos < 600 líneas)

| Archivo | Qué hace |
|---|---|
| `app.py` | Dashboard Streamlit: panel en vivo, motor agresivo, red, Binance, historial, ayuda |
| `aggressive_engine.py` | **V2**: motor multi-pool (unMineable/MoneroOcean/SupportXMR) + failover + descarga de XMRig |
| `run_miner.py` | **V2**: daemon headless 24/7 (mina aunque cierres el dashboard) |
| `telegram_bot.py` | **V2**: alertas Telegram + control remoto (/pausar /estado…) |
| `payout_manager.py` | **V2**: vigila depósitos en Binance y balances de pools, avisa por Telegram |
| `vigilante.py` | **V2**: pausa térmica, alertas de internet, resumen diario |
| `control.py` | **V2**: canal de control app ↔ daemon ↔ Telegram (control.json) |
| `panel_agresivo.py` | **V2**: pestaña del dashboard para el motor agresivo |
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
# edita secrets.toml: dirección BTC de Binance + Telegram + (opcional) wallet XMR
streamlit run app.py
# luego: pestaña "Motor agresivo" → INICIAR DAEMON (o: python run_miner.py)
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
| `TELEGRAM_BOT_TOKEN` | **V2**: token del bot (BotFather) para alertas y control |
| `TELEGRAM_CHAT_ID` | **V2**: tu chat_id (botón "¿Cuál es mi chat_id?" en el dashboard) |
| `WALLET_XMR` | **V2**: wallet Monero (objetivos MoneroOcean/SupportXMR) |
| `AGGRESSIVE_MODE` | **V2**: `true` = daemon con motor agresivo |
| `FAILOVER_MINUTES` | **V2**: min sin shares antes de cambiar de pool (12) |
| `ROTATE_MINUTES` | **V2**: rotación preventiva cada N min (0 = off) |
| `CPU_TEMP_MAX` | **V2**: pausa térmica automática (°C, default 85) |
| `DAILY_SUMMARY_HOUR` | **V2**: hora del resumen diario por Telegram (20) |
| `PAYOUT_ALERT_MIN_BTC` | **V2**: balance que dispara aviso de payout (0.0005) |

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

## 🧰 Recolección de caja y APAGADO TOTAL (nuevo en v3.2)

**Recolectar lo minado hacia Binance:**
```bash
python recolectar_pool.py            # reporte completo + envío a Telegram
python recolectar_pool.py --sin-tg   # solo consola
```
Consulta en paralelo: balance en unMineable (BTC), saldo on-chain de tu
dirección (mempool.space), XMR pendientes en MoneroOcean, y tu Binance
(dirección de depósito, saldo spot, últimos depósitos). Imprime un plan
paso a paso y guarda copia en `data/recolecta_*.json`.

**Apagar TODO (xmrig.exe + daemon + bot):**
| Método | Cómo |
|---|---|
| Windows (recomendado) | Doble clic en `DETENER_TODO.bat` |
| Telegram | Envía `/apagar` a tu bot (nuevo comando v3.2) |
| Consola | Ctrl+C en la ventana del daemon |

El saldo pendiente en cada pool **no se pierde** al apagar: queda asociado
a tu dirección y el pool lo paga solo cuando cruce su umbral
(unMineable: 0.00075 BTC, ajustable en unmineable.com → Addresses;
MoneroOcean: ~0.001 XMR). Recuerda: Binance no acepta depósitos de XMR
(delistado), ese saldo va a tu wallet Monero.

### ¿No puedes abrir una wallet Monero? (FAQ v3.3)

| Opción | ¿Sirve? |
|---|---|
| **Binance** para el XMR | ❌ NO acepta XMR (delistado 2024-02) |
| **Trust Wallet** | ❌ No soporta Monero (lo eliminó hace años) |
| **Dejar `WALLET_XMR` vacío** | ✅ RECOMENDADO: el motor mina solo unMineable y paga en BTC directo a tu dirección (Binance si es su dirección de depósito) |
| **Cake Wallet** — gratis, Windows/móvil, usa nodo remoto (no descarga la blockchain) | ✅ Si quieres cobrar XMR |
| **Feather Wallet** (escritorio, ligera) · **Exodus** (multimoneda) | ✅ Alternativas XMR gratuitas |

Con `WALLET_XMR` vacío el motor queda en **modo SOLO-BTC**: solo unMineable
(apaga el failover a los pools XMR pero todo lo demás sigue igual), el
arranque por Telegram lo anuncia, y `recolectar_pool.py` te sigue mostrando
el pipeline completo. El XMR ya pendiente en MoneroOcean no se pierde al
quitar `WALLET_XMR`: queda asociado a la dirección que usaste y lo
recuperas cuando instales una wallet y la vuelvas a poner en secrets.

## 🔄 Sincronización automática con GitHub (nuevo en v3.4)

Un doble clic en **`ACTUALIZAR_BOT.bat`** sincroniza tu carpeta local
(p. ej. `C:\software_phyton\Cripo_Mine`) con tu repo de GitHub
(`efraneo/Cripo_Mine`), y al actualizarse el repo **Streamlit Cloud
redespliega la app solo**. Nunca más descargas ni subidas manuales.

**Primera vez (setup guiado, 2 minutos):**
1. Instala Git si no lo tienes: `winget install --id Git.Git -e` (opciones
   por defecto — incluye el Git Credential Manager).
2. Copia `sincronizar.py`, `ACTUALIZAR_BOT.bat` y `.gitignore` a tu
   carpeta del bot y haz doble clic en `ACTUALIZAR_BOT.bat`.
3. Revisa el resumen de diferencias y confirma con `s`. La primera vez
   que sube, tu navegador se abre para autorizar GitHub (solo una vez).

**A partir de entonces:** doble clic = pull + commit + push automático.
Si no hay cambios, lo dice y no toca nada.

**Manual (equivalente en consola):**
```bash
python sincronizar.py auto     # pull + commit + push (recomendado)
python sincronizar.py estado   # ver qué cambió sin tocar nada
python sincronizar.py bajar    # solo descargar lo último del repo
python sincronizar.py subir    # solo subir tus cambios
```

**Automatización total (opcional):** sincroniza cada 30 min con el
Programador de tareas de Windows:
```bat
schtasks /Create /SC MINUTE /MO 30 /TN "CripoMine Sync" ^
  /TR "C:\software_phyton\Cripo_Mine\ACTUALIZAR_BOT.bat"
```

**Seguridad:** el `.gitignore` incluido excluye SIEMPRE
`.streamlit/secrets.toml` (tus claves), `data/`, `logs/`, `bin/`,
`__pycache__/` y `*.zip`. Tus secrets nunca se suben al repo.

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
