import os
import logging
from flask import Flask, request, abort, jsonify
from dotenv import load_dotenv

# ✅ Import from utils (correct folder)
from utils.verify import verify_challenge, verify_x_hub_signature
from utils.event_bus import EventBus
from utils.idempotency import SeenCache
from utils.mongo_client import MongoDB

# ✅ Import from handler (correct folder)
from handler.send_message import send_text_reply

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-webhook")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")

app = Flask(__name__)

# --- Mongo init (non-fatal if fails) ---
try:
    MongoDB.initialize()
    logger.info("Mongo connected & indexes ensured.")
except Exception as e:
    logger.exception("Mongo init failed: %s", e)

# --- Event system ---
bus = EventBus()
seen = SeenCache(max_items=5000, ttl_seconds=60 * 60)

# Try lazy-import rich handler to avoid cold start crash
def _try_receive_message(evt):
    try:
        from handler.receive_message import on_message
        on_message(evt)
        return True
    except Exception as e:
        logger.warning("receive_message not loaded: %s", e)
        return False

def _fallback_reply(msg, meta):
    ws_id = msg.get("from")
    typ = msg.get("type")
    if typ == "text":
        body = msg.get("text", {}).get("body", "")
        reply = body or "👋 Hello! I received your message."
    else:
        reply = f"Got {typ} message."
    try:
        send_text_reply(ws_id, reply)
    except Exception as e:
        logger.exception("Failed to send reply: %s", e)

def _bus_on_message(evt):
    if not _try_receive_message(evt):
        _fallback_reply(evt.get("message", {}), evt.get("metadata", {}))

bus.subscribe("message", _bus_on_message)

@app.get("/")
def home():
    return "Flank BE running ✅", 200

@app.get("/health")
def health():
    return jsonify(status="ok"), 200


# --- Routes ---
@app.get("/webhook/whatsapp")
def whatsapp_verify():
    ok, challenge_or_err = verify_challenge(request, VERIFY_TOKEN)
    if not ok:
        logger.warning("Verification failed: %s", challenge_or_err)
        abort(403, challenge_or_err)
    return challenge_or_err, 200


@app.post("/webhook/whatsapp")
def whatsapp_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_x_hub_signature(APP_SECRET, sig, raw):
        logger.warning("Invalid signature")
        abort(403, "Invalid signature")

    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        logger.exception("Invalid JSON: %s", e)
        abort(400, "Invalid JSON")

    try:
        for entry in (payload.get("entry") or []):
            for change in (entry.get("changes") or []):
                value = change.get("value") or {}
                for msg in (value.get("messages") or []):
                    msg_id = msg.get("id")
                    if msg_id and seen.seen(msg_id):
                        logger.info("Skipping duplicate message id=%s", msg_id)
                        continue
                    bus.publish("message", {"message": msg, "metadata": value.get("metadata", {})})
    except Exception as e:
        logger.exception("Error processing webhook: %s", e)
        return jsonify({"status": "ignored", "error": str(e)}), 200

    return jsonify({"status": "ok"}), 200
