Set-Location "C:\software_phyton\BOT_SST"
python -m uvicorn poster_sst_bot.whatsapp_webhook:app --host 0.0.0.0 --port 8001
