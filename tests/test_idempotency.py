import time
from utils.idempotency import SeenCache

def test_seen_cache_basic():
    c = SeenCache(max_items=2, ttl_seconds=1)
    assert c.seen("a") is False    # first time, not seen
    assert c.seen("a") is True     # second time, seen
    time.sleep(1.1)
    assert c.seen("a") is False    # expired

def test_seen_cache_eviction():
    c = SeenCache(max_items=2, ttl_seconds=10)
    # First sightings: all return False
    assert c.seen("a") is False
    assert c.seen("b") is False
    assert c.seen("c") is False  # triggers eviction

    # After capacity exceeded, at least one old key should have been evicted
    evicted_count = sum(1 for k in ("a", "b") if c.seen(k) is False)
    assert evicted_count >= 1  # at least one eviction occurred

    # Seen keys should later return True if not evicted
    for key in ("a", "b", "c"):
        _ = c.seen(key)  # record presence again
        assert c.seen(key) is True