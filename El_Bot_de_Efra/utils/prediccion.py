# utils/prediccion.py
# ==========================================================
# 🔮 Motor principal de combinación (versión IA reforzada)
# - Manejo robusto de entradas faltantes
# - Helpers internos añadidos (normalización, logistic, map de trust)
# - Safe imports para Fibonacci / logger
# ==========================================================

from typing import List, Dict, Any, Optional
import math

# -------------------------
# 🔧 Mapa por defecto de "trust" por método
# -------------------------
_DEFAULT_METHOD_TRUST: Dict[str, float] = {
    "RSI": 0.85,
    "MACD": 0.80,
    "Bollinger": 0.80,
    "MA Crossover": 0.78,
    "Volumen": 0.70,
    "ATR Breakout": 0.78,
    "ADX": 0.65,
    "Stochastic": 0.70,
    "Patrones": 0.75,
    "fallback": 0.50
}

# -------------------------
# 🔁 Helpers internos
# -------------------------
def normalizar_senal(s: Any) -> str:
    """Normalize input signal to 'BUY'|'SELL'|'HOLD'."""
    try:
        if s is None:
            return "HOLD"
        ss = str(s).strip().upper()
        if ss in ("BUY", "BUYER", "COMPRAR", "LONG"):
            return "BUY"
        if ss in ("SELL", "SHORT", "VENDER"):
            return "SELL"
        return "HOLD"
    except Exception:
        return "HOLD"


def _normalizar_confianza_raw(v: Any) -> float:
    """
    Normaliza valores de confianza heterogéneos:
      - Si viene en 0..1 -> lo devuelve
      - Si viene en 0..100 -> lo transforma a 0..1
      - Si viene como string numérico intenta parsear
    """
    try:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            vv = float(v)
            if vv > 1.0:
                # asumimos 0..100
                return max(0.0, min(1.0, vv / 100.0))
            return max(0.0, min(1.0, vv))
        vs = str(v).strip()
        # quitar % si existe
        if vs.endswith("%"):
            try:
                return max(0.0, min(1.0, float(vs[:-1]) / 100.0))
            except Exception:
                return 0.0
        return max(0.0, min(1.0, float(vs)))
    except Exception:
        return 0.0


def _logistic(x: float, a: float = 1.0, b: float = 0.5) -> float:
    """
    Función logística simple para mapear a probabilidad en (0,1).
    a controla pendiente, b desplazamiento.
    """
    try:
        z = a * (x - b)
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        # fallback lineal acotado
        return max(0.0, min(1.0, x))

def backtest_rapido_ensemble(df, window=50, horizonte=3):
    """
    Backtest rápido y sencillo que:
    - calcula señales 'metodo' sencillas (ej. cruce de close futuro) para las últimas `window` velas
    - compara la dirección real en el horizonte y devuelve una precision histórica 0..1.
    NOTA: es simple y rápido; ajústalo según tu lógica real.
    """
    try:
        if df is None or df.empty or len(df) < window + horizonte:
            return {"precision": 0.0, "samples": 0}

        df2 = df.copy().reset_index(drop=True)
        samples = 0
        aciertos = 0

        for i in range(len(df2) - window - horizonte, len(df2) - horizonte):
            # señal simple: si close actual < close futuro-horizonte => BUY, else SELL
            cur = df2.loc[i, "close"]
            fut = df2.loc[i + horizonte, "close"]
            if fut > cur:
                senal = "BUY"
            else:
                senal = "SELL"
            # etiqueta real
            real = "BUY" if fut > cur else "SELL"
            if senal == real:
                aciertos += 1
            samples += 1

        prec = aciertos / samples if samples > 0 else 0.0
        return {"precision": float(prec), "samples": samples}
    except Exception:
        return {"precision": 0.0, "samples": 0}


# -------------------------
# 🔮 combinar_senales
# -------------------------

