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
| `recolectar_pool.py` | **V3.2**: recoge balances de pools/cadena/Binance y los lleva a Binance |
| `sincronizar.py` | **V3.4**: sincronización automática local ↔ GitHub (pull/commit/push) |
| `probar_ganancias.py` | **V3.5**: PRUEBA DE GANANCIAS en vivo (pool + BTC/día + ANTES vs AHORA) |
| `hidra_minera.py` | **V3.7**: LA HIDRA — 5 cabezas (FUEGO/ESCUDO/MÉDICO/VIGÍA/CASA) |
| `defender_fix.ps1` | **V3.7**: escudo manual de Defender (exclusiones correctas + restaurar cuarentena) |
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

## 💸 PRUEBA DE GANANCIAS en Telegram (nuevo en v3.5)

"¿Pásame el pool a Binance y pruébame cuánto más BTC puedo ganar ahora?"
— Esto es lo que hace **`probar_ganancias.py`** con datos 100% reales:

- **Tu hashrate medido por tu propio bot** (metrics_daemon.json; si nunca
  ha minado, estima por tus núcleos y te dice que corras el bot primero).
- **Saldo REAL del pool unMineable** (API v4) + % del umbral de pago
  (0.00075 BTC) + **días estimados para el payout a tu Binance**.
- **Matemática de la red Monero en vivo**: dificultad (Blockchair) →
  hashrate de red, precio BTC (Binance) y XMR (Kraken) → BTC/día exactos.
- **3 escenarios**: HOY · TODOS LOS NÚCLEOS · +HUGE PAGES/MSR (×1.30).
- **La prueba honesta ANTES vs AHORA**: antes tu XMR iba a una wallet que
  no podías abrir (BTC recibido: 0). Ahora en modo SOLO-BTC el 100% de lo
  minado se acredita en BTC y vuela a tu Binance al cruzar el umbral.

**Cuándo la ves en Telegram:**
1. **Al arrancar el bot** (daemon) — mensaje inmediato con tu prueba.
2. **Cuando quieras**: escribe `/ganancias` a tu bot.
3. **Automático cada `EVIDENCIA_CADA_HORAS`** (default 6 h; 0 = apagado).

**Manual (sin daemon):**
```bash
python probar_ganancias.py            # reporte completo + Telegram
python probar_ganancias.py --tg-solo  # solo el resumen al celular
python probar_ganancias.py --hashrate 1500   # fijar H/s a mano
```

Cada prueba deja copia en `data/prueba_ganancias_*.json` para que
comparemos tu progreso semana a semana.

**▶️ CORRER todo con un doble clic:** `CORRER_BOT.bat` = sincroniza con
GitHub → verifica dependencias → arranca el daemon minero → abre el
dashboard. Y `DETENER_TODO.bat` para parar todo (el saldo del pool NO se
pierde: el pool paga al cruzar el umbral).

## 🚨 v3.8 DESBLOQUEO — pool zombi detectado y solventado (oct-2026)

**Qué pasó el 23-24/oct/2026**: `rx.unmineable.com` (puertos 3333 y 443)
quedó **ZOMBI**: aceptaba conexiones TCP pero NO respondía al protocolo
stratum — xmrig conectaba, nunca recibía un job y el hashrate quedaba en
0. El motor anterior elegía pool por latencia TCP (un zombi parece
"rápido") y, con un solo objetivo (modo SOLO-BTC), el failover no podía
rotar → **hashrate 0 para siempre**. Verificado en vivo con sondeo
stratum: MoneroOcean y SupportXMR estaban vivos mientras unMineable no
hablaba.

**Qué hace diferente la v3.8**:

