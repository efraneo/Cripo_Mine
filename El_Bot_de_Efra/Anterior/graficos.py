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

def calcular_confianza_mejorada(model_conf: float, df: pd.DataFrame) -> float:
    """
    Ajusta la confianza del modelo usando heurísticas (RSI, MACD, volumen, momentum).
    Devuelve valor entre 0 y 1.
    """
    try:
        conf = float(model_conf) if model_conf is not None else 0.0
        if df is None or df.empty:
            return min(max(conf, 0.0), 1.0)
        score = 0.0
        weight_total = 0.0

        # RSI
        try:
            rsi = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else None
            if rsi is not None:
                w = 0.2
                weight_total += w
                if rsi < 30 or rsi > 70:
                    score += w * 0.9
                else:
                    score += w * (abs(50 - rsi) / 50) * 0.5
        except Exception:
            pass

        # MACD
        try:
            macd = float(df["macd"].iloc[-1]) if "macd" in df.columns else None
            signal = float(df["macd_signal"].iloc[-1]) if "macd_signal" in df.columns else None
            if macd is not None and signal is not None:
                w = 0.25
                weight_total += w
                diff = macd - signal
                score += w * (1.0 if diff > 0 else 0.0) * min(abs(diff) / (abs(signal) + 1e-6), 1.0)
        except Exception:
            pass

        # Volumen
        try:
            vol = float(df["volume"].iloc[-1]) if "volume" in df.columns else None
            vol_med = float(df["volume"].tail(20).median()) if "volume" in df.columns and len(df) >= 20 else None
            if vol is not None and vol_med and vol_med > 0:
                w = 0.15
                weight_total += w
                if vol > 1.5 * vol_med:
                    score += w * 0.9
                else:
                    score += w * (vol / (vol_med * 1.5))
        except Exception:
            pass

        # Momentum precio corto plazo
        try:
            close = df["close"].iloc[-6:] if "close" in df.columns else None
            if close is not None and len(close) >= 3:
                w = 0.25
                weight_total += w
                returns = (close.iloc[-1] - close.iloc[0]) / (close.iloc[0] + 1e-9)
                score += w * (0.5 + 0.5 * np.tanh(returns * 10))
        except Exception:
            pass

        if weight_total > 0:
            adj = score / weight_total
            combined = 0.7 * conf + 0.3 * adj
            return max(0.0, min(1.0, combined))
        else:
            return max(0.0, min(1.0, conf))
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="calcular_confianza_mejorada")
        return float(model_conf if model_conf is not None else 0.0)

