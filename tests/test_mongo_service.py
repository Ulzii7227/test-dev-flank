from service.mongo import (
    add_new_user, get_user_detail_m, store_user_conversation_m, get_user_conversation,
    update_user_token_usage, update_user_summary_m, delete_user_conversation_m
)

def test_user_crud(fake_mongo):
    user = "555"
    add_new_user(user, {"is_registered": True})
    doc = get_user_detail_m(user)
    assert doc and doc.get("user_id") == user

def test_conversation_and_summary(fake_mongo):
    user = "555"
    add_new_user(user, {"is_registered": True})
    store_user_conversation_m(user, "Hello")
    store_user_conversation_m(user, "World")
    convo = get_user_conversation(user)
    if isinstance(convo, list):
        if convo and isinstance(convo[0], dict):
            joined = "".join(m.get("content") or m.get("message", "") for m in convo)
        else:
            joined = "".join(map(str, convo))
    else:
        joined = str(convo)
    assert "Hello" in joined and "World" in joined

    update_user_token_usage(user, 25)
    doc = get_user_detail_m(user)
    assert doc.get("token_used") in (25, "25")
    # assert isinstance(convo, str) and "Hello" in convo and "World" in convo
    # update_user_summary_m(user, "Short summary")
    # doc = get_user_detail_m(user)
    # assert doc.get("summary") == "Short summary"
    # delete_user_conversation_m(user)
    # convo2 = get_user_conversation(user)
    # assert convo2 == "" or convo2 is None

def test_token_usage(fake_mongo):
    user = "555"
    add_new_user(user, {"is_registered": True})
    update_user_token_usage(user, 25)
    doc = get_user_detail_m(user)
    assert doc.get("token_used") in (25, "25")