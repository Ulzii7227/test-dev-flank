from typing import Callable, Dict, List, Any
import logging

logger = logging.getLogger("event-bus")

class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event: str, handler: Callable[[Any], None]):
        self._subs.setdefault(event, []).append(handler)
        logger.info("Subscribed handler %s to event '%s'", getattr(handler, '__name__', repr(handler)), event)

    def publish(self, event: str, payload: Any):
        handlers = self._subs.get(event, [])
        logger.info("Dispatching event '%s' to %d handler(s)", event, len(handlers))
        for h in handlers:
            try:
                h(payload)
            except Exception as e:
                logger.exception("Handler %s failed: %s", getattr(h, '__name__', repr(h)), e)