# ==========================================================
# 📊 Gráficos principales con señal
# - graficar_velas_con_senal devuelve un Plotly Figure (para st.plotly_chart)
# - También ofrezco una versión MPLFinance -> graficar_velas_con_senal_mpf
# ==========================================================
def graficar_velas_con_senal(
    df: pd.DataFrame,
    activo: str,
    accion: Optional[str] = None,
    extend_minutes: int = 10,
    show_future_shade: bool = True
) -> Optional[go.Figure]:
    """
    Genera un go.Figure (Plotly) con velas y señal. Extiende visualmente el df hacia el futuro
    con 'extend_minutes' y sombrea el área proyectada.
    """
    try:
        if df is None or df.empty:
            log_warning("graficar_velas_con_senal: DataFrame vacío", archivo="graficos.py", funcion="graficar_velas_con_senal")
            return None

        df_local = _ensure_datetime_index(df)
        # Forzar timezone naive -> local timezone display will venir del cliente
        if df_local.index.tzinfo is not None:
            try:
                df_local = df_local.tz_convert(None)
            except Exception:
                pass

        df_ext = extender_df_prediccion(df_local, minutos=extend_minutes, freq="1min")

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

        if "volume" in df_ext.columns:
            fig.add_trace(go.Bar(x=df_ext.index, y=df_ext["volume"], name="Volumen", yaxis="y2", opacity=0.4))

        # Señal en la última vela real
        try:
            last_real_idx = df_local.index[-1]
            if accion:
                color = "#2ecc71" if accion.lower() == "buy" else "#e74c3c"
                fig.add_trace(
                    go.Scatter(
                        x=[last_real_idx],
                        y=[df_local.loc[last_real_idx, "close"]],
                        mode="markers+text",
                        marker=dict(color=color, size=12),
                        text=[accion.upper()],
                        textposition="top center",
                        name="Señal"
                    )
                )
        except Exception:
            pass

        if show_future_shade:
            future_start = df_local.index[-1]
            future_end = df_ext.index[-1]
            fig.add_vrect(x0=future_start, x1=future_end,
                          fillcolor="rgba(100,100,100,0.08)", layer="below", line_width=0,
                          annotation_text="Periodo proyectado", annotation_position="top left")

        fig.update_layout(
            title=f"📈 {activo} — Señal: {accion.upper() if accion else 'N/A'}",
            xaxis=dict(title="Fecha / Hora", type="date", tickformat="%d-%m %H:%M", rangeslider=dict(visible=False), tickangle=-45),
            yaxis=dict(title="Precio"),
            yaxis2=dict(title="Volumen", overlaying="y", side="right", showgrid=False),
            template="plotly_dark",
            margin=dict(l=40, r=20, t=50, b=80),
            hovermode="x unified",
            height=600
        )

        # Forzar rango x completo (desde inicio df hasta fin extendido)
        try:
            fig.update_xaxes(range=[df_ext.index[0], df_ext.index[-1]])
        except Exception:
            pass

        return fig
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="graficar_velas_con_senal")
        return None

def graficar_velas_con_senal_mpf(df: pd.DataFrame, activo: str, accion: Optional[str] = None):
    """
    Versión clásica basada en mplfinance (devuelve (fig, ax) si mpf está disponible).
    Mantengo para compatibilidad con flujos que esperan mplfinance.
    """
    try:
        if mpf is None:
            raise ImportError("mplfinance no instalado")

        if df is None or df.empty:
            log_warning("graficar_velas_con_senal_mpf: DataFrame vacío", archivo="graficos.py", funcion="graficar_velas_con_senal_mpf")
            return None

        df_plot = _ensure_datetime_index(df).copy()

        if "date" in df_plot.columns:
            df_plot.index = pd.to_datetime(df_plot["date"])
        df_plot = df_plot[["open", "high", "low", "close", "volume"]]

        if len(df_plot) < 3:
            log_warning("Datos insuficientes para mplfinance", archivo="graficos.py", funcion="graficar_velas_con_senal_mpf")
            return None

        mc = mpf.make_marketcolors(up="g", down="r", wick="inherit", edge="inherit")
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle="--", facecolor="white")

        apds = []
        if accion == "buy":
            apds.append(mpf.make_addplot(df_plot["close"].iloc[-1], type="scatter", markersize=200, marker="^", color="g"))
        elif accion == "sell":
            apds.append(mpf.make_addplot(df_plot["close"].iloc[-1], type="scatter", markersize=200, marker="v", color="r"))

        fig, ax = mpf.plot(df_plot.tail(100), type="candle", style=s, volume=True, addplot=apds, returnfig=True, figsize=(12, 6))
        return fig, ax
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="graficar_velas_con_senal_mpf")
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
# 💾 Guardado y envío de gráficos
# - guardar_grafico intenta forzar Kaleido para Plotly para mantener apariencia
# - enviar_grafico_telegram hace un único envío (texto + foto)
# ==========================================================
def guardar_grafico(fig: Any, filename: str = "grafico.png", carpeta: str = "graficos") -> Optional[str]:
    """
    Guarda una figura en disco:
    - Si es Plotly: intenta usar fig.write_image(..., engine='kaleido') para un PNG idéntico a la UI.
    - Si es Matplotlib: usa savefig.
    - Si es mplfinance: guarda fig[0].
    Devuelve ruta o None.
    """
    try:
        os.makedirs(carpeta, exist_ok=True)
        path = os.path.join(carpeta, filename)

        # Plotly: forzar kaleido si está disponible
        try:
            if isinstance(fig, go.Figure):
                # asegurar layout compacto
                if hasattr(fig, "update_layout"):
                    fig.update_layout(autosize=True)
                # Intentar write_image con kaleido como engine
                try:
                    fig.write_image(path, scale=2, engine="kaleido")
                    log_info(f"guardar_grafico: Plotly guardado con kaleido en {path}", archivo="graficos.py", funcion="guardar_grafico")
                    return path
                except Exception as e_k:
                    log_warning(f"guardar_grafico: fallo con kaleido: {e_k}", archivo="graficos.py", funcion="guardar_grafico")
                    # fallback a pio.write_image (que también puede usar kaleido)
                    try:
                        pio.write_image(fig, path, scale=1)
                        log_info(f"guardar_grafico: Plotly guardado con pio.write_image en {path}", archivo="graficos.py", funcion="guardar_grafico")
                        return path
                    except Exception as e2:
                        log_warning(f"guardar_grafico: pio.write_image falló: {e2}", archivo="graficos.py", funcion="guardar_grafico")
        except Exception:
            # no crítico
            pass

        # Matplotlib
        try:
            if plt is not None and hasattr(fig, "savefig"):
                fig.savefig(path, dpi=150, bbox_inches="tight")
                log_info(f"guardar_grafico: Matplotlib guardado en {path}", archivo="graficos.py", funcion="guardar_grafico")
                return path
        except Exception:
            pass

        # mplfinance (fig, ax)
        try:
            if mpf is not None and isinstance(fig, tuple) and hasattr(fig[0], "savefig"):
                fig[0].savefig(path, dpi=150, bbox_inches="tight")
                log_info(f"guardar_grafico: mplfinance guardado en {path}", archivo="graficos.py", funcion="guardar_grafico")
                return path
        except Exception:
            pass

        raise ValueError("guardar_grafico: Tipo de figura no soportado o falla en exportación")
    except Exception as e:
        log_error(e, archivo="graficos.py", funcion="guardar_grafico")
        return None

