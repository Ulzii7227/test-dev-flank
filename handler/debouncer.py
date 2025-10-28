from datetime import datetime
import threading
from collections import defaultdict
import re

# Store messages per ws_id
message_buffer = defaultdict(list)
is_forwared_buffer = defaultdict(list)
timers = {}

def sequence_message(ws_id, process_message):
    """Called when user stops sending messages."""
    combined = []
    if ws_id in is_forwared_buffer and any(is_forwared_buffer[ws_id]):
        convo, convo_str = [], ''
        for item1, item2 in zip(message_buffer[ws_id], is_forwared_buffer[ws_id]):
            if item2:
                convo.append({"message":item1,"role":"third-forwarded", "timestamp": datetime.utcnow(),})
                convo_str += f"third-forwarded: {item1}\n"
            else:
                convo_str += f"user-forwarded: {item1}\n"
                convo.append({"message":item1,"role":"user-forwarded","timestamp": datetime.utcnow(),})
            
            combined.extend(convo)
    else:
        convo_str = f"user: {' '.join(message_buffer[ws_id])}\n"
        for msg in message_buffer[ws_id]:
            combined.append({"message": msg,"role": "user"})

    is_forwared_buffer[ws_id].clear()  # Clear after processing
    message_buffer[ws_id].clear()  # Clear after processing

    process_message(ws_id, combined, convo_str)

def schedule_processing(ws_id, process_message):
    """Wait 1 second after last message, then process."""
    def delayed():
        sequence_message(ws_id, process_message)
        timers.pop(ws_id, None)

    if ws_id in timers:
        timers[ws_id].cancel()  # Cancel old timer if new message arrived

    timer = threading.Timer(5, delayed)
    timers[ws_id] = timer
    timer.start()

def debouncer_message(ws_id, message, process_message, is_forwarded=False):
    """Simulate receiving a message from a user."""
    is_forwared_buffer[ws_id].append(is_forwarded)
    cleaned = re.sub(r'[ ]+', ' ', message)       # collapse spaces
    cleaned = re.sub(r'\n+', ' ', cleaned)    # collapse multiple newlines to one
    cleaned = cleaned.strip()
    message_buffer[ws_id].append(cleaned)
    schedule_processing(ws_id, process_message)