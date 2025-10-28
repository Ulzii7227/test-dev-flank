import time
from collections import OrderedDict

class SeenCache:
    """A tiny in-memory seen cache with TTL to avoid reprocessing duplicates."""
    def __init__(self, max_items: int = 10000, ttl_seconds: int = 3600):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._store = OrderedDict()

    def seen(self, key: str) -> bool:
        now = time.time()
        # purge expired
        to_delete = []
        for k, (ts) in list(self._store.items()):
            if now - ts > self.ttl_seconds:
                to_delete.append(k)
            else:
                break  # because OrderedDict is insertion-ordered
        for k in to_delete:
            self._store.pop(k, None)
        # check
        if key in self._store:
            # Refresh position/time
            self._store.move_to_end(key)
            self._store[key] = now
            return True
        # add
        self._store[key] = now
        if len(self._store) > self.max_items:
            self._store.popitem(last=False)
        return False