def enviar_grafico_telegram(fig: Any, mensaje: str, filename: str = "grafico.png") -> bool:
    """
    Guarda el gráfico y envía UN único mensaje a Telegram con imagen y texto.
    Intenta usar helpers del proyecto (telegram_alertas), si no hace POST directo a la API.
    """
    try:
        path = guardar_grafico(fig, filename=filename)
        if not path:
            log_warning("enviar_grafico_telegram: no se pudo guardar gráfico", archivo="graficos.py", funcion="enviar_grafico_telegram")
            return False

        # Intento usar telegram_alertas helpers
        try:
            from telegram_alertas import send_telegram_chart, send_telegram_alert
            try:
                send_telegram_chart(path, caption=mensaje)
                log_info("enviar_grafico_telegram: enviado via telegram_alertas.send_telegram_chart", archivo="graficos.py", funcion="enviar_grafico_telegram")
                return True
            except Exception as e:
                log_warning(f"send_telegram_chart fallo: {e}", archivo="graficos.py", funcion="enviar_grafico_telegram")
                # fallback a send_telegram_alert (texto) y luego upload directo
                try:
                    send_telegram_alert(mensaje)
                except Exception:
                    pass
        except Exception:
            # no está disponible telegram_alertas -> fallback HTTP
            pass

        # Fallback HTTP directo usando config_loader
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
                    log_info("enviar_grafico_telegram: enviado via API HTTP", archivo="graficos.py", funcion="enviar_grafico_telegram")
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

# Alias antiguo si hay código que lo usa:
def enviar_imagen_telegram(ruta_imagen: str, mensaje: str = "📊 Gráfico"):
    try:
        if os.path.exists(ruta_imagen):
            # intenta usar telegram_alertas
            try:
                from telegram_alertas import send_telegram_chart
                send_telegram_chart(ruta_imagen, caption=mensaje)
                return True
            except Exception:
                pass
            # fallback a HTTP
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
