# WhatsApp Webhook: Event-Driven Flask Starter

A minimal, production-ready-ish Flask webhook for **WhatsApp Cloud API** at `/webhook/whatsapp` with:

- GET verification (`hub.mode`, `hub.verify_token`, `hub.challenge`)
- POST signature verification (`X-Hub-Signature-256` using `APP_SECRET`)
- Event dispatching for `message` and `status` events
- Simple idempotency guard
- Example text echo reply (optional) via WhatsApp Cloud API

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env  # then edit values
flask --app app run --port ${PORT:-3001}
ngrok http 3001
```

Expose tunneling (e.g., ngrok) and paste your public URL in the **Meta Developer** "Webhook URL" for WhatsApp, with the **Verify Token** you set in `.env`.

## Verify Endpoint (GET)

Meta will call with query params:
- `hub.mode=subscribe`
- `hub.verify_token=<your VERIFY_TOKEN>`
- `hub.challenge=<random string>`

Your app returns the `hub.challenge` on success.

## Incoming Messages (POST)

The app verifies `X-Hub-Signature-256` header using your `APP_SECRET`. It then dispatches events:

- `message` payloads for new messages
- `status` payloads for delivery/read status updates

### Example curl

```bash
curl -X POST http://localhost:5000/webhook/whatsapp   -H 'Content-Type: application/json'   -H 'X-Hub-Signature-256=sha256=deadbeef'   -d @tests/sample_webhook.json
```

(Replace signature with a real one if testing verification.)

## Replying

Uncomment the call in `handlers/message_handlers.py` to reply using the WhatsApp Cloud API.
Set `WHATSAPP_TOKEN` and `PHONE_NUMBER_ID` in `.env`.

## Tests

```bash
python -m pytest -q
```

## Files

- `app.py` – Flask app and webhook routes
- `handlers/message_handlers.py` – message & status handlers (+ optional reply)
- `utils/event_bus.py` – tiny sync pub/sub
- `utils/verify.py` – signature verification + verification GET handler
- `utils/idempotency.py` – in-memory seen cache
```