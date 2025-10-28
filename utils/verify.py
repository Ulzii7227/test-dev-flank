import hmac
import hashlib
from flask import Request

def verify_challenge(req: Request, verify_token: str):
    mode = req.args.get("hub.mode")
    token = req.args.get("hub.verify_token")
    challenge = req.args.get("hub.challenge")
    if mode == "subscribe" and token and challenge and token == verify_token:
        return True, challenge
    return False, "Verification failed"

def verify_x_hub_signature(app_secret: str, header_signature: str, raw_body: bytes) -> bool:
    """Validate X-Hub-Signature-256: format 'sha256=<hexdigest>'"""
    if not app_secret or not header_signature or not header_signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
    provided = header_signature.split("=", 1)[1]
    # constant-time compare
    return hmac.compare_digest(expected, provided)