| Cambio | Efecto |
|---|---|
| **Sonda stratum REAL** (`pools_salud.py`) | Handshake `mining.subscribe` de verdad: si el pool no responde se marca ZOMBI (20 min de cooldown persistido en `data/pool_salud.json`) |
| Arranque solo entre pools VIVOS | El motor sondea TODOS los objetivos en paralelo y lanza el más rápido que hable stratum de verdad |
| Nuevo objetivo `unmineable-ssl` | Mismo pool por TLS `stratum+ssl://rx.unmineable.com:443` (si el :3333 está caído o bloqueado por ISP/firewall, el :443 suele pasar). Con SOLO-BTC ahora hay 2 objetivos y el failover vuelve a rotar |
| `saltar_a_pool_viva()` | Si el pool actual se pone zombi EN MARCHA (hashrate 0 >5 min con motor vivo), salta al primero que responda |
| VIGÍA anti-hashrate-cero | 3 rondas (6 min) con motor vivo y 0 H/s → reparación + salto a pool vivo + aviso Telegram (antes la VIGÍA era muda ante el 0) |
| `secrets.toml` se lee directo (tomllib) | El daemon ya no depende de que streamlit importe bien para ver tus claves |
| **DIAGNOSTICO.bat / diagnostico.py** | Un doble clic: examina TODO (daemon, secrets, Defender, xmrig, pools con sondeo real, hidra), REPARA lo reparable (restaura xmrig, exclusiones, limpia pausas pegadas) y ARRANCA el daemon si está caído. Evidencia en `data/diagnostico_*.json` |

**Si un día vuelve el hashrate 0**: doble clic en **DIAGNOSTICO.bat** →
te dice en español qué pasó y casi siempre lo arregla solo. Si unMineable
está caído, el bot re-sondea cada ronda y arranca solo en cuanto reviva
(mientras tanto puedes pegar una `WALLET_XMR` en secrets para minar en
MoneroOcean/SupportXMR, que pagan XMR).

## 💰 v3.9 UTILIDADES — 7 pools y payout honesto (oct-2026)

Mientras unMineable sigue inestable (zombi intermitente), la v3.9 le da al
motor **salidas reales que pagan en BTC sin wallet Monero y sin registro**:

| # | Pool | Pago | Nota |
|---|---|---|---|
| 1-2 | unMineable :3333 / SSL :443 | **BTC** | Tu canal principal; si revive se usa solo (prioridad) |
| 3-4 | **ZergPool** `rx.mine.zergpool.com:5354` (+EU) | **BTC** | Familia Yiimp: usuario = tu dirección BTC, password `c=BTC,ID=worker`; sin registro, pago diario, umbral ~0.0005-0.001 BTC |
| 5 | MoneroOcean | XMR | Requiere WALLET_XMR |
| 6 | **Kryptex** `xmr.kryptex.network:7029` | XMR | Nuevo respaldo (formato `wallet/worker`, umbral bajo 0.01 XMR) |
| 7 | SupportXMR | XMR | Requiere WALLET_XMR |

El motor elige **solo pools VIVOS** (sondeo stratum real) y dentro de los
vivos prioriza el orden del catálogo (BTC primero) y luego la latencia.
Si unMineable está zombi, ahora en modo SOLO-BTC hay **2 canales BTC más**
(ZergPool TCP/EU) → el hashrate ya no se queda en 0 por falta de destino.

**Payout honesto**: la estimación "payout en X días" es
`(umbral − acumulado) ÷ BTC/día medido AHORA`. Si tu hashrate medido está
en el suelo (pool zombi, muestra de arranque), el número se dispara a
"años" — la v3.9 lo marca **NO FIABLE** en vez de asustar, y muestra la
sección **[2b] TU REGLA: USD 10/DÍA** con los H/s reales que necesitas y
los caminos para lograrlo (HIDRA al máximo, más PCs, hardware mayor).
ZergPool también aparece en `probar_ganancias` y `recolectar_pool`.


## 🚀 v4.1 — SONDEO EN VIVO + TUNING RANDOMX (27-10-2026, noche)

