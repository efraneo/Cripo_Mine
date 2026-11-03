# ==============================================================================
# MOTOR_IA.PY - Pipeline de 4 Dioses Especializados (Patrón -> Flujo -> Riesgo -> Juez)
# ==============================================================================
import re
import json
import requests

# ─── Función Unificada para Llamar Cualquier IA ─────────────────────────────
def llamar_api_ia(url, api_key, model, prompt, timeout=12.0, json_mode=False):
    if not api_key: return None, "Sin API Key"
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 300}
        if json_mode: payload["response_format"] = {"type": "json_object"}
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200: return None, f"HTTP {resp.status_code}"
        texto = resp.json()['choices'][0]['message']['content'].strip()
        match = re.search(r'\{[^{}]*\}', texto, re.DOTALL)
        if match:
            try: return json.loads(match.group()), None
            except json.JSONDecodeError: pass
        return None, "No JSON"
    except requests.exceptions.Timeout: return None, "Timeout"
    except Exception as e: return None, str(e)[:30]

# ─── PROMPT 1: GROQ (Analista Visual de Patrones) ──────────────────────────
def prompt_groq_patrones(datos):
    patrones_str = "\n".join([f"- {p}" for p in datos['patrones_japoneses']])
    return f"""Eres un MASTER en Velas Japonesas. Analiza esta vela de 1 minuto para {datos['symbol']}:
Cuerpo: {datos['cuerpo']} | Mecha Inf: {datos['mecha_inf']} | Mecha Sup: {datos['mecha_sup']}
Mi script detectó: {patrones_str}
¿Estás de acuerdo? ¿Hay algún patrón sutil que el script pasó por alto?
Responde SOLO JSON: {{"patron_confirmado": "Nombre exacto o NINGUNO", "sesgo_visual": "ALCISTA/BAJISTA/NEUTRO", "confianza_visual": 85}}"""

# ─── PROMPT 2: OPENAI (Analista de Flujo de Dinero y Macro) ────────────────
def prompt_openai_flujo(datos):
    return f"""Eres un analista de Flujo de Órdenes y Smart Money. Datos de {datos['symbol']}:
- Volumen vs Promedio: {datos['vol_ratio']}x {'(BALLENA DETECTADA)' if datos['es_ballena'] else ''}
- Trades en última vela: {datos['trades']}
- Sesión de Mercado: {datos['sesion']}
- Cambio 5 velas: {datos['cambio_5v']}%
Evalúa si el flujo de dinero respalda un movimiento alcista inminente.
Responde SOLO JSON: {{"flujo_dinero": "ALCISTA/BAJISTA/NEUTRO", "presion_smart_money": "ALTA/BAJA/NULA", "confianza_flujo": 80}}"""

# ─── PROMPT 3: DEEPSEEK (Gestor de Riesgo Cuantitativo) ─────────────────────
def prompt_deepseek_riesgo(datos):
    return f"""Eres un Gestor de Riesgo Cuantitativo estricto. Datos {datos['symbol']}:
- RSI 14: {datos['rsi']}/100
- Tendencia EMA: {datos['tendencia']}
- Distancia EMA 9: {datos['dist_ema9']}%
Evalúa matemáticamente si es seguro entrar en LONG ahora.
Responde SOLO JSON: {{"estado_riesgo": "BAJO/MEDIO/ALTO", "sesgo_tecnico": "ALCISTA/BAJISTA/NEUTRO", "confianza_tecnico": 75}}"""

# ─── PROMPT 4: Z.AI (El Juez / Director de Inversión) ──────────────────────
def prompt_zai_juez(datos, resp_groq, resp_openai, resp_deepseek, tp_pct):
    return f"""Eres el DIRECTOR DE INVERSIÓN FINAL. Tienes 3 reportes de expertos para {datos['symbol']} a {datos['precio']} USDT:
1. PATRONES VISUALES (Groq): {resp_groq}
2. FLUJO DE DINERO (OpenAI): {resp_openai}
3. RIESGO CUANTITATIVO (DeepSeek): {resp_deepseek}

REGLA ESTRICTA: Solo dictaminar COMPRA si los 3 reportes indican "ALCISTA" y ninguno dice "ALTO" riesgo.
Estrategia: LONG Scalping 3-5 min. TP: +{tp_pct}%.
Responde SOLO JSON: {{"decision": "COMPRA" o "NEUTRO", "veredicto": "Resumen de por qué en 15 palabras max", "confianza_total": 90}}"""

