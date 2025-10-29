import os
import logging
import requests
import time
import threading
import re
from handlers.llm import (
    ask_llm,
    build_messages,
    get_stage_for_user,
    advance_stage,
    SYSTEM_PROMPT,
    STAGE_PROMPTS,
    user_stages,
    parse_stage_signal,
    detect_tools_trigger,
)

logger = logging.getLogger("handlers")

# ---------------- WhatsApp API config ----------------
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_URL = "https://graph.facebook.com/v23.0"

# ---------------- In-memory stores ----------------
user_history = {}
narrative_mode = {}
last_message_time = {}
user_stage_turns = {}
speaker_confirmation = {}
last_forwarded_speaker = {}
validation_sent = {}
system_prompt_sent = {}
last_reply = {}
tools_history = {}
tools_practice_count = {}
tools_user_declined = {}
current_tool = {}
tool_step = {}
tools_practice_just_finished = {}

BUFFER_TIMEOUT = 60
MAX_REFLECTION_TURNS = 2
MAX_TOOL_STEPS = 4  # maximum steps per tool


# ---------------- Utility functions ----------------
def safe_advance_stage(user_id, current_stage):
    """Advance stage only if current stage matches; reset counters and mark validation done."""
    if current_stage not in ["Next Steps"]:
        advance_stage(user_id)
        user_stage_turns[user_id] = 0
        validation_sent[user_id] = True


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
    msg = payload.get("message", {})
    user_id = msg.get("from")
    type_ = msg.get("type")
    text = msg.get("text", {}).get("body", "").strip() if type_ == "text" else None

    if not text:
        logger.info("Ignoring non-text message from %s", user_id)
        return

    last_message_time[user_id] = time.time()

    # ---------------- Initialize per-user state ----------------
    user_history.setdefault(user_id, [])
    narrative_mode.setdefault(user_id, False)
    speaker_confirmation.setdefault(user_id, {"waiting": False, "text": None})
    user_stage_turns.setdefault(user_id, 0)
    last_forwarded_speaker.setdefault(user_id, None)
    user_stages.setdefault(user_id, "Greeting")
    validation_sent.setdefault(user_id, False)
    system_prompt_sent.setdefault(user_id, False)
    last_reply.setdefault(user_id, "")
    tools_history.setdefault(user_id, set())
    tools_practice_count.setdefault(user_id, 0)
    tools_user_declined.setdefault(user_id, False)
    current_tool.setdefault(user_id, None)

    current_stage = get_stage_for_user(user_id)
    logger.info(f"Incoming message from {user_id}: '{text}' | stage={current_stage}")

    # ---------------- Step 0: Greeting ----------------
    if current_stage == "Greeting" and user_stage_turns[user_id] == 0:
        messages = build_messages(user_message="", stage="Greeting", forwarded_messages=[], user_intent="self")
        reply = ask_llm(messages, stage="Greeting")
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
            threading.Thread(target=_watch_for_done_timeout, args=(user_id, BUFFER_TIMEOUT), daemon=True).start()
            return
        elif text.lower() in ["no", "explain"]:
            send_text_reply(to=user_id, text="Alright! Please tell me what happened in your own words.")
            user_stage_turns[user_id] = 0
            user_stages[user_id] = "Validation"
            return

    # ---------------- Step 2: Collect forwarded messages ----------------
    if narrative_mode[user_id]:
        if speaker_confirmation[user_id]["waiting"] and speaker_confirmation[user_id]["text"] is None:
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

            user_history[user_id].append({"speaker": speaker, "text": first_msg})
            last_forwarded_speaker[user_id] = speaker
            speaker_confirmation[user_id] = {"waiting": False, "text": None}
            send_text_reply(to=user_id, text="Got it! Forward the next message or type 'done' when finished.")
            return

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
    user_history[user_id].append({"speaker": "user", "text": text})

    # ---------------- Step 4: Detect Tools trigger ----------------
    if detect_tools_trigger(text) and current_stage in ["Reflection", "Next Steps"]:
        user_stages[user_id] = "Tools"
        user_stage_turns[user_id] = 0
        current_stage = "Tools"

    # ---------------- Validation stage ----------------
    if current_stage == "Validation" and not validation_sent[user_id]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": STAGE_PROMPTS.get("Validation", "")},
            {"role": "user", "content": text},
        ]
        reply = ask_llm(messages, stage="Validation")
        final_text, stage_ready, next_stage = parse_stage_signal(reply)
        if last_reply[user_id] and final_text.startswith(last_reply[user_id]):
            final_text = final_text[len(last_reply[user_id]):].strip()
        last_reply[user_id] = final_text
        send_text_reply(to=user_id, text=final_text)
        safe_advance_stage(user_id, "Validation")
        user_stages[user_id] = "Reflection"
        return

    # ---------------- Reflection stage ----------------
    if current_stage == "Reflection":
        user_stage_turns[user_id] += 1
        reflection_turn = user_stage_turns[user_id]

        continue_reflection = any(
            phrase in text.lower() for phrase in [
                "keep reflecting", "talk more", "go deeper", "not ready", "stay here", "still thinking", "want to explore"
            ]
        )

        reflection_hint = (
            f"(Reflection turn {reflection_turn}/{MAX_REFLECTION_TURNS}). "
            "Build on the user's message without repeating. "
            "If the user is ready for practical help or has reached max turns, include [stage_ready: true]."
        )

        messages = build_messages(
            user_message=text,
            stage="Reflection",
            forwarded_messages=user_history[user_id][:-1],
            user_intent="self",
            last_reply_text=last_reply.get(user_id)
        )
        messages.append({"role": "system", "content": reflection_hint})
        reply = ask_llm(messages, stage="Reflection")
        final_text, stage_ready, next_stage = parse_stage_signal(reply)

        if last_reply[user_id] and final_text.strip().lower() == last_reply[user_id].strip().lower():
            clarification = (
                "The previous reflection was too similar. "
                "Please build upon the user's new message with a fresh, deeper perspective."
            )
            messages.append({"role": "system", "content": clarification})
            reply = ask_llm(messages, stage="Reflection")
            final_text, stage_ready, next_stage = parse_stage_signal(reply)

        last_reply[user_id] = final_text
        send_text_reply(to=user_id, text=final_text)

        if reflection_turn >= MAX_REFLECTION_TURNS or stage_ready:
            safe_advance_stage(user_id, "Reflection")
            user_stages[user_id] = "Tools"
            user_stage_turns[user_id] = 0
        elif continue_reflection:
            return
        return

    # ---------------- Tools stage (LLM-driven) ----------------
    if current_stage == "Tools":
        tools_history.setdefault(user_id, set())
        tool_step.setdefault(user_id, 0)
        tools_practice_count.setdefault(user_id, 0)
        current_tool.setdefault(user_id, None)
        tools_user_declined.setdefault(user_id, False)
        tools_practice_just_finished.setdefault(user_id, False)

        practicing = current_tool.get(user_id) is not None and not tools_user_declined.get(user_id, False)
        current_step = tool_step.get(user_id, 0)

        # ---------------- Step 1: Practice existing tool ----------------
        if practicing:
            messages = build_messages(
                user_message=text,
                stage="Tools",
                forwarded_messages=user_history[user_id][:-1],
                user_intent="self",
                last_reply_text=last_reply.get(user_id)
            )
            messages.append({
                "role": "system",
                "content": (
                    f"The user is currently practicing '{current_tool[user_id]}'. "
                    "Do NOT suggest a new tool. Only guide them interactively through the next step. "
                    "Keep instructions short and supportive. "
                    "After the final step, include [stage_ready:true]."
                )
            })

            reply = ask_llm(messages, stage="Tools")
            final_text, stage_ready, _ = parse_stage_signal(reply)
            send_text_reply(to=user_id, text=final_text)
            last_reply[user_id] = final_text

            # Move to next step
            tool_step[user_id] = current_step + 1

            # If this was the final step, mark practice finished, but don't wrap-up yet
            if stage_ready or tool_step[user_id] >= MAX_TOOL_STEPS:
                tools_practice_just_finished[user_id] = True
                tools_history[user_id].add(current_tool[user_id])
                current_tool[user_id] = None
                tool_step[user_id] = 0
                tools_practice_count[user_id] += 1
                # Wait for next user input to send wrap-up
                return

        # ---------------- Step 2: Wrap-up after practice with readiness check ----------------
        if tools_practice_just_finished.get(user_id, False) and not practicing:
            wrapup_messages = build_messages(
                user_message=(
                    "The user has just finished practicing a tool. "
                    "Provide a warm, supportive wrap-up message that acknowledges their effort, "
                    "mentions the tool they just practiced, and asks if they feel ready to move on. "
                    "Do NOT suggest the tool again or introduce a new tool. "
                    "Regardless of their answer, advance to the next stage."
                ),
                stage="Tools",
                forwarded_messages=user_history[user_id][:-1],
                user_intent="self"
            )
            wrapup_reply = ask_llm(wrapup_messages, stage="Tools")
            final_wrapup, _, _ = parse_stage_signal(wrapup_reply)
            send_text_reply(to=user_id, text=final_wrapup)

            # Move directly to Next Steps after sending wrap-up
            tools_practice_just_finished[user_id] = False
            user_stages[user_id] = "Next Steps"
            return

        # ---------------- Step 3: Suggest a new tool ----------------
        if (not practicing
            and current_tool.get(user_id) is None
            and not tools_practice_just_finished.get(user_id, False)
            and not tools_user_declined.get(user_id, False)):
            
            messages = build_messages(
                user_message=text,
                stage="Tools",
                forwarded_messages=user_history[user_id][:-1],
                user_intent="self",
                last_reply_text=last_reply.get(user_id)
            )
            messages.append({
                "role": "system",
                "content": (
                    "You are in the Tools stage. Suggest ONE practical, evidence-based therapeutic tool "
                    "relevant to the user's situation. Keep tone conversational and concise. "
                    "Introduce it with [tool_name:<name>]. "
                    "Do NOT suggest a second tool. "
                    "If the user declines, move directly to Next Steps with a warm wrap-up."
                )
            })
            reply = ask_llm(messages, stage="Tools")
            final_text, stage_ready, _ = parse_stage_signal(reply)

            # Detect new tool suggested
            match = re.search(r"\[tool_name:\s*(.+?)\]", reply, re.IGNORECASE)
            if match:
                current_tool[user_id] = match.group(1).strip()
                tools_user_declined[user_id] = False
                tool_step[user_id] = 0
                last_reply[user_id] = final_text
                send_text_reply(to=user_id, text=final_text)
                return

        # ---------------- Step 4: Handle user decline ----------------
        if any(kw in text.lower() for kw in ["no", "not now", "skip", "don't want", "later"]):
            if current_tool.get(user_id) and not tools_user_declined.get(user_id, False):
                # Mark tool as declined
                tools_history[user_id].add(current_tool[user_id])
                current_tool[user_id] = None
                tools_user_declined[user_id] = True
                tool_step[user_id] = 0
                tools_practice_count[user_id] = 1

                # Wrap-up message via LLM (acknowledge tool and move to Next Steps)
                wrapup_messages = build_messages(
                    user_message=(
                        "The user declined practicing the tool. Provide a warm, supportive wrap-up message, "
                        "mention the tool they just saw, and move on to the next stage. "
                        "Do NOT suggest another tool."
                    ),
                    stage="Tools",
                    forwarded_messages=user_history[user_id][:-1],
                    user_intent="self"
                )
                wrapup_reply = ask_llm(wrapup_messages, stage="Tools")
                final_wrapup, _, _ = parse_stage_signal(wrapup_reply)
                send_text_reply(to=user_id, text=final_wrapup)

                # Advance to Next Steps
                safe_advance_stage(user_id, "Tools")
                user_stages[user_id] = "Next Steps"
                return

        

    # ---------------- Next Steps stage ----------------
    if current_stage == "Next Steps":
        tools_practice_just_finished[user_id] = False
        messages = build_messages(
            user_message=text,
            stage="Next Steps",
            forwarded_messages=user_history[user_id][:-1],
            user_intent="self",
            last_reply_text=last_reply.get(user_id)
        )
        reply = ask_llm(messages, stage="Next Steps")
        final_text, stage_ready, next_stage = parse_stage_signal(reply)

        if last_reply.get(user_id) and final_text.startswith(last_reply[user_id]):
            final_text = final_text[len(last_reply[user_id]):].strip()

        last_reply[user_id] = final_text
        send_text_reply(to=user_id, text=final_text)

        if stage_ready:
            safe_advance_stage(user_id, current_stage)
        elif next_stage and next_stage != "Validation":
            user_stages[user_id] = next_stage
            user_stage_turns[user_id] = 0


