# test_analisis.py
# =====================================================
# Script rápido para probar analizar_activo en consola
# =====================================================

from trading_bot import TradingBot

def main():
    bot = TradingBot()
    symbol = "BTCUSDT"   # 👈 puedes cambiarlo a ETHUSDT, BNBUSDT, etc.

    print(f"\n🔎 Analizando activo: {symbol}")
    resultado = bot.analizar_activo(activo=symbol)

    if not resultado:
        print("❌ No se pudo analizar el activo. Revisa logs.")
        return

    print("\n=== RESULTADO CRUDO ===")
    for k, v in resultado.items():
        if k != "df":  # no imprimir dataframe completo
            print(f"{k}: {v}")

    combinado = resultado.get("combinado", {})
    print("\n=== SEÑAL COMBINADA ===")
    print(f"Señal final: {combinado.get('senal')}")
    print(f"Confianza:   {combinado.get('confianza'):.2%}")
    print(f"Score:       {combinado.get('score'):.3f}")
    print("Resumen metodologías:")
    for linea in combinado.get("resumen", []):
        print(" •", linea)

if __name__ == "__main__":
    main()