**Sondeo real de pools a las 20:47 UTC** (handshake stratum completo, no
solo ping — así ya no engaña un pool que acepta TCP y no responde):

| Estado | Pool | Detalle |
|---|---|---|
| ✅ VIVO | MoneroOcean `:10128` | 79 ms — **objetivo #1** (auto-algoritmo = max profit) |
| ✅ VIVO | SupportXMR `:3333` | 81 ms — respaldo |
| ✅ VIVO | xmrpool.eu `:9999` | 472 ms — respaldo |
| 💀 ZOMBI | unMineable `:3333/:443` | TCP sí, stratum mudo; se re-sondea solo |
| 💀 MUERTO | Kryptex `:7029` | 0 bytes |
| 💀 SIN DNS | ZergPool | el dominio ya no resuelve |
| 💀 SIN DNS | NiceHash | además exige cuenta propia → no automatizable |

**Tuning de hashrate (FUEGO v4.1)**: `randomx.mode` ahora es **AUTO** en vez
de `fast` fijo. El modo fast exige 2 MB de caché L3 **por hilo**; forzarlo
en CPUs con poca L3 BAJABA el hashrate sin que se note. Con `auto`, xmrig
elige fast o light según la caché REAL de tu CPU → siempre el óptimo
(docs: xmrig.com/docs/miner/config/randomx). Lo demás ya estaba a tope:
huge-pages + huge-pages-jit, memory-pool, prioridad, MSR (rdmsr/wrmsr),
scratchpad prefetch, NUMA.

**Cómo cobras el XMR de los pools vivos** (recordatorio honesto: Binance
declasó XMR en 2024 — no existe dirección de depósito XMR en Binance):
1. El pool te paga a tu `WALLET_XMR` (si no la pusiste, el bot genera una
   offline y te avisa por Telegram — RESPALDA `data/wallet_emergencia.json`).
2. Cambias XMR→BTC donde aún cotiza (Kraken, por ejemplo) o con un swap.
3. El BTC entra a tu Binance como siempre.
Cuando unMineable reviva, el canal BTC-directo se reactiva solo (está
último en el catálogo a la espera) y ese paso 2 desaparece.

**Extra v4.1.1 — último 1% de hashrate**: `donate-level` 0 (el 1% que xmrig
donaba al autor ahora es TUYO) y `1gb-pages` activado. Para que las 1GB
pages funcionen en Windows: clic derecho en `paginas_1gb.ps1` → "Ejecutar
con PowerShell" (concede el privilegio "Lock pages in memory") y reinicia
el PC una vez. Si no lo haces, no pasa nada: xmrig cae automáticamente a
las 2MB huge pages y mina igual.

## 🔗 v4.2 — PUENTE DAEMON→DASHBOARD (bug "hashrate 0 en pantalla" cazado EN VIVO)

**Cazado en vivo el 27-10-2026 con el bot minando de verdad**: el daemon
marcaba **1058.9 H/s reales** (API de xmrig :4068 → `metrics_daemon.json`)
mientras el panel en vivo mostraba **0** — porque el dashboard leía
`metrics.json` (modo python), un archivo que el daemon **nunca escribe**.
Dos procesos, dos archivos, cero conexión: tú veías ceros aunque la CPU
estuviera minando.

**La regulación (v4.2)**: nuevo puente en `state_store.py`
(`leer_daemon_metrics` + `daemon_history_df`) — el panel en vivo detecta
la métrica FRESCA del daemon (<3 min) y la muestra como fuente principal
con el sello "⚡ Fuente de datos: DAEMON 24/7"; los gráficos pasan a la
historia real del bot. Si el daemon está parado, el panel vuelve
automáticamente a las métricas del minero interno del dashboard.

**Patrón de bots públicos verificado**: así lo hacen los dashboards serios
(p. ej. xmrig-api de hreikin y los lanzadores de MoneroOcean) — poll del
API HTTP de xmrig `:4068/2/summary` (ya lo hacemos desde v3.9) + exponer
esas métricas al frontend desde UNA sola fuente. Nuestro hueco era el
puente hacia el panel; ya está cerrado.

