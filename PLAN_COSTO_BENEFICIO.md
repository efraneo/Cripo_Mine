# PLAN DE OPCIONES ORDENADAS POR COSTO/BENEFICIO — Cripo_Mine v4.4

Fecha: 27 de octubre de 2026 · Moneda de cuenta: dólares (dls)
Meta original: utilidades >= 10 dls/día
Datos del día: XMR ~ $600 (rango anual $282–$795) · red Monero 7.16 GH/s · emisión 432 XMR/día
Piloto A/B hidra: ejecutado (scripts/pilot) — veredicto al final.

---

## 1. RESUMEN EJECUTIVO (veredicto en 60 segundos)

1) **Lo mejor del plan YA es gratis y YA está en tus manos.** El arreglo del "5 años" (v4.3.2), el DESVELO (24/7), el tuning de hashrate (v4.1.1) y la decisión de la hidra no cuestan un peso: solo faltan doble clics.
2) **Tu variable decisiva es el HASHRATE REAL, y hay que medirlo HOY.** Los "33" que viste son H/s; una laptop normal en RandomX hace 500–8,000 H/s. Si tu máquina da 33 H/s cuando debería dar 1,000+, hay un arreglo gratuito con efecto de 30x–240x. Ninguna otra opción del plan se le acerca en beneficio/costo.
3) **La hidra SE QUEDA.** El piloto A/B midió config FUEGO de la hidra vs xmrig base contra el mismo pool: idénticas. Quitarla te dejaría sin MÉDICO, VIGÍA, ESCUDO y sin el MSR que en un Ryzen suma hasta x1.5. Tu sospecha nació del número falso de 5 años, ya corregido.
4) **La verdad incómoda:** con 1 laptop, minar Monero a precio de hoy paga centavos al día y, si cuentas la electricidad, puede dejar PÉRDIDA. La meta de 10 dls/día por minería de CPU necesita ~276 kH/s (equipo de servidores). Este plan te dice exactamente dónde está tu línea de decisión (sección 5) y qué hacer en cada rama.

---

## 2. LOS NÚMEROS DE HOY (base de todo el plan)

Cadena del dinero, sin adornos:
- Tus **shares OK (102)** son boletos de trabajo aceptado: miden SALUD del motor, no dinero.
- El pool te paga por **hashrate sostenido × tiempo** (sistema PPLNS): tu porción de los 432 XMR/día que emite toda la red.
- El saldo acumulado cruza el **umbral de pago de MoneroOcean = 0.003 XMR (~$1.80)** y el pool te envía el XMR a tu wallet.
- Después cambias XMR → BTC en un exchange que aún cotice XMR (Kraken) y de ahí a tu Binance.

Fórmula usada (igual que probar_ganancias.py):
- XMR/día = 0.6 x 720 x (tu H/s ÷ 7,160,000,000)
- Dólares/día = XMR/día x precio XMR ($600 hoy)

**Tabla maestra: qué paga cada nivel de hashrate (XMR $600, red 7.16 GH/s)**

| Tu hashrate | Ejemplo de máquina | XMR/día | Dólares/día | Días hasta el pago MO (0.003 XMR) |
|---|---|---|---|---|
| 33 H/s | tu laptop hoy (sospechoso de estar roto) | 0.000002 | $0.001 | ~4.1 años |
| 500 H/s | laptop antigua / 1 núcleo | 0.00003 | $0.018 | ~100 días |
| 1,000 H/s (1 kH/s) | laptop media | 0.000060 | $0.036 | ~50 días |
| 5,000 H/s (5 kH/s) | laptop moderna Ryzen i5 | 0.00030 | $0.18 | ~10 días |
| 10,000 H/s (10 kH/s) | laptop potente / desktop mediano | 0.00060 | $0.36 | ~5 días |
| 23,000 H/s (23 kH/s) | desktop Ryzen 9 7950X (~175 W) | 0.00139 | $0.83 | ~2.2 días |
| 100,000 H/s (100 kH/s) | servidor usado EPYC (~400 W) | 0.00603 | $3.62 | ~0.5 días |
| 276,000 H/s (276 kH/s) | granja de servidores | 0.01664 | $10.00 | ~cada día |

