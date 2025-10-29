import os
import logging
from flask import Flask, request, abort, jsonify
from dotenv import load_dotenv

# ✅ import from root-level files (not utils./handler.)
from verify import verify_challenge, verify_x_hub_signature
from event_bus import EventBus
from idempotency import SeenCache
from mongo_client import MongoDB

# Optional: use your WhatsApp sender directly for a lightweight fallback reply
from send_message import send_text_reply

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-webhook")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")

app = Flask(__name__)

# --- Mongo init (non-fatal if absent) ---
try:
    MongoDB.initialize()
    logger.info("Mongo connected & indexes ensured.")
except Exception as e:
    logger.exception("Mongo init failed: %s", e)

# --- Event system ---
bus = EventBus()
seen = SeenCache(max_items=5000, ttl_seconds=60 * 60)  # 1 hour TTL

def _try_receive_message(payload: dict) -> bool:
    """
    Try to route through your rich handler if it imports cleanly.
    Return True if handled; False to let the fallback handle it.
    """
    try:
        # Lazy import so missing deps don't crash cold start
        from receive_message import on_message  # type: ignore
        on_message(payload)
        return True
    except Exception as e:
        logger.warning("receive_message handler unavailable: %s", e)
        return False

def _fallback_reply(msg: dict, meta: dict) -> None:
    """
    Minimal, safe echo reply using your WhatsApp sender.
    Keeps the webhook functional while you wire up service/* and LLM.
    """
    ws_id = msg.get("from")
    typ = msg.get("type")
    if typ == "text":
        body = (msg.get("text", {}) or {}).get("body", "").strip()
        reply = body or "👋 Hi! Your message was received."
    else:
        reply = f"Received {typ} message. Send text to chat."
    try:
        send_text_reply(ws_id, reply)
    except Exception as e:
        logger.exception("Failed to send reply: %s", e)

# Subscribe a lightweight event consumer that prefers your rich handler
def _bus_on_message(evt: dict):
    if not _try_receive_message(evt):
        _fallback_reply(evt.get("message", {}), evt.get("metadata", {}))

bus.subscribe("message", _bus_on_message)

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
    # Meta requires signature verification on POSTs
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
        # WhatsApp payload: entry -> changes -> value -> messages[]
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
        # Return 200 so Meta doesn't hammer retries while you iterate
        return jsonify({"status": "ignored", "error": str(e)}), 200

    # Always 200 within 10s per Meta requirement
    return jsonify({"status": "ok"}), 200
