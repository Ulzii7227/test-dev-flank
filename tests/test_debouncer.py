import time
from handler.debouncer import debouncer_message, message_buffer, is_forwared_buffer

def test_debouncer_accumulates_and_cleans():
    events = []
    def process(ws_id, text, is_forwarded):
        events.append((ws_id, text))
    # Send 2 quick messages
    debouncer_message("u1", "hello", process, False)
    debouncer_message("u1", "world", process, False)
    time.sleep(6.0)  # wait for timer
    # Should have combined messages and invoked once
    assert len(events) == 1
    payload = events[0][1]
    msgs = [d.get("message") for d in payload]
    assert "hello" in msgs and "world" in msgs