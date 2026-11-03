from trading_bot import TradingBot

bot = TradingBot(timeframe='1m')
bot.agregar_simbolo('BTC-USD')
bot.agregar_simbolo('GC=F')
bot.iniciar()
