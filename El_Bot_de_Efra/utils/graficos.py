# utils/graficos.py
# ==========================================================
# Módulo de visualización de datos financieros y señales.
# - Compatible con Matplotlib, mplfinance y Plotly.
# - Guarda gráficos (forzando Kaleido para Plotly cuando sea posible).
# - Extiende DataFrames para mostrar "predicción visual".
# - Calcula heurística para ajustar confianza del modelo.
# - Exporta y envía gráficos a Telegram de forma robusta.
# ==========================================================

from typing import Any, Optional, Dict, List
import os
import io
import math
import re
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Plotly
import plotly.graph_objs as go
import plotly.express as px
import plotly.io as pio

# Matplotlib / mplfinance (import guard)
try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None

try:
    import mplfinance as mpf
except Exception:
    mpf = None

# Logger para capturar errores
from utils.logger import log_error, log_info, log_warning

# ------------------------
# Utilidades y helpers
# ------------------------

def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asegura que el índice de df sea DatetimeIndex. Si no, intenta convertir.
    Devuelve copia del df con índice datetime o el df original si falla.
    """
    try:
        if df is None:
            return df
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            # Si hay columna 'fecha' o similar, también lo intentamos
            if "fecha" in df.columns:
                df.index = pd.to_datetime(df["fecha"])
            else:
                df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log_warning(f"_ensure_datetime_index: {e}", archivo="graficos.py", funcion="_ensure_datetime_index")
        return df

# ==========================================================
# 📈 Visualización con Matplotlib (legacy)
# ==========================================================
def plot_candlestick_matplotlib(df: pd.DataFrame, title: str = "Gráfico de Velas"):
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío en plot_candlestick_matplotlib")

        if plt is None:
            raise ImportError("matplotlib no disponible")

        df_local = _ensure_datetime_index(df)

        fig, ax = plt.subplots(figsize=(12, 6))

        alcistas = df_local[df_local["close"] >= df_local["open"]]
        ax.bar(alcistas.index, alcistas["close"] - alcistas["open"],
               bottom=alcistas["open"], color="green", width=0.01, align="center")
        ax.vlines(alcistas.index, alcistas["low"], alcistas["high"], color="green")

        bajistas = df_local[df_local["close"] < df_local["open"]]
        ax.bar(bajistas.index, bajistas["close"] - bajistas["open"],
               bottom=bajistas["open"], color="red", width=0.01, align="center")
        ax.vlines(bajistas.index, bajistas["low"], bajistas["high"], color="red")

        ax.set_title(title)
        ax.set_ylabel("Precio")
        fig.autofmt_xdate()
        plt.tight_layout()
        plt.show()
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_candlestick_matplotlib")

def plot_metricas_matplotlib(metricas: Dict[str, float], title: str = "Métricas de Estrategia"):
    try:
        if not metricas:
            raise ValueError("No se proporcionaron métricas para graficar")

        if plt is None:
            raise ImportError("matplotlib no disponible")

        fig, ax = plt.subplots(figsize=(10, 5))
        keys, values = list(metricas.keys()), list(metricas.values())
        ax.bar(keys, values, edgecolor="black")

        ax.set_title(title)
        ax.set_ylabel("Valor")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_metricas_matplotlib")

# ==========================================================
# 📈 Visualización con Plotly (moderna)
# ==========================================================
def plot_candlestick_plotly(df: pd.DataFrame, title: str = "Gráfico de Velas (Plotly)") -> go.Figure:
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío en plot_candlestick_plotly")
        df_local = _ensure_datetime_index(df)

        fig = go.Figure(
            data=[go.Candlestick(
                x=df_local.index,
                open=df_local["open"],
                high=df_local["high"],
                low=df_local["low"],
                close=df_local["close"],
                name="Velas"
            )]
        )
        fig.update_layout(
            title=title,
            xaxis_title="Fecha",
            yaxis_title="Precio",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=600
        )
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_candlestick_plotly")
        return go.Figure()

def plot_candlestick_with_indicators(df: pd.DataFrame, indicadores: Dict[str, pd.Series] = None,
                                     title: str = "Velas con Indicadores (Plotly)") -> go.Figure:
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío en plot_candlestick_with_indicators")
        df_local = _ensure_datetime_index(df)

        fig = make_subplots = None  # placeholder if user wants subplots; we'll keep a single figure for simplicity
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df_local.index, open=df_local["open"], high=df_local["high"],
            low=df_local["low"], close=df_local["close"], name="OHLC"
        ))
        if "volume" in df_local.columns:
            fig.add_trace(go.Bar(x=df_local.index, y=df_local["volume"], name="Volumen", marker_color="lightblue"))

        if indicadores:
            for nombre, serie in indicadores.items():
                try:
                    fig.add_trace(go.Scatter(x=serie.index, y=serie.values, mode="lines", name=nombre))
                except Exception:
                    continue

        fig.update_layout(title=title, xaxis_rangeslider_visible=False, template="plotly_dark", height=700)
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_candlestick_with_indicators")
        return go.Figure()

# ==========================================================
# 📊 Comparaciones y proyecciones
# ==========================================================
def plot_comparacion_activos(df_dict: Dict[str, pd.DataFrame], title: str = "Comparación de Activos") -> go.Figure:
    try:
        if not df_dict:
            raise ValueError("df_dict vacío en plot_comparacion_activos")
        fig = go.Figure()
        for activo, df in df_dict.items():
            if df is None or df.empty or "close" not in df.columns:
                continue
            serie_norm = df["close"] / df["close"].iloc[0] * 100
            fig.add_trace(go.Scatter(x=df.index, y=serie_norm, mode="lines", name=activo))
        fig.update_layout(title=title, xaxis_title="Fecha", yaxis_title="Precio Normalizado (100=Inicio)", template="plotly_dark")
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_comparacion_activos")
        return go.Figure()

def plot_predicciones_vs_real(df: pd.DataFrame, predicciones: List[float],
                              title: str = "Proyección vs Real"):
    try:
        if df is None or df.empty or "close" not in df.columns:
            raise ValueError("DataFrame inválido en plot_predicciones_vs_real")
        if not predicciones:
            raise ValueError("Lista de predicciones vacía")
        if plt is None:
            raise ImportError("matplotlib no disponible")
        fig, ax = plt.subplots(figsize=(10, 5))
        df["close"].tail(200).plot(ax=ax, label="Histórico")
        pred_index = range(len(df), len(df) + len(predicciones))
        ax.plot(pred_index, predicciones, "--", label="Proyección IA")
        ax.legend()
        ax.set_title(title)
        ax.set_xlabel("Tiempo")
        ax.set_ylabel("Precio")
        plt.tight_layout()
        plt.show()
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_predicciones_vs_real")

def plot_heatmap_correlacion(df_dict: Dict[str, pd.DataFrame], title: str = "Matriz de Correlación") -> go.Figure:
    try:
        if not df_dict:
            raise ValueError("df_dict vacío en plot_heatmap_correlacion")
        precios = pd.DataFrame({
            activo: df["close"] if ("close" in df.columns and not df.empty) else pd.Series(dtype=float)
            for activo, df in df_dict.items()
        }).dropna(axis=1, how="all")
        if precios.empty:
            raise ValueError("No hay precios válidos para calcular correlación")
        corr = precios.corr()
        fig = px.imshow(corr, text_auto=True, color_continuous_scale="RdBu_r", title=title, aspect="auto")
        fig.update_layout(template="plotly_dark")
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="plot_heatmap_correlacion")
        return go.Figure()

# ==========================================================
# Generadores auxiliares (compatibilidad original)
# ==========================================================
def generar_grafico_velas(df: pd.DataFrame, titulo: str = "Gráfico de Velas") -> go.Figure:
    """
    Crea y devuelve un plotly.go.Figure de velas a partir del DataFrame.
    Mantener para compatibilidad con otras partes del proyecto.
    """
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío en generar_grafico_velas.")
        if not all(col in df.columns for col in ["open", "high", "low", "close"]):
            raise ValueError("El DataFrame debe contener columnas open, high, low, close.")

        df_local = _ensure_datetime_index(df)
        fig = go.Figure(data=[go.Candlestick(
            x=df_local.index,
            open=df_local["open"],
            high=df_local["high"],
            low=df_local["low"],
            close=df_local["close"],
            name="Velas"
        )])
        fig.update_layout(
            title=titulo,
            xaxis_title="Tiempo",
            yaxis_title="Precio",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=600
        )
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="generar_grafico_velas")
        return go.Figure()

def generar_heatmap(df: pd.DataFrame, columnas: Optional[List[str]] = None, titulo: str = "Heatmap de correlaciones") -> go.Figure:
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío en generar_heatmap.")
        if columnas is None:
            columnas = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        corr = df[columnas].corr()
        fig = px.imshow(corr, text_auto=True, aspect="auto", color_continuous_scale="RdBu_r", title=titulo)
        fig.update_layout(template="plotly_dark")
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="generar_heatmap")
        return go.Figure()

def generar_caja_riesgo(df: pd.DataFrame, columna: str = "close", titulo: str = "Distribución de Riesgo") -> go.Figure:
    try:
        if df is None or df.empty or columna not in df.columns:
            raise ValueError(f"DataFrame inválido en generar_caja_riesgo: falta columna {columna}")
        fig = px.box(df, y=columna, points="all", title=titulo)
        fig.update_layout(template="plotly_dark")
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="generar_caja_riesgo")
        return go.Figure()

# ==========================================================
# --- NUESTROS NUEVOS: Extensión de DF y confianza mejorada
# ==========================================================
def extender_df_prediccion(df: pd.DataFrame, minutos: int = 60, freq: str = "1min") -> pd.DataFrame:
    """
    Extiende el DataFrame hacia el futuro rellenando con último precio conocido.
    Útil para mostrar el área proyectada en los gráficos.
    """
    try:
        if df is None or df.empty:
            return df
        df_local = _ensure_datetime_index(df)
        last_time = df_local.index[-1]
        start = last_time + pd.Timedelta(freq)
        end = last_time + pd.Timedelta(minutes=minutos)
        if start > end:
            return df_local.copy()
        future_index = pd.date_range(start=start, end=end, freq=freq)
        if len(future_index) == 0:
            return df_local.copy()
        future_df = pd.DataFrame(index=future_index, columns=df_local.columns)
        last_row = df_local.iloc[[-1]]
        for col in df_local.columns:
            try:
                future_df[col] = last_row[col].iloc[0]
            except Exception:
                future_df[col] = np.nan
        result = pd.concat([df_local, future_df])
        return result
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="extender_df_prediccion")
        return df

# --- Heurística para mejorar la confianza del modelo combinando señales técnicas ---
def calcular_confianza_mejorada(model_conf: float, df: pd.DataFrame) -> float:
    """
    Ajusta la confianza del modelo (0..1) con heurística basada en indicadores.
    Ya NO aplica boosts aleatorios ni mínimos arbitrarios.
    """
    try:
        conf = float(model_conf) if model_conf is not None else 0.0
        conf = max(0.0, min(1.0, conf))
        if df is None or df.empty:
            return conf

        score = 0.0
        weight_total = 0.0

        # RSI
        try:
            if "rsi" in df.columns:
                rsi = float(df["rsi"].iloc[-1])
                weight = 0.2
                weight_total += weight
                if rsi < 30 or rsi > 70:
                    score += weight * 0.9
                else:
                    score += weight * (abs(50 - rsi) / 50) * 0.5
        except Exception:
            pass

        # MACD
        try:
            if "macd" in df.columns and "macd_signal" in df.columns:
                macd = float(df["macd"].iloc[-1])
                signal = float(df["macd_signal"].iloc[-1])
                weight = 0.25
                weight_total += weight
                score += weight * (1.0 if macd - signal > 0 else 0.0)
        except Exception:
            pass

        # Volumen
        try:
            if "volume" in df.columns and len(df) >= 20:
                vol = float(df["volume"].iloc[-1])
                vol_med = float(df["volume"].tail(20).median())
                weight = 0.15
                weight_total += weight
                if vol_med > 0:
                    score += weight * min(1.0, vol / (1.5 * vol_med))
        except Exception:
            pass

        # Momentum
        try:
            if "close" in df.columns and len(df) >= 6:
                close = df["close"].iloc[-6:]
                weight = 0.25
                weight_total += weight
                returns = (close.iloc[-1] - close.iloc[0]) / (close.iloc[0] + 1e-9)
                score += weight * (0.5 + 0.5 * np.tanh(returns * 10))
        except Exception:
            pass

        if weight_total > 0:
            adj = score / weight_total
            combined = 0.7 * conf + 0.3 * adj
            combined = max(0.0, min(1.0, combined))
        else:
            combined = conf

        return round(float(combined), 4)
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="calcular_confianza_mejorada")
        return round(float(max(0.0, min(1.0, model_conf or 0.0))), 4)

# ==========================================================
# 📈 Extender gráfico con predicción robusta (+X min)
# Basada en patrones de velas (14 metodologías del bot)
# ==========================================================
def extender_grafico_prediccion(fig, df, minutos_extra: int = 5, patrones_detectados=None):
    """
    Extiende un gráfico Plotly con una predicción simulada de +X minutos
    representada como mini-velas (candlesticks) basadas en los patrones
    detectados (14 metodologías del bot).

    - fig: objeto Plotly ya generado.
    - df: DataFrame original con ['open','high','low','close'].
    - minutos_extra: minutos hacia adelante a simular.
    - patrones_detectados: lista o str de patrones detectados.
    """
    import pandas as pd
    import numpy as np
    from datetime import timedelta

    try:
        if df is None or df.empty:
            return fig

        # Última vela real
        last_row = df.iloc[-1]
        last_time = pd.to_datetime(last_row.name if "time" not in df.columns else last_row["time"])
        last_close = float(last_row["close"])

        # ---------------------------
        # Definir sesgo según patrones
        # ---------------------------
        tendencia = "neutral"
        if patrones_detectados:
            patrones_text = ", ".join(patrones_detectados).lower() if isinstance(patrones_detectados, list) else str(patrones_detectados).lower()

            alcistas = ["martillo", "envolvente alcista", "tres soldados blancos", "morning star"]
            bajistas = ["shooting star", "envolvente bajista", "tres cuervos negros", "evening star"]
            neutros  = ["doji", "spinning top"]

            if any(p in patrones_text for p in alcistas):
                tendencia = "alcista"
            elif any(p in patrones_text for p in bajistas):
                tendencia = "bajista"
            elif any(p in patrones_text for p in neutros):
                tendencia = "neutral"

        # ---------------------------
        # Simulación de velas
        # ---------------------------
        future_times, opens, highs, lows, closes = [], [], [], [], []
        precio = last_close

        # Definir drift según tendencia
        if tendencia == "alcista":
            drift = 0.0015   # +0.15% por vela
        elif tendencia == "bajista":
            drift = -0.0015  # -0.15% por vela
        else:
            drift = 0.0002   # lateral

        np.random.seed(42)
        noise = np.random.normal(0, 0.0007, size=minutos_extra)  # volatilidad leve

        for i in range(minutos_extra):
            open_p = precio
            close_p = open_p * (1 + drift + noise[i])
            high_p = max(open_p, close_p) * (1 + abs(noise[i]))
            low_p  = min(open_p, close_p) * (1 - abs(noise[i]))

            t = last_time + timedelta(minutes=i+1)

            future_times.append(t)
            opens.append(open_p)
            highs.append(high_p)
            lows.append(low_p)
            closes.append(close_p)

            precio = close_p

        # ---------------------------
        # Dibujar mini velas proyectadas
        # ---------------------------
        fig.add_trace(go.Candlestick(
            x=future_times,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name=f"Predicción +{minutos_extra}min ({tendencia})",
            increasing=dict(line=dict(color="orange")),
            decreasing=dict(line=dict(color="darkred")),
            opacity=0.6
        ))

        return fig

    except Exception as e:
        log_warning(f"extender_grafico_prediccion error: {e}", archivo="graficos.py", funcion="extender_grafico_prediccion")
        return fig

# -------------------------------------------
# GRAFICAR VELAS CON SEÑAL
# -------------------------------------------

def graficar_velas_con_senal(
    df: pd.DataFrame,
    activo: str,
    accion: Optional[str] = None,
    extend_minutes: int = 10,
    show_future_shade: bool = True,
    patrones: Optional[List[str]] = None,
    **kwargs  # 🔥 compatibilidad: acepta 'senal', 'confianza', etc.
) -> Optional[go.Figure]:
    """
    Genera un gráfico Plotly robusto con soporte para argumentos adicionales.
    Compatible con Streamlit y los módulos que pasen kwargs inesperados.
    """
    try:
        if df is None or df.empty:
            log_warning("graficar_velas_con_senal: DataFrame vacío", archivo="graficos.py", funcion="graficar_velas_con_senal")
            return None

        # --- Validar columnas mínimas ---
        columnas_requeridas = {"open", "high", "low", "close"}
        if not columnas_requeridas.issubset(df.columns):
            log_warning(f"graficar_velas_con_senal: columnas faltantes ({columnas_requeridas - set(df.columns)})", archivo="graficos.py", funcion="graficar_velas_con_senal")
            return None

        # --- Preparar índice temporal ---
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

        df.index = df.index.tz_convert("America/Bogota")

        # --- Extensión visual ---
        df_ext = extender_df_prediccion(df, minutos=extend_minutes, freq="1min")
        if df_ext is None or df_ext.empty:
            df_ext = df.copy()

        # --- Crear figura base ---
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df_ext.index,
                    open=df_ext["open"],
                    high=df_ext["high"],
                    low=df_ext["low"],
                    close=df_ext["close"],
                    name="Velas",
                    increasing=dict(line=dict(color="#00b894")),
                    decreasing=dict(line=dict(color="#d63031")),
                )
            ]
        )

        # --- Volumen ---
        if "volume" in df_ext.columns:
            fig.add_trace(
                go.Bar(
                    x=df_ext.index,
                    y=df_ext["volume"],
                    name="Volumen",
                    yaxis="y2",
                    opacity=0.3
                )
            )

        # --- Señal de trading ---
        senal = accion or kwargs.get("senal")
        if senal:
            last_real_idx = df.index[-1]
            color = "#2ecc71" if senal.lower() == "buy" else "#e74c3c"
            fig.add_trace(
                go.Scatter(
                    x=[last_real_idx],
                    y=[df.loc[last_real_idx, "close"]],
                    mode="markers+text",
                    marker=dict(color=color, size=12),
                    text=[senal.upper()],
                    textposition="top center",
                    name="Señal"
                )
            )

        # --- Área futura ---
        if show_future_shade:
            fig.add_vrect(
                x0=df.index[-1],
                x1=df_ext.index[-1],
                fillcolor="rgba(0,100,200,0.05)",
                layer="below",
                line_width=0,
                annotation_text="Proyección",
                annotation_position="top left"
            )

        # --- Extensión predicción +5 min ---
        fig = extender_grafico_prediccion(fig, df, minutos_extra=5, patrones_detectados=patrones)

        # --- Layout final ---
        fig.update_layout(
            title=f"📈 {activo} — Señal: {senal.upper() if senal else 'N/A'}",
            xaxis=dict(
                title="Fecha / Hora (local)",
                type="date",
                tickformat="%d-%m %H:%M",
                rangeslider=dict(visible=False),
                tickangle=-45
            ),
            yaxis=dict(title="Precio"),
            yaxis2=dict(title="Volumen", overlaying="y", side="right", showgrid=False),
            template="plotly_white",
            margin=dict(l=40, r=20, t=50, b=80),
            hovermode="x unified",
            height=600
        )

        return fig

    except Exception as e:
        log_error(f"graficar_velas_con_senal falló: {e}", archivo="graficos.py", funcion="graficar_velas_con_senal")
        return None

# ==========================================================
# Compatibilidad para trading_bot.py: graficar_candlestick acepta niveles_fibo y mostrar_senales
# ==========================================================
def graficar_candlestick(df: pd.DataFrame, titulo: str = "Gráfico de Velas (Compatibilidad)", niveles_fibo: Optional[List[float]] = None, mostrar_senales: bool = False) -> go.Figure:
    """
    API de compatibilidad: acepta niveles_fibo (lista de valores) y mostrar_senales.
    Devuelve un Plotly Figure (usado por trading_bot.py).
    """
    try:
        fig = generar_grafico_velas(df, titulo=titulo)
        # Añadir niveles Fibo si llegan como lista numérica
        if niveles_fibo:
            shapes, annotations = [], []
            for i, lvl in enumerate(sorted(set([float(x) for x in niveles_fibo]))):
                shapes.append(dict(type="line", xref="paper", x0=0, x1=1, yref="y", y0=lvl, y1=lvl, line=dict(dash="dash", width=1, color="yellow")))
                annotations.append(dict(xref="paper", x=0.99, y=lvl, xanchor="right", yanchor="middle", text=f"Fibo {i+1}: {lvl:.2f}", showarrow=False, font=dict(size=10, color="yellow")))
            fig.update_layout(shapes=(fig.layout.shapes or []) + shapes, annotations=(fig.layout.annotations or []) + annotations)
        # Si mostrar_senales: intentar marcar última vela (si existen columnas)
        if mostrar_senales and df is not None and not df.empty and "close" in df.columns:
            try:
                last_idx = _ensure_datetime_index(df).index[-1]
                fig.add_trace(go.Scatter(x=[last_idx], y=[df["close"].iloc[-1]], mode="markers", marker=dict(size=10, color="cyan"), name="Última"))
            except Exception:
                pass
        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="graficar_candlestick")
        return go.Figure()

# ==========================================================
# 💾 Guardado universal de gráficos (Plotly / Matplotlib / mplfinance)
# ==========================================================
def guardar_grafico(fig: Any, filename: str = "grafico.png", carpeta: str = "graficos") -> Optional[str]:
    """
    Guarda una figura detectando su tipo (Plotly, Matplotlib, mplfinance).
    - Usa Kaleido si es Plotly.
    - Usa savefig() si es Matplotlib.
    - Detecta figuras mplfinance (tupla).
    Devuelve la ruta completa o None si falla.
    """
    try:
        os.makedirs(carpeta, exist_ok=True)
        path = os.path.join(carpeta, filename)

        # --- Plotly ---
        try:
            import plotly.graph_objects as go
            if isinstance(fig, go.Figure):
                fig.update_layout(template="plotly_white", autosize=True)
                try:
                    fig.write_image(path, format="png", scale=2, engine="kaleido")
                    log_info(f"guardar_grafico: Plotly exportado en {path}", archivo="graficos.py", funcion="guardar_grafico")
                    return path
                except Exception as e_k:
                    log_warning(f"Kaleido falló ({e_k}), usando fallback HTML-screenshot.", archivo="graficos.py", funcion="guardar_grafico")
                    try:
                        import plotly.io as pio
                        pio.write_image(fig, path, format="png", scale=2)
                        return path
                    except Exception:
                        pass
        except Exception:
            pass

        # --- Matplotlib ---
        try:
            import matplotlib.figure
            if isinstance(fig, matplotlib.figure.Figure) and hasattr(fig, "savefig"):
                fig.savefig(path, dpi=150, bbox_inches="tight")
                log_info(f"guardar_grafico: Matplotlib guardado en {path}", archivo="graficos.py", funcion="guardar_grafico")
                return path
        except Exception as e:
            log_warning(f"No se pudo guardar figura Matplotlib: {e}", archivo="graficos.py", funcion="guardar_grafico")

        # --- mplfinance ---
        try:
            if isinstance(fig, tuple) and len(fig) > 0 and hasattr(fig[0], "savefig"):
                fig[0].savefig(path, dpi=150, bbox_inches="tight")
                log_info(f"guardar_grafico: mplfinance guardado en {path}", archivo="graficos.py", funcion="guardar_grafico")
                return path
        except Exception as e_mpf:
            log_warning(f"guardar_grafico: mplfinance falló -> {e_mpf}", archivo="graficos.py", funcion="guardar_grafico")

        log_warning("guardar_grafico: tipo de figura no reconocido o no soportado.", archivo="graficos.py", funcion="guardar_grafico")
        return None

    except Exception as e:
        log_error(f"Error general guardando gráfico: {e}", archivo="graficos.py", funcion="guardar_grafico")
        return None

# ==========================================================
# Enviar Grafico a Telegram
# ==========================================================
def enviar_grafico_telegram(fig: Any, mensaje: str, filename: str = "grafico.png") -> bool:
    """
    Guarda el gráfico y envía UN único mensaje a Telegram con la imagen y el texto.
    - Intenta usar telegram_alertas helpers.
    - Si no, hace POST directo a la API de Telegram.
    Retorna True si el envío fue exitoso.
    """
    try:
        path = guardar_grafico(fig, filename=filename)
        if not path:
            log_warning("enviar_grafico_telegram: no se pudo guardar gráfico", archivo="graficos.py", funcion="enviar_grafico_telegram")
            return False

        # --- Usar telegram_alertas helpers ---
        try:
            from telegram_alertas import send_telegram_chart
            try:
                send_telegram_chart(path, caption=mensaje)
                log_info("enviar_grafico_telegram: enviado vía telegram_alertas.send_telegram_chart", archivo="graficos.py", funcion="enviar_grafico_telegram")
                return True
            except Exception as e:
                log_warning(f"send_telegram_chart falló: {e}", archivo="graficos.py", funcion="enviar_grafico_telegram")
        except Exception:
            pass  # no hay telegram_alertas

        # --- Fallback HTTP directo ---
        try:
            from config_loader import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
                log_warning("enviar_grafico_telegram: Telegram no configurado", archivo="graficos.py", funcion="enviar_grafico_telegram")
                return False

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": mensaje, "parse_mode": "HTML"}
                import requests
                r = requests.post(url, data=data, files=files, timeout=30)
                if r.status_code in (200, 201):
                    log_info("enviar_grafico_telegram: enviado vía API HTTP", archivo="graficos.py", funcion="enviar_grafico_telegram")
                    return True
                else:
                    log_warning(f"enviar_grafico_telegram: fallo HTTP {r.status_code} {r.text}", archivo="graficos.py", funcion="enviar_grafico_telegram")
                    return False
        except Exception as e:
            log_error(e, archivo="graficos.py", funcion="enviar_grafico_telegram")
            return False

    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="enviar_grafico_telegram")
        return False


# Alias retrocompatible
def enviar_imagen_telegram(ruta_imagen: str, mensaje: str = "📊 Gráfico"):
    """
    Alias para compatibilidad con código viejo que usaba enviar_imagen_telegram.
    Usa internamente send_telegram_chart si existe, o fallback HTTP.
    """
    try:
        if os.path.exists(ruta_imagen):
            try:
                from telegram_alertas import send_telegram_chart
                send_telegram_chart(ruta_imagen, caption=mensaje)
                return True
            except Exception:
                pass
            try:
                from config_loader import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                with open(ruta_imagen, "rb") as f:
                    import requests
                    files = {"photo": f}
                    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": mensaje, "parse_mode": "HTML"}
                    requests.post(url, data=data, files=files, timeout=30)
                    return True
            except Exception as e:
                log_error(e, archivo="graficos.py", funcion="enviar_imagen_telegram")
                return False
        return False
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="enviar_imagen_telegram")
        return False

# ==========================================================
# Fin archivo utils/graficos.py
# ==========================================================