### v4.2.1 — "¿pulo INICIAR si ya corrí CORRER_BOT.bat?" → NO

Doble arranque detectado como causa real de hashrate a la mitad: el
`CORRER_BOT.bat` ya arranca el **DAEMON 24/7** (xmrig en su propia
ventana). Si además pulsas **▶️ INICIAR** en el menú lateral del panel,
lanzas un **SEGUNDO minero** dentro del dashboard: los dos procesos
pelean los mismos hilos de CPU y el hashrate de cada uno cae ~50%
(tú lo ves como "no reporta nada").

**Regla de oro**: `CORRER_BOT.bat` = única fuente. Abre el panel solo
para **VER**, no para iniciar. El botón ▶️ INICIAR es únicamente para
minar SIN el bat (modo panel).

Arreglo v4.2.1 (el panel ahora se defiende solo):
1. El semáforo **Pool/Minero** del menú lateral se pone 🟢 si el daemon
   está vivo (antes mostraba 🔴 aunque estuvieras minando — eso empujaba
   a pulsar INICIAR).
2. Aviso visible: "⚡ Bot YA corriendo como DAEMON 24/7. NO pulses INICIAR".
3. El botón ▶️ INICIAR **se desactiva solo** mientras el daemon reporte
   métricas frescas (<3 min), y `start_miner()` re-verifica por si acaso
   (queda registrado en el log del panel, nunca lanza el doble minado).
4. `CORRER_BOT.bat` imprime la regla al terminar.

## 🐲 LA HIDRA — 5 cabezas de agresividad (nuevo en v3.7)

La hidra es el sistema que **recupera la agresividad perdida** y blinda el
minado 24/7. Despierta sola al arrancar el daemon (CORRER_BOT.bat) y sus
5 cabezas hacen esto en paralelo:

