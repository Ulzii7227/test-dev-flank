import os
import logging
import requests
import time
import threading
from handlers.llm import (
    ask_llm,
    build_messages,
    get_stage_for_user,
    advance_stage,
    SYSTEM_PROMPT,
    STAGE_PROMPTS,
)
from sequencer import ConversationSequencer
from handlers.meta_store_handler import get_remaining_tokens, increment_tokens, get_user_metadata


logger = logging.getLogger("handlers")

# ---------------- WhatsApp API config ----------------
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_URL = "https://graph.facebook.com/v23.0"

# ---------------- In-memory stores ----------------
user_history = {}              # user_id -> list of {"speaker":..., "text":...}
narrative_mode = {}            # user_id -> collecting forwarded messages?
last_message_time = {}         # user_id -> timestamp of last msg
user_stage_turns = {}          # user_id -> turns used in current stage
speaker_confirmation = {}      # user_id -> {"waiting": bool, "text": str}
last_forwarded_speaker = {}    # user_id -> "user" or "friend"

BUFFER_TIMEOUT = 60
sequencer = ConversationSequencer(buffer_seconds=2, max_msgs=100)

# ---------------- Stage multi-turn config ----------------
stage_turns_required = {
    "Greeting": 1,
    "Validation": 1,
    "Reflection": 2,
    "Tools": 1,
    "Next Steps": 1
}

# ---------------- Utility functions ----------------
def safe_advance_stage(user_id, current_stage):
    if get_stage_for_user(user_id) == current_stage:
        advance_stage(user_id)
    user_stage_turns[user_id] = 0


