# ==============================================================================
# MOTOR_TRADING.PY - Escaneo, Ejecución (Conectando con los 4 Dioses)
# ==============================================================================
import time
from config import agregar_log, ACTIVOS_ANALIZAR
from analisis_tecnico import obtener_datos_cuantitativos, obtener_sesion_mercado
from binance_utils import (
    actualizar_saldo_spot, obtener_step_size, formatear_cantidad,
    obtener_consensus_top_traders, simular_compra_demo, simular_venta_demo
)
from motor_ia import consejo_4_dioses_especializados # ✅ NUEVA IMPORTACIÓN

# ─── Escanear y Evaluar Mercado ──────────────────────────────────────────────
def escanear_y_evaluar_mercado(ss, tp_pct):
    client = ss.get('client')
    if not client: return "NEUTRO", "Ninguno", {}

    agregar_log(ss, f"🔍 Escaneando {len(ACTIVOS_ANALIZAR)} activos...")
    sesion_nombre, sesion_pts = obtener_sesion_mercado()
    ss.sesion_mercado = sesion_nombre
    activo_top = obtener_consensus_top_traders(ss)

    candidatos, max_pts = [], 0
    for simbolo in ACTIVOS_ANALIZAR:
        datos = obtener_datos_cuantitativos(client, simbolo)
        if not datos: continue

        pts = 0
        # ✅ Puntuación por Patrones Japoneses
        if any("Alcista" in p or "Martillo" in p or "Soldados" in p or "Mañana" in p or "Pin Bar Alcista" in p for p in datos['patrones_japoneses']): 
            pts += 30
        if any("Bajista" in p or "Estrella Fugaz" in p or "Cuervos" in p for p in datos['patrones_japoneses']): 
            pts -= 20 # Penalización fuerte por patrones bajistas
            
        if datos['es_ballena']: pts += 20
        elif datos['vol_ratio'] > 1.5: pts += 10
        if "FUERTE" in datos['tendencia'] and "ALCISTA" in datos['tendencia']: pts += 20
        elif "ALCISTA" in datos['tendencia']: pts += 10
        if 30 < datos['rsi'] < 60: pts += 10
        if activo_top and activo_top in simbolo: pts += 10
        pts += sesion_pts

        if pts > max_pts: max_pts = pts
        if pts >= 40: candidatos.append({"symbol": simbolo, "puntaje": pts, "datos": datos})

    if not candidatos:
        ss.mejor_puntaje = max_pts
        ss.patron_actual = ("NEUTRO", f"⚪ Mercado frío. Mejor: {max_pts}pts")
        return "NEUTRO", "Ninguno", {}

    candidatos.sort(key=lambda x: x['puntaje'], reverse=True)
    mejor = candidatos[0]
    ss.mejor_puntaje = mejor['puntaje']
    patrones_str = ", ".join(mejor['datos']['patrones_japoneses'][:2])
    agregar_log(ss, f"🏆 Líder: {mejor['symbol']} ({mejor['puntaje']}pts) - {patrones_str}")

    # ✅ Si hay al menos 1 señal alcista básica, mandar a los 4 Dioses
    if mejor['puntaje'] >= 40:
        decision, veredicto = consejo_4_dioses_especializados(ss, mejor['symbol'], mejor['datos'], tp_pct)
    else:
        ss.patron_actual = ("NEUTRO", f"⏭️ {mejor['symbol']} sin señales")
        return "NEUTRO", "Ninguno", {}

    if decision == "COMPRA":
        ss.patron_actual = ("COMPRA", f"👑 Juez Z.ai: {veredicto}")
        ss.activo_seleccionado = mejor['symbol']
        return "COMPRA", mejor['symbol'], mejor['datos']

    ss.patron_actual = ("NEUTRO", f"👑 Juez Z.ai RECHAZÓ: {veredicto}")
    return "NEUTRO", "Ninguno", {}