| Cabeza | Qué hace |
|---|---|
| 🔥 **FUEGO** | Reconfigura xmrig a MÁXIMO: hilos óptimos según tu CPU, huge pages + huge-pages-jit (boost Ryzen), memory-pool persistente, prioridad de hilos y `randomx mode auto` (v4.1: el óptimo real según la caché L3 de TU CPU — docs xmrig.com/docs/miner/config/cpu) |
| 🛡 **ESCUDO** | Agrega en Windows Defender las exclusiones **CORRECTAS** (docs Microsoft Add-MpPreference): carpeta `bin\` + ruta EXACTA del `xmrig.exe` + proceso `xmrig.exe`. La excepción de carpeta sola NO evita la cuarentena — por eso xmrig “desaparecía” aunque la tuvieras |
| ⚕ **MÉDICO** | Resucita xmrig.exe: si Defender lo borró lo **restaura de la cuarentena** (`MpCmdRun -Restore -All`) y si ya no hay nada lo **re-descarga solo** (fork MoneroOcean → oficial) |
| 👁 **VIGÍA** | Vigila el hashrate contra tu RÉCORD histórico (`data/hidra_state.json`); si cae más de `HIDRA_CAIDA_PCT` (35%) varias rondas seguidas → diagnostica (¿Defender? ¿binario borrado?), repara y relanza con la config óptima. Avisa por Telegram |
| 🏠 **CASA** | Memoria de la hidra: récord de hashrate, reparaciones y estado — visible en el dashboard (sección 1.5) y con `/hidra` en Telegram |

**Por qué tu proyección se cayó a 1/4** (y cómo se recupera): el hashrate
“HOY” se mide del bot real. Sin admin (MSR no aplicado) + xmrig bloqueado
por Defender → el medidor caía. Con la hidra: admin (MSR ~×1.5 en Ryzen) +
todos los núcleos + huge pages → la prueba de ganancias ahora muestra el
escenario **“HIDRA ACTIVA”** con el potencial REAL de tu CPU.

**Si tu antivirus NO es Defender** (Avast/Avira/McAfee/Norton…): el ESCUDO
solo controla Defender. Agrega la exclusión de la carpeta `bin\xmrig-mo`
en el panel de ESE antivirus, o ejecuta `defender_fix.ps1`
(clic derecho → Ejecutar con PowerShell) que además restaura lo
cuarentenado.

## 🐛 Solución de problemas

| Problema | Solución |
|---|---|
| `Pool rechazó la autorización` | Verifica que `POOL_USER` sea una dirección BTC **válida** |
| No veo shares en solo.ckpool | Su diff mínima es 10,000: usa **Public Pool** con CPU |
| `Faltan BINANCE_API_KEY` | Rellena secrets.toml o usa el modo simulado |
| Latencia/401 en Binance | Revisa claves y whitelist de IP del panel de Binance |
| El minero externo no arranca | Revisa `EXTERNAL_MINER_PATH` (ruta absoluta) |
| Demasiado CPU al minar | Baja `CPU_THREADS` a 1 o usa el modo bench |
| `msr FAILED TO APPLY MSR MOD` (v3.6) | El bot mina a MENOS DE LA MITAD: cierra con `DETENER_TODO.bat` y abre `CORRER_BOT.bat` — pide ADMINISTRADOR solo (acepta la ventanita UAC). Si reaparece: exclusión en Windows Defender para la carpeta `bin\xmrig-mo`. En Ryzen esto casi DUPLICA el hashrate |
| `huge pages` incompletas | Mismo remedio: administrador. Si sigue, reinicia Windows una vez (libera memoria fragmentada) |
| Aviso "Hashrate limitado" en Telegram | El daemon arrancó sin administrador. Ciérralo y reabre con `CORRER_BOT.bat` (la auto-elevación de v3.6 lo evita) |
| **xmrig.exe no ejecuta / desaparece aunque excluí la carpeta** (v3.7) | Defender cuarentena el .exe al EJECUTARLO aunque la carpeta esté excluida: faltan la exclusión del proceso y del .exe exacto. La HIDRA las agrega sola al arrancar (ESCUDO) y lo restaura (MÉDICO). Manual: `defender_fix.ps1` como admin |
| **Hashrate 0 de repente, el bot “no hace nada”** (v3.8) | Doble clic en **DIAGNOSTICO.bat**: te dice qué pasó (daemon caído, pool ZOMBI, xmrig borrado, pausa pegada…) y lo arregla solo. Causa típica: unMineable zombi — el motor v3.8 lo detecta, lo salta y mina en el pool vivo más rápido |

## 🔗 Infraestructura y repos de referencia

- Stratum en Python (referencia): https://github.com/ricmoo/nightminer
- Public Pool (servidor open source): https://github.com/benjamin-wilson/public-pool
- ckpool (el servidor de solo.ckpool): https://github.com/ckolivas/ckpool
- XMRig: https://github.com/xmrig/xmrig
- Fork XMRig-MO (auto-algoritmos): https://github.com/MoneroOcean/xmrig_setup
- Config CPU xmrig (huge pages/MSR/memory-pool): https://xmrig.com/docs/miner/config/cpu
- Defender Add-MpPreference (exclusiones): https://learn.microsoft.com/en-us/powershell/module/defender/add-mppreference
- cpuminer-opt: https://github.com/JayDDee/cpuminer-opt
- mempool.space API: https://mempool.space/docs/api/rest
- Binance API docs: https://developers.binance.com/docs
- NiceHash API docs: https://www.nicehash.com/docs

## ⚖️ Nota legal/energética

Minar consume electricidad. Calcula tu costo kWh antes de dejar la máquina
hasheando toda la noche. El software se entrega tal cual, con fines educativos
y de prueba de concepto.
