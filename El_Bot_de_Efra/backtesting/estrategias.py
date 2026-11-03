class EstrategiaBase:
    def __init__(self, nombre):
        self.nombre = nombre

    def aplicar(self, df):
        raise NotImplementedError("Debes implementar el método aplicar()")


class EstrategiaCruceMedias(EstrategiaBase):
    def __init__(self):
        super().__init__("Cruce de medias")

    def aplicar(self, df):
        df = df.copy()
        df['signal'] = 0
        df['signal'] = (df['sma_20'] > df['sma_50']).astype(int)
        df['signal'] = df['signal'].diff().fillna(0)
        return df


class EstrategiaRsiMacd(EstrategiaBase):
    def __init__(self):
        super().__init__("RSI + MACD")

    def aplicar(self, df):
        df = df.copy()
        df['signal'] = 0
        df.loc[(df['rsi'] < 30) & (df['macd'] > df['macd_signal']), 'signal'] = 1
        df.loc[(df['rsi'] > 70) & (df['macd'] < df['macd_signal']), 'signal'] = -1
        return df


class EstrategiaVolatilidad(EstrategiaBase):
    def __init__(self):
        super().__init__("Volatilidad")

    def aplicar(self, df):
        df = df.copy()
        df['signal'] = 0
        volatilidad = df['high'] - df['low']
        umbral = volatilidad.rolling(window=10).mean()
        df['signal'] = (volatilidad > umbral).astype(int).diff().fillna(0)
        return df


class GestorEstrategias:
    def __init__(self, estrategias):
        self.estrategias = estrategias

    def aplicar_todas(self, df):
        señales = []
        for estrategia in self.estrategias:
            df_resultado = estrategia.aplicar(df.copy())
            señal = df_resultado['signal'].iloc[-1]
            señales.append((estrategia.nombre, señal))

        señales_filtradas = [s for _, s in señales if s != 0]
        señal_final = 0
        if señales_filtradas:
            señal_final = max(set(señales_filtradas), key=señales_filtradas.count)

        return señal_final, señales


# Función retrocompatible para app.py
def aplicar_estrategia_tecnica(df):
    gestor = GestorEstrategias([
        EstrategiaCruceMedias(),
        EstrategiaRsiMacd(),
        EstrategiaVolatilidad()
    ])
    señal_final, _ = gestor.aplicar_todas(df)
    return señal_final