# ─── Ejecutar Ciclo Mutante ──────────────────────────────────────────────────
def ejecutar_ciclo_mutante(ss, tp_pct, sl_pct, capital_ini, reinvertir):
    from binance.exceptions import BinanceAPIException
    client = ss.get('client')
    if not client: return
    es_demo = ss.get('es_demo', False)
    actualizar_saldo_spot(ss)

    if ss.comprado:
        sym = ss.activo_seleccionado
        precio = float(client.get_symbol_ticker(symbol=sym)['price'])
        if precio > ss.max_precio_alcanzado: ss.max_precio_alcanzado = precio

        valor_pos = ss.cantidad_comprada * precio
        ss.ganancia_flotante = valor_pos - ss.monto_invertido_operacion
        diff_pct = ((precio - ss.precio_compra) / ss.precio_compra) * 100

        if not ss.break_even_activado and diff_pct >= 0.2:
            ss.break_even_activado = True
            agregar_log(ss, "🛡️ Break-Even activado.")

        sl_din = sl_pct
        if ss.break_even_activado: sl_din = 0.0
        if diff_pct >= 0.4: sl_din = 0.2
        if diff_pct >= 0.6: sl_din = 0.4

        vender, motivo = False, ""
        if diff_pct >= tp_pct: vender, motivo = True, f"TAKE PROFIT ({diff_pct:.2f}%)"
        elif diff_pct <= sl_din: vender, motivo = True, f"STOP DINÁMICO ({sl_din:.2f}%)"
        else:
            datos_rap = obtener_datos_cuantitativos(client, sym)
            if datos_rap and any("Bajista" in p or "Cuervos" in p or "Tarde" in p for p in datos_rap.get('patrones_japoneses', [])):
                vender, motivo = True, "SEÑAL VELA JAPONESA BAJISTA"

        if vender:
            ss.accion_actual = f"💸 VENDIENDO: {motivo}"
            try:
                if es_demo:
                    monto_recibido = simular_venta_demo(ss, sym, ss.cantidad_comprada, precio)
                    fee = monto_recibido * 0.001
                    ganancia = monto_recibido - ss.monto_invertido_operacion - fee
                    ss.demo_usdt_virtual -= fee
                else:
                    step, prec = obtener_step_size(client, sym)
                    cant = formatear_cantidad(ss.cantidad_comprada, step)
                    if cant > 0: client.order_market_sell(symbol=sym, quantity=round(cant, prec))
                    fee = valor_pos * 0.001
                    ganancia = valor_pos - ss.monto_invertido_operacion - fee

                ss.ganancia_total_realizada += ganancia
                if reinvertir:
                    ss.capital_bot_actual = ss.demo_usdt_virtual if es_demo else (valor_pos - fee)
                    agregar_log(ss, f"💰 Compound: ${ss.capital_bot_actual:.4f}")

                ss.comprado = False; ss.precio_compra = 0.0
                ss.cantidad_comprada = 0.0; ss.monto_invertido_operacion = 0.0
                ss.max_precio_alcanzado = 0.0; ss.break_even_activado = False
                ss.flash_venta = True
                ss.accion_actual = f"💰 VENTA EXITOSA ({motivo})"
                agregar_log(ss, f"💰 VENTA. P&L: {ganancia:+.4f} USDT")
            except BinanceAPIException as e:
                ss.accion_actual = f"❌ ERROR VENTA: {e.message}"
        else:
            ss.accion_actual = f"📈 EN {sym}. Dif:{diff_pct:+.2f}% (SL:{sl_din}%)"
    else:
        if ss.saldo_usdt_libre < ss.capital_bot_actual:
            ss.accion_actual = "⚠️ FONDOS INSUFICIENTES"; return

        ss.ganancia_flotante = 0.0
        señal, simbolo, datos = escanear_y_evaluar_mercado(ss, tp_pct)

        if señal == "COMPRA" and simbolo != "Ninguno":
            ss.accion_actual = f"🎯 ¡DISPARO! Comprando {simbolo}..."
            monto = ss.capital_bot_actual if reinvertir else capital_ini
            step, prec = obtener_step_size(client, simbolo)
            precio = float(client.get_symbol_ticker(symbol=simbolo)['price'])
            cant = formatear_cantidad(float(monto / precio), step)
            if cant > 0:
                try:
                    if es_demo: orden = simular_compra_demo(ss, simbolo, cant, precio)
                    else: orden = client.order_market_buy(symbol=simbolo, quantity=round(cant, prec))

                    ss.comprado = True; ss.activo_seleccionado = simbolo
                    ss.precio_compra = precio; ss.cantidad_comprada = float(orden['executedQty'])
                    ss.monto_invertido_operacion = monto; ss.max_precio_alcanzado = precio
                    ss.break_even_activado = False
                    ss.accion_actual = f"✅ COMPRADO {simbolo}. Activando BE..."
                    agregar_log(ss, f"✅ COMPRA en {simbolo} @ {precio}. TP:+{tp_pct}%")
                except BinanceAPIException as e:
                    ss.accion_actual = f"❌ ERROR: {e.message}"
        else:
            ss.accion_actual = f"🔍 Escaneando... (Líder: {ss.mejor_puntaje}pts)"

def ejecutar_si_corresponde(ss, intervalo_seg, tp_pct, sl_pct, capital_ini, reinvertir):
    ahora = time.time()
    if (ahora - ss.ultimo_ciclo_ts) >= intervalo_seg:
        ss.ultimo_ciclo_ts = ahora
        ejecutar_ciclo_mutante(ss, tp_pct, sl_pct, capital_ini, reinvertir)
        return True
    return False