Lectura honesta: cada 1 kH/s extra suma ~$0.036/día. Nota: MoneroOcean conmuta automáticamente al algoritmo RandomX más rentable del momento y paga en XMR, lo que suele dar un extra de ~5–30% según la CPU — no lo incluyo en la tabla por honestidad.

---

## 3. POR QUÉ VEÍAS "5 AÑOS" (y qué era verdad)

Hubo DOS problemas encadenados:
1) **Bug de rutas mezcladas (corregido en v4.3.2):** el reporte [4] dividía el BTC que faltaba para el umbral de unMineable (una ruta MUERTA desde v4.0, congelada en 0.00075 BTC) entre las ganancias de la ruta XMR de HOY. Mezcló un futuro que no existe con tu ingreso real → ETA absurdo. El nuevo [4b] "RUTA ACTIVA XMR → MoneroOcean" muestra el ETA correcto de la ruta que sí mina.
2) **Hashrate demasiado bajo:** aun con el bug corregido, si tu máquina entrega ~33 H/s el ETA real a 0.003 XMR sigue siendo ~4 años (ver tabla). Por eso el plan pone "medir y arreglar el hashrate" como prioridad número 1: NO es un problema de configuración del bot, es un número de motor 30x–240x por debajo de lo esperable en una laptop.

Causas típicas de un 33 H/s en una laptop que debería dar más (todas cubiertas por la hidra / DIAGNOSTICO.bat): xmrig con 1 solo hilo, RAM insuficiente para RandomX, Windows Defender escaneando el minero (falta ESCUDO), temperatura que estrangula la CPU (throttle), o máquina muy vieja. El diagnóstico lo dice en 30 segundos.

---

## 4. EL PLAN: 11 OPCIONES ORDENADAS POR COSTO/BENEFICIO

Ordenadas de mayor a menor "beneficio por peso/esfuerzo invertido". Costo 0 = solo tiempo.

