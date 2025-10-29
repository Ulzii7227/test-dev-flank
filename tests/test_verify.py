from types import SimpleNamespace
from utils.verify import verify_challenge, verify_x_hub_signature
from conftest import sign_body

class _Req:
    def __init__(self, args):
        self.args = args

def test_verify_challenge_success():
    req = _Req({"hub.mode": "subscribe", "hub.verify_token": "TEST_VERIFY_TOKEN", "hub.challenge": "12345"})
    ok, chal = verify_challenge(req, "TEST_VERIFY_TOKEN")
    assert ok is True and chal == "12345"

def test_verify_challenge_fail():
    req = _Req({"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "12345"})
    ok, msg = verify_challenge(req, "TEST_VERIFY_TOKEN")
    assert ok is False and "fail" in msg.lower()

def test_verify_x_hub_signature_success():
    raw = b'{"object":"whatsapp_business_account"}'
    header = sign_body("test_app_secret", raw)
    assert verify_x_hub_signature("test_app_secret", header, raw) is True

def test_verify_x_hub_signature_bad():
    raw = b'{}'
    assert verify_x_hub_signature("test_app_secret", "sha256=deadbeef", raw) is False
    assert verify_x_hub_signature("", "", raw) is False