def combinar_senales(
    metodos: List[Dict[str, Any]],
    prediccion_lstm: Optional[Dict[str, Any]] = None,
    peso_lstm: float = 0.5,
    umbral: float = 0.20,
    force_threshold: float = 0.75,
    method_trust_map: Optional[Dict[str, float]] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Combina señales de metodologías + LSTM + Fibonacci y devuelve:
      - senal: BUY / SELL / HOLD
      - score: -1..1
      - confianza: 0..1
      - resumen: lista de strings con detalles
      - forced: bool (si se forzó decisión)
    """
    try:
        resumen: List[str] = []
        trust_map = method_trust_map or _DEFAULT_METHOD_TRUST

        buy_w = sell_w = total_w = 0.0
        votes_count = 0

        # ========================
        # 📊 Métodos clásicos
        # ========================
        for m in (metodos or []):
            try:
                metodo = str(m.get("metodo", "metodo")).strip()
                senal = normalizar_senal(m.get("senal", "HOLD"))
                conf_raw = m.get("confianza", 0.5)
                conf = _normalizar_confianza_raw(conf_raw)
                trust = float(trust_map.get(metodo, trust_map.get(metodo.title(), 0.6)))
                peso = conf * trust

                resumen.append(f"{metodo}: {senal} (conf {conf:.2f}, trust {trust:.2f}, peso {peso:.3f})")

                if senal == "BUY":
                    buy_w += peso
                    votes_count += 1
                elif senal == "SELL":
                    sell_w += peso
                    votes_count += 1
                else:
                    total_w += peso * 0.25

                total_w += peso
            except Exception as e_m:
                if verbose:
                    resumen.append(f"⚠️ Metodo error: {e_m}")
                continue

        score_methods = (buy_w - sell_w) / total_w if total_w > 0 else 0.0

        # ========================
        # 🔮 LSTM (modelo IA)
        # ========================
        lstm_contrib = 0.0
        lstm_conf = 0.0
        if prediccion_lstm:
            try:
                tend = normalizar_senal(prediccion_lstm.get("tendencia", prediccion_lstm.get("accion", "HOLD")))
                lstm_conf = _normalizar_confianza_raw(prediccion_lstm.get("confianza", prediccion_lstm.get("precision", 0.0)))
                lstm_trust = 0.85
                peso_lstm_eff = lstm_conf * lstm_trust
                if tend == "BUY":
                    lstm_contrib = peso_lstm_eff
                elif tend == "SELL":
                    lstm_contrib = -peso_lstm_eff
                resumen.append(f"LSTM: {tend} (conf {lstm_conf:.2f}, peso_eff {peso_lstm_eff:.3f})")
            except Exception as e_l:
                if verbose:
                    resumen.append(f"⚠️ LSTM parse error: {e_l}")

        # ========================
        # 📐 Fibonacci (safe)
        # ========================
        try:
            try:
                from fibonacci import detectar_niveles_fibonacci  # type: ignore
            except Exception:
                detectar_niveles_fibonacci = None

            if detectar_niveles_fibonacci:
                try:
                    niveles = detectar_niveles_fibonacci(None)
                    if niveles:
                        resumen.append("Fibonacci detectado (niveles calculados)")
                except Exception:
                    if verbose:
                        resumen.append("detectar_niveles_fibonacci: sin datos reales (ignorado en test)")
        except Exception:
            pass

        # ========================
        # ⚖️ Combinación ponderada
        # ========================
        if prediccion_lstm:
            combined_raw = (1.0 - peso_lstm) * score_methods + peso_lstm * (lstm_contrib)
        else:
            combined_raw = score_methods

        combined = max(-1.0, min(1.0, float(combined_raw)))

        denom = abs(buy_w) + abs(sell_w)
        consensus = abs(buy_w - sell_w) / denom if denom > 0 else 0.0
        votes_factor = min(1.0, votes_count / 6.0)

        raw_comb_for_conf = abs(combined) * (0.6 + 0.4 * consensus) * (0.6 + 0.4 * votes_factor)
        conf_prob = _logistic(raw_comb_for_conf, a=9.0, b=0.30)

        if prediccion_lstm:
            conf_prob = conf_prob * 0.80 + lstm_conf * 0.20
            conf_prob = max(0.0, min(1.0, conf_prob))

        # ---------------------------------------------------
        # Justo antes de decidir: intentar backtest rápido (si tenemos df disponible)
        # ---------------------------------------------------
        hist_prec = 0.0
        try:
            df_for_bt = None
            # algunas llamadas pueden incluir un DF embebido en metodos o prediccion_lstm para testing
            if isinstance(metodos, dict) and metodos.get("_df"):
                df_for_bt = metodos.get("_df")
            elif isinstance(prediccion_lstm, dict) and prediccion_lstm.get("_df"):
                df_for_bt = prediccion_lstm.get("_df")
            # también aceptamos que un item special esté pegado al final de la lista:
            if not df_for_bt:
                for m in (metodos or []):
                    if isinstance(m, dict) and m.get("_df"):
                        df_for_bt = m.get("_df")
                        break

            if df_for_bt is not None:
                try:
                    from utils.backtesting import backtest_rapido_ensemble
                    bt = backtest_rapido_ensemble(df_for_bt)
                    hist_prec = float(bt.get("precision", 0.0) or 0.0)
                    resumen.append(f"Backtest rápido: precision histórica {hist_prec:.2f}")
                except Exception as e_bt:
                    if verbose:
                        resumen.append(f"⚠️ backtest rápido falló: {e_bt}")
                    hist_prec = 0.0
        except Exception:
            hist_prec = 0.0

        # si hist_prec alto (>0.60) y muestra suficientes samples, inyecta un pequeño bonus
        try:
            if hist_prec >= 0.60:
                bonus = min(0.08, (hist_prec - 0.60) * 0.2)  # hasta +8%
                conf_prob = min(0.99, conf_prob + bonus)
                resumen.append(f"Bonus por backtest: +{bonus*100:.2f}%")
        except Exception:
            pass

        # ================================
        # 🧪 Backtest rápido (seguro) — inyectar bonus si histórico robusto
        # ================================
        hist_prec = 0.0
        try:
            # Usamos ejecutar_backtest que acepta (df, activo, estrategia)
            from utils.backtesting import ejecutar_backtest

            df_for_bt = None

            # 1) Buscar df asociado en 'metodos' (metodos puede ser lista con un dict "_df")
            if isinstance(metodos, dict) and "_df" in metodos:
                df_for_bt = metodos["_df"]
            elif isinstance(metodos, list):
                # buscamos una entrada que contenga el df (no rompe si no existe)
                for m in metodos:
                    if isinstance(m, dict) and "_df" in m:
                        df_for_bt = m["_df"]
                        break

            # 2) Ejecutar backtest solo si tenemos DataFrame válido
            if df_for_bt is not None:
                # ejecutar_backtest devuelve (resultados, operaciones)
                bt_resultados, bt_operaciones = ejecutar_backtest(df_for_bt, activo="RECENT", estrategia="Cruce de Medias", capital_inicial=1000)
                # Algunos wrappers devuelven winrate como 'winrate'
                hist_prec = float(bt_resultados.get("winrate", 0.0) or 0.0)

                # Mapear métricas para UI (opcionalmente las incluimos en el resumen)
                resumen.append(f"📈 Backtest: winrate {hist_prec*100:.1f}%, trades {bt_resultados.get('num_trades', 0)}")

                # 3) Si el histórico es bueno, aplicar bonus a conf_prob (hasta +8%)
                if hist_prec >= 0.60:
                    bonus = min(0.08, (hist_prec - 0.60) * 0.2)  # escalado suave
                    old_conf = conf_prob
                    conf_prob = min(0.99, conf_prob + bonus)
                    resumen.append(f"🧠 Bonus histórico aplicado: +{bonus*100:.2f}% (conf {old_conf*100:.2f}% → {conf_prob*100:.2f}%)")
        except Exception as e_bt:
            # No interrumpir pipeline por el backtest
            if verbose:
                resumen.append(f"⚠️ Backtest omitido: {e_bt}")
            hist_prec = 0.0


        # ========================
        # 🏁 Decisión inicial
        # ========================
        if conf_prob < umbral:
            decision = "HOLD"
        else:
            decision = "BUY" if combined > 0 else "SELL"

        forced = False
        if decision == "HOLD" and conf_prob >= force_threshold:
            forced = True
            decision = "BUY" if combined >= 0 else "SELL"

        # ================================
        # 🚀 BOOST DE CONFIANZA INTELIGENTE (safe)
        # ================================
        try:
            from utils.confidence_boost import (
                boost_confidence_and_alert,
                dynamic_confidence_boost
            )
            rf_score_placeholder = 0.65
            consistencia_placeholder = consensus
            error_score_placeholder = 1.0 - (lstm_conf or 0.0)
            estabilidad_placeholder = votes_factor

            conf_ajustada, forced_boost = boost_confidence_and_alert(
                metodologias=metodos,
                prediccion_lstm=prediccion_lstm,
                confianza_actual=float(conf_prob),
                score_methods=score_methods,
                rf_score=rf_score_placeholder,
                consistencia=consistencia_placeholder,
                error_score=error_score_placeholder,
                estabilidad=estabilidad_placeholder,
                resumen="\n".join(resumen)
            )

            if conf_ajustada >= 0.90:
                conf_ajustada, forced_boost = dynamic_confidence_boost(
                    metodologias=metodos,
                    prediccion_lstm=prediccion_lstm,
                    confianza_actual=conf_ajustada,
                    score_methods=score_methods,
                    rf_score=rf_score_placeholder,
                    consistencia=consistencia_placeholder,
                    error_score=error_score_placeholder,
                    estabilidad=estabilidad_placeholder,
                    resumen="\n".join(resumen)
                )

            if forced_boost:
                resumen.append(f"⚡ Confianza IA reforzada a {conf_ajustada*100:.2f}% (boost inteligente aplicado)")
                conf_prob = conf_ajustada
                forced = True

        except Exception as e_boost:
            if verbose:
                resumen.append(f"⚠️ Error aplicando refuerzo IA: {e_boost}")

        # ------------------------
        # Aseguramiento final
        # ------------------------
        try:
            conf_prob = float(conf_prob)
        except Exception:
            conf_prob = 0.0

        # Evitar mostrar valores absurdamente bajos: dejar un piso en 0.05 (visual)
        conf_prob = max(0.05, min(conf_prob, 0.99))

        if verbose:
            resumen.append(f"DEBUG: buy_w={buy_w:.4f}, sell_w={sell_w:.4f}, total_w={total_w:.4f}, score_methods={score_methods:.4f}")
            resumen.append(f"DEBUG: combined={combined:.4f}, consensus={consensus:.4f}, votes={votes_count}, conf_prob={conf_prob:.4f}")

        return {
            "senal": decision,
            "score": round(combined, 6),
            "confianza": round(float(conf_prob), 6),
            "resumen": resumen,
            "forced": forced
        }

    except Exception as e:
        return {
            "senal": "HOLD",
            "score": 0.0,
            "confianza": 0.0,
            "resumen": [f"❌ Error en combinar_senales: {e}"],
            "forced": False
        }
