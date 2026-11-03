from __future__ import annotations

import os
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .chatbot import PosterSSTChatbot
from .config import OUTPUT_DIR, ensure_directories
from .excel_exporter import build_workbook
from .seed_data import default_state
from .storage import load_state, save_state


ensure_directories()
app = FastAPI(title="Bot Poster SST WhatsApp", version="1.0")
app.mount("/files", StaticFiles(directory=OUTPUT_DIR), name="files")


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "efra_sst_bot")
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == verify_token:
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("Token invalido", status_code=403)


@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    message, phone = _extract_cloud_api_message(payload)
    if not message:
        return {"status": "ignored"}
    owner_phone = os.getenv("BOT_SST_OWNER_WHATSAPP", "573186146023")
    is_owner = _same_phone(phone, owner_phone)

    state_path = Path("data/poster_sst_bot") / f"whatsapp_{phone}.json"
    state = load_state(state_path) if state_path.exists() else default_state()
    bot = PosterSSTChatbot(state)

    lower = message.lower().strip()
    if not is_owner and os.getenv("BOT_SST_RESTRICT_TO_OWNER", "0") == "1":
        reply = "Este bot SST esta configurado solo para el numero autorizado."
    elif lower.startswith("poster\n"):
        updated = bot.update_poster_from_text(message.partition("\n")[2])
        reply = bot.with_next_step(f"Actualice {updated} campos del poster.")
    elif lower.startswith("hallazgo\n"):
        added = bot.add_record_from_text("hallazgo", message.partition("\n")[2])
        reply = bot.with_next_step("Hallazgo registrado." if added else "No pude leer el hallazgo. Usa CAMPO: valor.")
    elif lower.startswith("accion\n") or lower.startswith("acción\n"):
        added = bot.add_record_from_text("accion", message.partition("\n")[2])
        reply = bot.with_next_step("Accion registrada." if added else "No pude leer la accion. Usa CAMPO: valor.")
    elif lower.startswith("5 por que\n") or lower.startswith("5 por qué\n"):
        added = bot.add_record_from_text("5_por_que", message.partition("\n")[2])
        reply = bot.with_next_step("Analisis 5 Por Que registrado." if added else "No pude leer el analisis. Usa CAMPO: valor.")
    elif "export" in lower or "excel" in lower:
        output = build_workbook(state)
        public_base_url = os.getenv("PUBLIC_FILE_BASE_URL", "").rstrip("/")
        if public_base_url:
            reply = f"Excel generado: {public_base_url}/{output.name}"
        else:
            base_url = str(request.base_url).rstrip("/")
            reply = (
                f"Excel generado: {base_url}/files/{output.name}\n"
                "Para WhatsApp real, publica este servidor con HTTPS "
                "y configura PUBLIC_FILE_BASE_URL."
            )
    else:
        reply = bot.handle(message)

    save_state(state, state_path)
    _send_cloud_api_message(phone, reply)
    return {"status": "ok", "reply": reply}


def _extract_cloud_api_message(payload: dict) -> tuple[str, str]:
    try:
        entry = payload["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]
        phone = message["from"]
        text = message.get("text", {}).get("body", "")
        return text, phone
    except (KeyError, IndexError, TypeError):
        return "", ""


def _send_cloud_api_message(phone: str, text: str) -> None:
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id or not phone:
        return
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text[:4000]},
    }
    requests.post(url, headers=headers, json=payload, timeout=15)


def _same_phone(incoming: str, expected: str) -> bool:
    clean_incoming = "".join(ch for ch in incoming if ch.isdigit())
    clean_expected = "".join(ch for ch in expected if ch.isdigit())
    return clean_incoming.endswith(clean_expected[-10:])
