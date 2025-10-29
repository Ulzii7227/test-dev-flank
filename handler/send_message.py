import os
import logging
import requests
import re

logger = logging.getLogger("handlers")

# ---------------- WhatsApp API config ----------------
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_URL = "https://graph.facebook.com/v23.0"

def clean_text(text: str) -> str:
    clean = re.sub(r'<bot>\s*', '', re.sub(r'\[tool_name=[^\]]*\]\s*', '', text))
    return clean.strip()

def send_text_reply(to: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")

    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    text = clean_text(text)
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    if r.status_code >= 400:
        raise RuntimeError(f"Graph reply error {r.status_code}: {r.text}")
    return r.json()