| # | Opción | Costo | Beneficio esperado | Riesgo | Veredicto |
|---|---|---|---|---|---|
| 1 | Arreglo del "5 años" (v4.3.2, ya en tu ZIP) | $0, 0 min | Decisiones con números reales | Ninguno | HECHO — recoger |
| 2 | Mantener la hidra (piloto A/B) | $0 | Hashrate estable + MSR x1.5 + autocuración | Ninguno | DECIDIDO: SE QUEDA |
| 3 | DESVELO.bat (24/7 sin dormir) | $0, 1 doble clic | Hasta x3 shares/día si antes dormías | Luz extra (ver #7) | HACER HOY |
| 4 | Medir hashrate real (DIAGNOSTICO.bat + panel) | $0, 30 s | Si está roto (33 vs 1000+): x30–x240 gratis | Ninguno | HACER HOY — máxima prioridad |
| 5 | PAGINAS_1GB.ps1 + 1 reinicio | $0, 2 min | +1–3% (hasta +10–20% si faltaban huge pages) | Ninguno | HACER ESTA SEMANA |
| 6 | Cobrar saldos (MO auto-paga a 0.003 XMR) | $0 | ~$1.80 por ciclo; saldos de rutas en pausa se conservan | Ninguno | PASIVO — dejar que corra |
| 7 | Regla del NETO (CALCULO_NETO.bat NUEVO) | $0, 3 min | Evita minar a pérdida; decide todo lo demás | Ninguno | HACER HOY |
| 8 | Bajar umbral MO en moneroocean.org Settings | $0 | Cobros más frecuentes | Ninguno | OPCIONAL |
| 9 | Sumar PCs/laptops ociosos a la hidra | Luz de cada máquina | Lineal: +$0.036/día por cada kH/s | Luz | SOLO si su neto > 0 |
| 10 | Comprar hardware XMR (7950X / EPYC) | $700–$2,500+ | 7950X ≈ $0.83 bruto/día; EPYC x2 ≈ $2.2–2.5 | Payback de años | NO RECOMENDADO |
| 11 | Reasignar la meta $10/día fuera de la minería | $0 | La meta se vuelve alcanzable de inmediato | Ninguno | RECOMENDADO EN PARALELO |

### Detalle de las opciones que requieren acción

**#3 DESVELO.bat — el mejor ROI del plan.** Cerrar la tapa congelaba el daemon y mataba la conexión al pool: perdiste los 33 H/s de esa manera. DESVELO.bat deja standby/hibernación en 0 con cargador, LIDACTION en 0 (cerrar tapa = no hacer nada) y monitor en 15 min. Si antes minabas 8 h/día, ahora minas 24 h: hasta x3 de shares por el mismo hardware. Costo real: electricidad nocturna — la regla del neto (#7) te dice si conviene.

**#4 Medir el hashrate real — la jugada más grande del plan.** El flujo: doble clic CORRER_BOT.bat → esperar 2–3 min → el panel debe mostrar "⚡ Fuente: DAEMON 24/7" y un hashrate. Anota el número y pásalo por CALCULO_NETO.bat. Si sale < 300 H/s en una laptop no ancient: doble clic DIAGNOSTICO.bat (revisa Defender, hilos, RAM, temperatura y repara lo reparable). Saltar de 33 H/s a 1,000+ H/s multiplica por 30 tus centavos actuales — ninguna inversión del plan llega ni de cerca a ese retorno por cero dólares.

**#5 PAGINAS_1GB.ps1 — el último 1–3%.** Concede "Lock pages in memory" a Administradores para que RandomX use páginas de 1 GB (+ reinicio único). Con fallback automático a 2 MB si algo falta. Ya está en el ZIP desde v4.1.1.

**#7 La regla del NETO — la decisión madre.**
NETO/día = (tu H/s ÷ 7.16e9) x 432 x $600 − (W x 24 ÷ 1000) x tarifa_kWh
- NETO > 0: mina 24/7 con DESVELO y (si quieres) suma máquinas (#9).
- NETO ≈ 0: mina solo mientras el PC esté encendido por otras razones; el daemon ya respeta el apagado.
- NETO < 0: apaga el minado en esa máquina (DETENER_TODO.bat); NO hay pérdida acumulada — el saldo ya minado sigue en el pool esperándote.

**#9 Sumar máquinas.** Es el único escalado "casi gratis": instalar el ZIP en cada PC ocioso con la MISMA wallet de MoneroOcean (los saldos se suman en un solo lugar). Regla dura: cada máquina debe pasar la regla del neto por sí sola.

**#10 Hardware — la tabla de la verdad (XMR $600, luz $0.20/kWh).**

| Equipo | Costo aprox. | Hashrate | Bruto/día | Luz/día | NETO/día | Payback |
|---|---|---|---|---|---|---|
| Laptop actual (rota o vieja) | $0 | 0.03–1 kH/s | $0.001–0.04 | $0.19–0.22 | NEGATIVO | n/a |
| Desktop Ryzen 9 7950X | ~$700–900 | ~23 kH/s | $0.83 | $0.84 | ~$0.00 | n/a |
| Servidor 2x EPYC 7742 usado | ~$1,500–2,500 | ~55–70 kH/s | $2.2–2.5 | $1.9–2.2 | ~$0.3–0.6 | 8–15 años |
| Granja para $10/día (276 kH/s) | ~$10,000+ | 276 kH/s | $10.0 | ~$10 (940 W) | ~$0 salvo luz muy barata | n/a |

Con XMR a $600 y luz a $0.20/kWh, el hardware nuevo para RandomX apenas empata con su propia electricidad. Solo tiene sentido con luz barata (<$0.10) y equipo usado barato, y aun así el payback es de años. Si el precio de XMR vuelve a su máximo anual ($795), los brutos suben ~33% — sigue sin cambiar el veredicto para una laptop.

**#11 Reasignar la meta.** $10/día = $300/mes. Por minería-CPU doméstica: matemáticamente inviable. Por trabajo/gig/servicio: alcanzable sin capital. El rol sano del bot: colector pasivo de centavos + laboratorio de aprendizaje + sistema 24/7 que se cuida solo (eso ya lo lograste con v4.3/v4.4). El tiempo liberado es el verdadero activo.

---

## 5. LA REGLA DEL NETO EN DETALLE (tabla de decisión)

Luz 24 h, XMR $600. Valores en dls/día.

| Máquina | Hashrate | Luz a $0.10 | Luz a $0.20 | Luz a $0.30 |
|---|---|---|---|---|
| Laptop 45 W | 0.5 kH/s | $0.018−$0.108 = **−$0.09** | **−$0.20** | **−$0.31** |
| Laptop 60 W | 5 kH/s | $0.18−$0.144 = **+$0.04** | $0.18−$0.288 = **−$0.11** | **−$0.25** |
| Desktop 175 W | 23 kH/s | $0.83−$0.42 = **+$0.41** | $0.83−$0.84 = **~$0.00** | $0.83−$1.26 = **−$0.43** |
| EPYC x2 400 W | 60 kH/s | $2.17−$0.96 = **+$1.21** | $2.17−$1.92 = **+$0.25** | $2.17−$2.88 = **−$0.71** |

Conclusión: en laptop, la electricidad come el ingreso salvo tarifas muy bajas o luz ya pagada (PC encendido igualmente). Por eso la calculadora te da el veredicto con TU tarifa.

---

## 6. LA HIDRA: VEREDICTO DEL PILOTO (se queda)

Prueba A/B controlada (scripts/pilot/piloto_hidra.py, xmrig 6.26.0, mismo pool MoneroOcean, misma wallet, 2 hilos):
- Escenario A = config FUEGO real de la hidra (config_optima: 1gb-pages, huge-pages, donate 0, MSR).
- Escenario B = xmrig por defecto sin hidra.
- Resultado: A y B idénticas en el sandbox (84 y 48 muestras de API, mismas curvas). La config de la hidra NO frena a xmrig. Sus palancas fuertes (MSR Ryzen x1.5, huge-pages) solo actúan en Windows como admin — allá donde tú minas de verdad.

Además, quitar la hidra te costaría: MÉDICO (resucita xmrig si Defender lo borra), VIGÍA (anti-hasrate-0), ESCUDO (exclusiones correctas), auto-wallet, failover de pools vivos y la pestaña Hidra 2.0. Todo eso es gratis y ya funcionando. **Decisión: NO quitarla.** Tu desconfianza venía del 5 años falso — ya corregido.

---

## 7. HOJA DE RUTA

**HOY (15 min):**
1. Doble clic CORRER_BOT.bat (UAC) → espera 2–3 min → anota el hashrate del panel (con sello "⚡ DAEMON 24/7").
2. Doble clic CALCULO_NETO.bat → mete ese hashrate, los vatios de tu cargador y tu tarifa → lee el veredicto.
3. Si falta: doble clic DESVELO.bat (UAC) para el 24/7.

**ESTA SEMANA:**
4. Si el hashrate sale < 300 H/s: DIAGNOSTICO.bat y revisa hilos/RAM/Defensor/temperatura (el arreglo es gratis y puede ser x30).
5. Doble clic PAGINAS_1GB.ps1 + 1 reinicio (último 1–3%).

**ESTE MES:**
6. Deja que MoneroOcean cruce 0.003 XMR y verifica el primer pago en tu wallet.
7. Solo si el neto > 0: considera sumar otra máquina (#9). Si el neto < 0 en luz 24/7: mina solo horas ociosas o pausa con DETENER_TODO.bat (sin perder saldo).
8. Re-evalúa con el precio del día: el bruto escala 1:1 con el precio de XMR (la tabla usa $600; a $795 sube 33%).

**Criterio de salida honesto:** este plan no te ata a nada. Si el neto sale negativo y no hay máquina que lo arregle, el camino de los 10 dls/día es el #11 — y el bot queda como lo que ya es: un sistema 24/7 que mina centavos, se autocura y no te roba tiempo.
