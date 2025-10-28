#!/usr/bin/env python3
"""
Starts ngrok, discovers the https URL, and updates the Meta webhook
callback for your App. Also (optionally) subscribes the App to your WABA.

Use APP_ID|APP_SECRET for /{APP_ID}/subscriptions.
Use System User token only for /{WABA_ID}/subscribed_apps (optional).
"""

import os, time, json, subprocess, sys
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

NGROK_API = "http://127.0.0.1:4040/api/tunnels"
TIMEOUT_S = 25

def ngrok_running():
    try:
        requests.get(NGROK_API, timeout=1)
        return True
    except Exception:
        return False

def start_ngrok(bin_cmd, port):
    if ngrok_running():
        print("ngrok already running.")
        return None
    print(f"Starting ngrok on port {port} ...")
    return subprocess.Popen([bin_cmd, "http", str(port)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)

def get_https_url():
    t0 = time.time()
    while time.time() - t0 < TIMEOUT_S:
        try:
            data = requests.get(NGROK_API, timeout=2).json()
            for t in data.get("tunnels", []):
                url = t.get("public_url", "")
                if url.startswith("https://"):
                    return url
        except Exception:
            pass
        time.sleep(1.2)
    raise RuntimeError("Timed out waiting for ngrok HTTPS tunnel.")

def set_app_subscription(app_id, app_token, callback_url, verify_token, graph_ver="v20.0"):
    url = f"https://graph.facebook.com/{graph_ver}/{app_id}/subscriptions"
    payload = {
        "object": "whatsapp_business_account",
        "callback_url": callback_url,
        "verify_token": verify_token,
        "fields": "messages,message_template_status_update"
    }
    r = requests.post(url, data=payload, params={"access_token": app_token}, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Set webhook failed: {r.status_code} {r.text}")
    return r.json()

def subscribe_app_to_waba(waba_id, sys_user_token, graph_ver="v20.0"):
    url = f"https://graph.facebook.com/{graph_ver}/{waba_id}/subscribed_apps"
    r = requests.post(url, params={"access_token": sys_user_token}, timeout=20)
    if r.status_code not in (200, 201):
        print(f"(Note) subscribe_app_to_wABA: {r.status_code} {r.text}")
        return None
    return r.json()

def main():
    load_dotenv()

    ngrok_bin = os.getenv("NGROK_BIN", "ngrok")
    port = int(os.getenv("PORT", "5000"))
    verify = os.getenv("VERIFY_TOKEN", "mysecret123")
    graph = os.getenv("GRAPH_API_VERSION", "v20.0")
    path = os.getenv("WEBHOOK_PATH", "webhook").lstrip("/")

    app_id = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    sys_user_token = os.getenv("META_APP_ACCESS_TOKEN")
    waba = os.getenv("WABA_ID")

    if not app_id or not app_secret:
        print("ERROR: META_APP_ID and META_APP_SECRET are required.")
        sys.exit(2)

    # Build APP access token for subscriptions endpoint
    app_access_token = f"{app_id}|{app_secret}"

    proc = start_ngrok(ngrok_bin, port)
    try:
        public = get_https_url()
        callback = urljoin(public + "/", path)
        print(f"✅ ngrok: {public}")
        print(f"➡  Callback: {callback}")

        res = set_app_subscription(app_id, app_access_token, callback, verify, graph)
        print(f"✅ Webhook set: {json.dumps(res)}")

        if waba and sys_user_token:
            sub = subscribe_app_to_waba(waba, sys_user_token, graph)
            if sub is not None:
                print(f"✅ Subscribed app to WABA: {json.dumps(sub)}")

        print("Keep this script running (or restart when URL changes). Ctrl+C to exit.")
        while True:
            time.sleep(60)

    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

if __name__ == "__main__":
    main()
