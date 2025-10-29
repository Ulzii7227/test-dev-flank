import os
import sys, types, uuid
from unittest.mock import patch
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 1) Stub `openai` so imports in handler.summarize_user work early
class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content): self.message = _Msg(content)
class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]
class _Completions:
    def create(self, **kwargs): return _Resp("Mocked assistant reply")
class _Chat:
    def __init__(self): self.completions = _Completions()
class _OpenAIStub:
    def __init__(self): self.chat = _Chat()
sys.modules.setdefault("openai", _OpenAIStub())

# 2) Stub `pymongo` *with its `database` submodule* using mongomock
import mongomock

# Create a proper module object for `pymongo`
pymongo_mod = types.ModuleType("pymongo")
pymongo_mod.MongoClient = mongomock.MongoClient

# Create a proper submodule `pymongo.database` that exposes `Database`
from mongomock.database import Database as _MMDatabase
database_mod = types.ModuleType("pymongo.database")
database_mod.Database = _MMDatabase

# Wire them into sys.modules so 'import pymongo' and 'from pymongo.database import Database' both work
pymongo_mod.database = database_mod
sys.modules["pymongo"] = pymongo_mod
sys.modules["pymongo.database"] = database_mod

bson_mod = types.ModuleType("bson")

class ObjectId:
    """Minimal stand-in for bson.ObjectId used by tests."""
    def __init__(self, oid: str | None = None):
        # 24 hex chars typical of BSON ObjectId; no validation needed for tests
        self._oid = (oid or uuid.uuid4().hex)[:24]
    def __str__(self): return self._oid
    def __repr__(self): return f"ObjectId('{self._oid}')"
    def __eq__(self, other): return str(self) == str(other)

bson_mod.ObjectId = ObjectId
sys.modules.setdefault("bson", bson_mod)
import fakeredis
rc_mod = types.ModuleType("utils.redis_client")

# one shared client across the whole process
_SHARED_CLIENT = fakeredis.FakeStrictRedis(decode_responses=True)

class RedisClient:
    def __init__(self):
        self.client = _SHARED_CLIENT
    def get_client(self):
        return self.client

rc_mod.RedisClient = RedisClient
sys.modules["utils.redis_client"] = rc_mod

import json
import pytest

# ---------- Environment for tests ----------
@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # Safe demo secrets for test runs
    monkeypatch.setenv("VERIFY_TOKEN", "TEST_VERIFY_TOKEN")
    monkeypatch.setenv("APP_SECRET", "test_app_secret")
    monkeypatch.setenv("WHATSAPP_TOKEN", "test_wa_token")
    monkeypatch.setenv("PHONE_NUMBER_ID", "1234567890")
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB", "flank_test_db")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("REDIS_DECODE_RESPONSES", "1")
    yield

# ---------- Fake Redis client wired into RedisClient ----------
@pytest.fixture()
def fake_redis(monkeypatch):
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    # Patch RedisClient().get_client() to return fakeredis
    from utils import redis_client as rc

    class DummyRedisClient(rc.RedisClient):
        def _connect(self):
            self.client = r

    monkeypatch.setattr(rc, "RedisClient", DummyRedisClient)
    return rc.RedisClient().get_client()

# ---------- Fake Mongo wired into MongoDB ----------
@pytest.fixture()
def fake_mongo(monkeypatch):
    import utils.mongo_client as mc
    client = mongomock.MongoClient()
    db = client[os.getenv("MONGO_DB", "flank_test_db")]
    monkeypatch.setattr(mc.MongoDB, "get_db", classmethod(lambda cls: db))
    return db

# ---------- Fake WhatsApp Graph POST ----------
@pytest.fixture()
def mock_graph_post(monkeypatch):
    import requests

    class DummyResp:
        status_code = 200
        def json(self):
            return {"id": "wamid.mocked"}

    def _post(url, headers=None, json=None, timeout=None):
        return DummyResp()

    monkeypatch.setattr(requests, "post", _post)
    return _post

# ---------- Fake OpenAI Chat Completions ----------
@pytest.fixture()
def mock_openai(monkeypatch):
    # Build a minimal stub matching openai.chat.completions.create(...).choices[0].message.content
    class _Msg: 
        def __init__(self, content): self.content = content
    class _Choice:
        def __init__(self, content): self.message = _Msg(content)
    class _Resp:
        def __init__(self, content): self.choices = [_Choice(content)]
    class _Completions:
        def create(self, **kwargs):
            return _Resp("Mocked assistant reply")
    class _Chat:
        def __init__(self): self.completions = _Completions()
    class _OpenAI:
        def __init__(self): self.chat = _Chat()

    import handler
    # If the code imports as `import openai`, patch that module
    monkeypatch.setitem(__import__("sys").modules, "openai", _OpenAI())
    return _OpenAI()

# ---------- Helper: sign body for webhook headers ----------
import hmac, hashlib
def sign_body(app_secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()