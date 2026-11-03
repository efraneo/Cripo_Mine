import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ==============================================
# 📊 Importar estrategias técnicas modulares
# ==============================================
from backtesting.estrategias import (
    EstrategiaCruceMedias,
    EstrategiaRsiMacd,
    EstrategiaVolatilidad,
    GestorEstrategias
)

# ==============================================
# 🔁 Simulación de operaciones con estrategias técnicas
# ==============================================
def realizar_backtesting(df, capital_inicial=1000, verbose=False):
    df = df.copy()
    df.sort_index(inplace=True)

    gestor = GestorEstrategias([
        EstrategiaCruceMedias(),
        EstrategiaRsiMacd(),
        EstrategiaVolatilidad()
    ])

    df['signal'] = 0
    df['retorno'] = 0.0
    df['capital'] = capital_inicial
    df['orden'] = ""

    posicion_abierta = False
    entrada = 0

    for i in range(1, len(df)):
        fila = df.iloc[:i+1]
        señal, _ = gestor.aplicar_todas(fila)
        precio_actual = df.iloc[i]['close']

        if señal > 0 and not posicion_abierta:
            entrada = precio_actual
            posicion_abierta = True
            df.at[df.index[i], 'orden'] = 'BUY'
            if verbose:
                print(f"[{df.index[i]}] COMPRA en {precio_actual:.2f}")

        elif señal < 0 and posicion_abierta:
            retorno = (precio_actual - entrada) / entrada
            df.at[df.index[i], 'retorno'] = retorno
            df.at[df.index[i], 'orden'] = 'SELL'
            posicion_abierta = False
            if verbose:
                print(f"[{df.index[i]}] VENTA en {precio_actual:.2f} | Retorno: {retorno:.2%}")

        df.at[df.index[i], 'capital'] = df.iloc[i - 1]['capital'] * (1 + df.iloc[i]['retorno'])

    return df

# ==============================================
# 📈 Métricas de rendimiento
# ==============================================
def calcular_metricas(df):
    df = df.copy()
    retornos = df['retorno'][df['retorno'] != 0]

    total_trades = len(retornos)
    aciertos = sum(retornos > 0)
    tasa_acierto = aciertos / total_trades if total_trades > 0 else 0

    retorno_total = df['capital'].iloc[-1] / df['capital'].iloc[0] - 1
    max_drawdown = (df['capital'] / df['capital'].cummax() - 1).min()
    sharpe_ratio = (
        (retornos.mean() / retornos.std()) * np.sqrt(252)
        if retornos.std() != 0 and len(retornos) > 1 else 0
    )

    return {
        "Total Trades": total_trades,
        "Tasa de Acierto": f"{tasa_acierto:.2%}",
        "Retorno Total": f"{retorno_total:.2%}",
        "Máx Drawdown": f"{max_drawdown:.2%}",
        "Sharpe Ratio": f"{sharpe_ratio:.2f}"
    }

# ==============================================
# 📊 Visualización de evolución del capital
# ==============================================
def graficar_equity_curve(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['capital'],
        name="Capital acumulado",
        line=dict(color='green')
    ))
    fig.update_layout(
        title="💰 Evolución del capital",
        xaxis_title="Fecha",
        yaxis_title="Capital (USDT)"
    )
    return fig