def send_text_reply(to: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")

    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    if r.status_code >= 400:
        raise RuntimeError(f"Graph reply error {r.status_code}: {r.text}")
    return r.json()


# ---------------- Core message handler ----------------
def on_message(payload: dict):
    """Main handler for incoming WhatsApp messages."""
    msg = payload.get("message", {})
    user_id = msg.get("from")
    type_ = msg.get("type")
    text = msg.get("text", {}).get("body", "").strip() if type_ == "text" else None

    text = None
    if type_ == "text":
        text = msg.get("text", {}).get("body")
    elif type_ == "image":
        raise RuntimeError("Image handling not allowed yet")
    elif type_ == "audio":
        raise RuntimeError("Audio handling not allowed yet")
    elif type_ == "video":
        raise RuntimeError("Video handling not allowed yet")
    else:
        logger.warning("Unhandled message type: %s", type_)
        return
    
    token_left = get_remaining_tokens(wa_id=user_id)
    logger.info("User %s has %s tokens left", user_id, token_left)

    end_conversation = False
    if token_left < 100:
        end_conversation = True 

    last_message_time[user_id] = time.time()

    # ---------------- Initialize per-user state ----------------
    user_history.setdefault(user_id, [])
    narrative_mode.setdefault(user_id, False)
    speaker_confirmation.setdefault(user_id, {"waiting": False, "text": None})
    user_stage_turns.setdefault(user_id, 0)
    last_forwarded_speaker.setdefault(user_id, None)

    current_stage = get_stage_for_user(user_id)
    logger.info(f"Incoming message from {user_id}: '{text}' | stage={current_stage}")

    # ---------------- Step 0: Greeting ----------------
    if current_stage == "Greeting" and user_stage_turns[user_id] == 0:
        messages = build_messages(user_message="", stage="Greeting", forwarded_messages=[], user_intent="self")
        reply, token_used = ask_llm(messages, stage="Greeting")
        increment_tokens(user_id, amount=token_used)
        get_user_metadata(user_id)
        send_text_reply(to=user_id, text=reply)
        user_stage_turns[user_id] += 1
        return

    # ---------------- Step 1: Forwarding / manual mode ----------------
    if current_stage == "Greeting" and not narrative_mode[user_id]:
        if text.lower() in ["yes", "forward", "fwd", "i want to forward"]:
            narrative_mode[user_id] = True
            user_history[user_id].clear()
            speaker_confirmation[user_id] = {"waiting": True, "text": None}
            send_text_reply(
                to=user_id,
                text="Great! Please forward your first message. Who sent it? Reply 'me' if you sent it, or 'them' if it was the other person."
            )
            safe_advance_stage(user_id, current_stage)
            threading.Thread(target=_watch_for_done_timeout, args=(user_id, BUFFER_TIMEOUT), daemon=True).start()
            return
        elif text.lower() in ["no", "explain"]:
            send_text_reply(to=user_id, text="Alright! Please tell me what happened in your own words.")
            safe_advance_stage(user_id, current_stage)
            return

    # ---------------- Step 2: Collect forwarded messages ----------------
    if narrative_mode[user_id]:
        if speaker_confirmation[user_id]["waiting"] and speaker_confirmation[user_id]["text"] is None:
            # Store first message temporarily
            speaker_confirmation[user_id]["text"] = text
            return
        elif speaker_confirmation[user_id]["waiting"]:
            first_msg = speaker_confirmation[user_id]["text"]
            if text.lower() in ["me", "i", "user", "u"]:
                speaker = "user"
            elif text.lower() in ["them", "friend", "other", "f"]:
                speaker = "friend"
            else:
                send_text_reply(to=user_id, text="Please reply 'me' if you sent it, or 'them' if it was the other person.")
                return

            # Save first message
            user_history[user_id].append({"speaker": speaker, "text": first_msg})
            last_forwarded_speaker[user_id] = speaker
            speaker_confirmation[user_id] = {"waiting": False, "text": None}
            send_text_reply(to=user_id, text="Got it! Forward the next message or type 'done' when finished.")
            return

        # Subsequent messages
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            if line.lower() == "done":
                narrative_mode[user_id] = False
                speaker_confirmation.pop(user_id, None)
                last_forwarded_speaker.pop(user_id, None)
                _process_forwarded(user_id)
                return
            last_speaker = last_forwarded_speaker.get(user_id, "friend")
            speaker = "user" if last_speaker == "friend" else "friend"
            user_history[user_id].append({"speaker": speaker, "text": line})
            last_forwarded_speaker[user_id] = speaker
        return

# ---------------- Step 3: Normal conversation ----------------
    else:
        # Append user message to history
        user_history[user_id].append({"speaker": "user", "text": text})

        # Build messages for LLM
        messages = build_messages(
            user_message=text,
            stage=current_stage,
            forwarded_messages=user_history[user_id][:-1],
            user_intent="self"
        )

        # Call LLM
        reply, token_used = ask_llm(messages, stage=current_stage)
        increment_tokens(user_id, amount=token_used)
        get_user_metadata(user_id)
        final_text = reply
        logger.info("LLM final reply:\n%s", final_text)

        try:
            # Send reply to user
            time.sleep(1)
            send_text_reply(to=user_id, text=final_text)

            # Stage turn management
            user_stage_turns[user_id] += 1
            required_turns = stage_turns_required.get(current_stage, 1)

            if user_stage_turns[user_id] >= required_turns:
                # Special handling for Next Steps
                if current_stage == "Next Steps":
                    # Mark that the next steps were shared so we don't loop
                    user_history[user_id].append("next_steps_done")
                    safe_advance_stage(user_id, current_stage)
                    # No extra hardcoded text; LLM already provides the closing naturally
                    return

                # Normal stage advancement
                safe_advance_stage(user_id, current_stage)

        except Exception as e:
            logger.exception("Failed to send LLM reply: %s", e)




# ---------------- Forwarded conversation processing ----------------
def _process_forwarded(user_id):
    forwarded_msgs = user_history[user_id]
    if not forwarded_msgs:
        send_text_reply(to=user_id, text="No messages were forwarded.")
        return

    context_note = (
        "The following conversation was forwarded by the user. "
        "Each message shows who originally said it (User or Other). "
        "Use this context to understand the situation and respond supportively."
    )
    formatted_forwarded = "\n".join(
        f"{'User' if msg['speaker']=='user' else 'Friend'}: {msg['text']}" for msg in forwarded_msgs
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{context_note}\n\n{formatted_forwarded}"},
        {"role": "system", "content": STAGE_PROMPTS.get("Validation", "")}
    ]
    reply, token_used = ask_llm(messages, stage="Validation")
    increment_tokens(user_id, amount=token_used)
    get_user_metadata(user_id)
    send_text_reply(to=user_id, text=reply)

    logger.info(f"User {user_id} finished forwarding {len(forwarded_msgs)} messages.")
    safe_advance_stage(user_id, get_stage_for_user(user_id))
    user_stage_turns[user_id] = 0


# ---------------- Timeout helper ----------------
def _watch_for_done_timeout(user_id: str, timeout: int = 60):
    start_time = time.time()
    while narrative_mode.get(user_id, False):
        if time.time() - last_message_time.get(user_id, start_time) > timeout:
            narrative_mode[user_id] = False
            _process_forwarded(user_id)
            logger.info(f"Auto-ended forwarding for {user_id} after timeout.")
            break
        time.sleep(2)


# ---------------- Status updates ----------------
def on_status(status_obj):
    """Handle delivery/read status updates."""
    logger.info(
        "Status update: id=%s status=%s timestamp=%s recipient_id=%s",
        status_obj.get("id"),
        status_obj.get("status"),
        status_obj.get("timestamp"),
        status_obj.get("recipient_id"),
    )
