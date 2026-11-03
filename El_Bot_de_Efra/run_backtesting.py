# run_backtesting.py

import pandas as pd
from backtesting.backtesting import realizar_backtesting, calcular_metricas, graficar_equity_curve
from backtesting.estrategias import (
    EstrategiaCruceMedias,
    EstrategiaRsiMacd,
    EstrategiaVolatilidad,
    GestorEstrategias
)

def cargar_datos(ruta_csv):
    """
    Carga los datos históricos desde un archivo CSV.
    """
    try:
        df = pd.read_csv(ruta_csv, parse_dates=True, index_col=0)
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"❌ Error cargando datos: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    ruta_csv = "csv/ultimo_df.csv"
    df = cargar_datos(ruta_csv)

    if df.empty:
        print("⚠️ No se pudo cargar el dataframe.")
        exit()

    # Configurar las estrategias a aplicar
    estrategias = [
        EstrategiaCruceMedias(),
        EstrategiaRsiMacd(),
        EstrategiaVolatilidad()
    ]

    gestor = GestorEstrategias(estrategias)

    # Ejecutar el backtesting con las estrategias
    resultado, señales = realizar_backtesting(df, gestor)

    # Calcular métricas de performance
    metricas = calcular_metricas(resultado)
    print("📊 Métricas del Backtesting:")
    for k, v in metricas.items():
        print(f"  {k}: {v}")

    # Graficar equity curve
    graficar_equity_curve(resultado)
