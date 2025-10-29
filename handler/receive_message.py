import logging
import asyncio
from handler.prompt import prompt_LLM
from handler.debouncer import debouncer_message
from handler.send_message import send_text_reply
from handler.summarize_user import summarize_user_session
from service.auth import get_user_details, handle_new_user
from service.mongo import store_user_conversation_m, update_user_token_usage
from service.redis import append_conversation_redis, get_user_detail_r, update_token_usage_redis

logger = logging.getLogger("handlers")

def extract_payload(payload):
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
        raise RuntimeError("Unhandled message type: %s", type_)
    
    ctx = msg.get("context", {})

    # Forwarded flags can vary by API version
    is_forwarded = ctx.get("forwarded") \
                or ctx.get("is_forwarded") \
                or (ctx.get("forwarding_score", 0) > 0)
    
    return user_id, text, is_forwarded

def post_prompt_tasks(total_tokens, ws_id, response):
    """Tasks to run after prompting LLM."""
    
    # Store the response in MongoDB and Redis    
    append_conversation_redis(ws_id, f"<bot> {response}", ttl_seconds=3600)
    update_token_usage_redis(ws_id, total_tokens)
    update_user_token_usage(ws_id,  total_tokens)

    response = get_user_detail_r(ws_id)
    if response.get('token_used') and response.get('token_limit') and int(response.get('token_limit')) < 20:
        send_text_reply(ws_id, "Warning: You are running low on tokens. Please consider upgrading your plan.")
    

def process_message(ws_id, combined, convo_str):
    """Process the combined message after debouncing."""
    store_user_conversation_m(ws_id, combined)

    logger.info(f"Store message in temp_collection for user {ws_id}")

    # Append to Redis conversation with TTL
    updated_convo = append_conversation_redis(ws_id, convo_str)

    response, total_tokens = prompt_LLM(ws_id, updated_convo, convo_str)

    logger.info(f"Response tokens used: {total_tokens} for user {ws_id}")

    post_prompt_tasks(total_tokens, ws_id, response)
    send_text_reply(ws_id, response)

def on_message(payload: dict):
    try:
        """Main handler for incoming WhatsApp messages."""
        user_id, text, is_forwarded = extract_payload(payload)

        if "PROMO_FLANK" in text:
            # Add new user to DB
            handle_new_user(user_id, text)
            return
        
        # get user info if exists
        get_user_details(user_id)
        
        # Debounce and process message
        debouncer_message(user_id, text, process_message, is_forwarded)
    except RuntimeError as re:
        msg = payload.get("message", {})
        user_id = msg.get("from")

        logger.warning("Runtime error: %s", re)
        send_text_reply(user_id, str(re))