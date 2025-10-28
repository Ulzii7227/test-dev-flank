import json
import hmac, hashlib
from app import app, APP_SECRET, VERIFY_TOKEN

def test_get_verify_ok():
    with app.test_client() as c:
        rv = c.get('/webhook/whatsapp', query_string={
            'hub.mode': 'subscribe',
            'hub.verify_token': VERIFY_TOKEN,
            'hub.challenge': '12345'
        })
        assert rv.status_code == 200
        assert rv.data == b'12345'

def test_post_signature_ok():
    body = json.dumps({"entry":[]}).encode("utf-8")
    sig = hmac.new(APP_SECRET.encode('utf-8'), body, hashlib.sha256).hexdigest()
    with app.test_client() as c:
        rv = c.post('/webhook/whatsapp', data=body, headers={
            'Content-Type': 'application/json',
            'X-Hub-Signature-256': f'sha256={sig}'
        })
        assert rv.status_code == 200