# ---------------- Forwarded conversation processing ----------------
def _process_forwarded(user_id):
    forwarded_msgs = user_history.get(user_id, [])
    if not forwarded_msgs:
        send_text_reply(to=user_id, text="No messages were forwarded.")
        return

    context_note = (
        "The following conversation was forwarded by the user. "
        "Each message shows who originally said it (User or Other). "
        "Use this context to respond supportively."
    )

    formatted_forwarded = "\n".join(
        f"{'User' if msg['speaker']=='user' else 'Friend'}: {msg['text']}"
        for msg in forwarded_msgs
    )

    messages = []
    if not system_prompt_sent[user_id]:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
        system_prompt_sent[user_id] = True

    messages.append({"role": "system", "content": STAGE_PROMPTS.get("Validation", "")})
    messages.append({"role": "user", "content": f"{context_note}\n\n{formatted_forwarded}"})

    reply = ask_llm(messages, stage="Validation")
    final_text, stage_ready, next_stage = parse_stage_signal(reply)

    if last_reply[user_id] and final_text.startswith(last_reply[user_id]):
        final_text = final_text[len(last_reply[user_id]):].strip()

    last_reply[user_id] = final_text
    send_text_reply(to=user_id, text=final_text)
    safe_advance_stage(user_id, "Validation")
    user_stages[user_id] = "Reflection"
    user_stage_turns[user_id] = 0
    validation_sent[user_id] = True


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
    logger.info(
        "Status update: id=%s status=%s timestamp=%s recipient_id=%s",
        status_obj.get("id"),
        status_obj.get("status"),
        status_obj.get("timestamp"),
        status_obj.get("recipient_id"),
    )
