import time
from collections import defaultdict, deque
from datetime import datetime

class ConversationSequencer:
    """
    A tiny time-based message aggregator.
    - Messages for the same "conversation key" (e.g., WhatsApp sender) are buffered.
    - When no new message arrives for `buffer_seconds`, the buffered batch is flushed.
    """

    def __init__(self, buffer_seconds=2, max_msgs=100):
        self.buffer_seconds = buffer_seconds
        self.max_msgs = max_msgs
        self._buffers = defaultdict(lambda: deque())
        self._last_ts = {}
        self._names = {}

    def add(self, key, timestamp, text, sender_name=None):
        """Add one message to the buffer for `key`."""
        self._buffers[key].append({
            "ts": int(timestamp),
            "text": text,
            "name": sender_name or key
        })
        self._last_ts[key] = int(time.time())
        if sender_name:
            self._names[key] = sender_name

        if len(self._buffers[key]) >= self.max_msgs:
            return self.flush(key)
        return None

    def try_flush(self, key):
        """Flush if idle for buffer_seconds."""
        if key not in self._last_ts:
            return None
        if int(time.time()) - self._last_ts[key] >= self.buffer_seconds:
            return self.flush(key)
        return None

    def flush(self, key):
        """
        Force-flush buffer for `key`.
        Returns (wa_id, sender_name, transcript, duration).
        """
        if key not in self._buffers or not self._buffers[key]:
            return None

        items = list(self._buffers[key])
        self._buffers[key].clear()
        self._last_ts.pop(key, None)

        items.sort(key=lambda x: x["ts"])
        sender_name = items[0]["name"]

        start_ts = items[0]["ts"]
        end_ts = items[-1]["ts"]
        duration = max(0, end_ts - start_ts)

        transcript = [
            f"[{datetime.fromtimestamp(m['ts']).strftime('%Y-%m-%d %H:%M:%S')} | {m['ts']}] {m['name']}: {m['text']}"
            for m in items
        ]

        return key, sender_name, transcript, duration

    def keys(self):
        return list(self._buffers.keys())
