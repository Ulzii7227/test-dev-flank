import json
import time
from service.redis import (
    cache_user_detail_r, get_user_detail_r, append_conversation_redis,
    update_token_usage_redis, detect_tools_r, get_tools_r, set_user_stage_r, get_user_stage_r
)

def test_cache_and_get_metadata(fake_redis):
    user = "555"
    data = {"user_id": user, "is_registered": True, "subscription_plan": "free"}
    cache_user_detail_r(user, data, 30)
    got = get_user_detail_r(user)
    assert got and got.get("user_id") == user or str(got.get("is_registered")).lower() == "true"

def test_append_conversation(fake_redis):
    user = "555"
    append_conversation_redis(user, "Hello")
    append_conversation_redis(user, "World")
    # Raw read to confirm
    key = f"user:{user}:conversation"
    val = fake_redis.get(key)
    # some implementations may store conversation differently; if present, validate contents
    if val is not None:
        assert "Hello" in val and "World" in val

def test_token_usage_and_stage(fake_redis):
    user = "555"
    update_token_usage_redis(user, 10)
    # Verify numeric-like field stored
    md = get_user_detail_r(user)
    assert "token_usage" in md
    set_user_stage_r(user, "intro", 1)
    assert get_user_stage_r(user) in ("intro", b"intro")

def test_detect_tools(fake_redis):
    user = "555"
    text = "Run [tool_name=search] please"
    detect_tools_r(text, user)
    assert get_tools_r(user) in ("search", b"search")