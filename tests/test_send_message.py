import os
import importlib
import pytest
from handler import send_message as sm

def test_send_message_happy(mock_graph_post, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pnid")
    importlib.reload(sm)
    result = sm.send_text_reply("555", "Hello")
    assert result.get("id") == "wamid.mocked"

def test_send_message_missing_env(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("PHONE_NUMBER_ID", raising=False)
    with pytest.raises(RuntimeError):
        sm.send_text_reply("555", "Hello")