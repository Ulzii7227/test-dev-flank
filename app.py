import os
import logging
from flask import Flask, request, abort, jsonify
from dotenv import load_dotenv

from handlers.meta_store_handler import pull_meta_store, r_
from utils.verify import verify_challenge, verify_x_hub_signature
from utils.event_bus import EventBus
from utils.idempotency import SeenCache
from handlers.message_handlers import on_message, on_status
from utils.mongo_client import init_mongo


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-webhook")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")
PORT = int(os.getenv("PORT", "3001"))

app = Flask(__name__)


try:
    init_mongo()
    logger.info("Mongo connected & indexes ensured.")
except Exception as e:
    logger.exception("Mongo init failed: %s", e)


# --- Event system
bus = EventBus()
bus.subscribe("message", on_message)
bus.subscribe("status", on_status)

# Idempotency guard for message IDs
seen = SeenCache(max_items=5000, ttl_seconds=60 * 60)  # 1 hour TTL

@app.get("/webhook/whatsapp")
def whatsapp_verify():
    ok, challenge_or_err = verify_challenge(request, VERIFY_TOKEN)
    if not ok:
        logger.warning("Verification failed: %s", challenge_or_err)
        abort(403, challenge_or_err)
    return challenge_or_err, 200

@app.post("/webhook/whatsapp")
def whatsapp_webhook():
    # Read raw body first for signature verification
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

    # WhatsApp structure: entry -> changes -> value
    try:

        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
              
                # Status updates
                # statuses = value.get("statuses", [])
                # for st in statuses:
                #     bus.publish("status", st)

                # New messages
                messages = value.get("messages", [])

                # Pull the metadata from db to redis if not present
                contacts = value.get("contacts", [])
                if contacts:
                    wa_id = contacts[0].get("wa_id")
                    if wa_id:
                        key = f"user:{wa_id}:metadata"

                        # Check if metadata exists in Redis
                        if not r_.exists(key):
                            pull_meta_store(wa_id)  # pull from Mongo if not cached
                        else:
                            logger.info("Metadata for %s already in Redis", wa_id)
                    else:
                        logger.warning("No wa_id found in first contact")
                else:
                    logger.warning("No contacts in webhook payload")

                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id and seen.seen(msg_id):
                        logger.info("Skipping duplicate message id=%s", msg_id)
                        continue
                    bus.publish("message", {"message": msg, "metadata": value.get("metadata", {})})
                    
    except Exception as e:
        logger.exception("Error processing webhook: %s", e)
        # Still respond 200 so Meta doesn't retry due to server error endlessly,
        # but you might choose 5xx to trigger retry while you fix issues.
        return jsonify({"status": "ignored", "error": str(e)}), 200

    # Always 200 within 10s per Meta's requirement
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