# ─── ✅ NUEVO: Pipeline de los 4 Dioses ─────────────────────────────────────
def consejo_4_dioses_especializados(ss, symbol, datos, tp_pct):
    """Ejecuta la cadena de 4 IAs especializadas que se comunican entre sí"""
    from config import agregar_log
    keys = ss.api_keys
    
    agregar_log(ss, f"🧠 Iniciando Pipeline 4 Dioses para {symbol}...")
    agregar_log(ss, f"   🎨 Patrones detectados: {', '.join(datos['patrones_japoneses'][:3])}")

    # ── FASE 1: Análisis Visual (Groq) ──
    agregar_log(ss, "   [1/4] 🎨 Consultando a Groq (Patrones Visuales)...")
    resp_groq, err1 = llamar_api_ia(
        "https://api.groq.com/openai/v1/chat/completions", keys.get('GROQ_API_KEY'),
        "llama3-8b-8192", prompt_groq_patrones(datos)
    )
    if resp_groq: agregar_log(ss, f"       ✅ Groq: {resp_groq.get('sesgo_visual')} [{resp_groq.get('patron_confirmado')}]")
    else: agregar_log(ss, f"       ❌ Groq falló: {err1}")
    resp_groq_str = json.dumps(resp_groq) if resp_groq else "No disponible"

    # ── FASE 2: Flujo de Dinero (OpenAI) ──
    agregar_log(ss, "   [2/4] 🌊 Consultando a OpenAI (Flujo de Dinero)...")
    resp_openai, err2 = llamar_api_ia(
        "https://api.openai.com/v1/chat/completions", keys.get('OPENAI_API_KEY'),
        "gpt-4o-mini", prompt_openai_flujo(datos)
    )
    if resp_openai: agregar_log(ss, f"       ✅ OpenAI: {resp_openai.get('flujo_dinero')} [Smart Money: {resp_openai.get('presion_smart_money')}]")
    else: agregar_log(ss, f"       ❌ OpenAI falló: {err2}")
    resp_openai_str = json.dumps(resp_openai) if resp_openai else "No disponible"

    # ── FASE 3: Riesgo Cuantitativo (DeepSeek) ──
    agregar_log(ss, "   [3/4] 📉 Consultando a DeepSeek (Riesgo Cuantitativo)...")
    resp_deepseek, err3 = llamar_api_ia(
        "https://api.deepseek.com/v1/chat/completions", keys.get('DEEPSEEK_API_KEY'),
        "deepseek-chat", prompt_deepseek_riesgo(datos), json_mode=True
    )
    if resp_deepseek: agregar_log(ss, f"       ✅ DeepSeek: {resp_deepseek.get('sesgo_tecnico')} [Riesgo: {resp_deepseek.get('estado_riesgo')}]")
    else: agregar_log(ss, f"       ❌ DeepSeek falló: {err3}")
    resp_deepseek_str = json.dumps(resp_deepseek) if resp_deepseek else "No disponible"

    # ── FASE 4: El Juez Final (Z.ai) ──
    agregar_log(ss, "   [4/4] 👑 Consultando a Z.ai (El Juez Final)...")
    resp_zai, err4 = llamar_api_ia(
        keys.get('ZAI_BASE_URL'), keys.get('ZAI_API_KEY'), keys.get('ZAI_MODEL', 'gpt-4o'),
        prompt_zai_juez(datos, resp_groq_str, resp_openai_str, resp_deepseek_str, tp_pct),
        json_mode=True, timeout=15.0
    )
    
    if resp_zai:
        decision_raw = str(resp_zai.get('decision', 'NEUTRO')).upper()
        veredicto = resp_zai.get('veredicto', '')
        confianza = resp_zai.get('confianza_total', 0)
        decision = "COMPRA" if "COMPRA" in decision_raw else "NEUTRO"
        
        agregar_log(ss, f"       👑 Z.ai VEREDICTO: {decision} - \"{veredicto}\"")
        agregar_log(ss, f"🎉 Pipeline completada exitosamente.")
        return decision, veredicto
    else:
        agregar_log(ss, f"       ❌ Z.ai falló: {err4}. Operación cancelada por seguridad.")
        return "NEUTRO", "Fallo el Juez (Z.ai)"
