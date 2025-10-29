from utils.event_bus import EventBus

def test_bus_publish_subscribe():
    bus = EventBus()
    hits = []
    def h1(x): hits.append(("h1", x["p"]))
    def h2(x): hits.append(("h2", x["p"]))
    bus.subscribe("ev", h1)
    bus.subscribe("ev", h2)
    bus.publish("ev", {"p": 42})
    assert ("h1", 42) in hits and ("h2", 42) in hits