# api/index.py
import os
from flask import Flask, request, abort

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")

@app.get("/webhook/whatsapp")
def whatsapp_verify():
    token = request.args.get("hub.verify_token")
    if token != VERIFY_TOKEN:
        return abort(403)
    return request.args.get("hub.challenge", "")

@app.post("/webhook/whatsapp")
def whatsapp_receive():
    # handle messages here
    return "OK"
