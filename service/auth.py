from time import time
import logging

from handlers.send_message_handler import send_text_reply
from service.mongo import add_new_user, get_user_detail_m
from service.redis import cache_user_detail_r, get_user_detail_r
from utils.config import subscription_plan

logger = logging.getLogger("handlers")

def handle_new_user(user_id, text):
    send_text_reply(user_id, "Congratulations! You've unlocked the FLANK. Let's talk about how FLANK can help you.")
        
    # Add metadata
    user_data = {"is_registered": True, "registered_at": int(time())}

    if text in subscription_plan:
        plan_info = subscription_plan[text]
        user_data.update(plan_info)
        send_text_reply(user_id, f"You're now registered under the {plan_info['plan_name']}. You have {plan_info['tokens']} tokens available.")

        user_data["subscription_plan"] = text
        user_data["token_used"] = 0
        user_data["token_limit"] = plan_info["tokens"]
        user_data["summary_limit"] = plan_info["summary_limit"]
        
        logger.info("Registering new user %s with plan %s", user_id, text)
        add_new_user(user_id, user_data)
    else:
        send_text_reply(user_id, "Invalid promo code. Please check and try again.")
        return

def get_user_details(user_id):
    """
    Check if a user exists in Redis first. 
    If not, check MongoDB.
    Returns user details if found, else None.
    """
    # --- Step 1: Check Redis ---
    user_data = get_user_detail_r(user_id)
    if user_data:
        logger.info(f"Found user {user_id} in Redis")
        return user_data
    
    # --- Step 2: Fallback to MongoDB ---
    user_doc = get_user_detail_m(user_id)

    if user_doc:
        logger.info(f"Found user {user_id} in MongoDB")
        # Cache in Redis for future requests
        ttl_limit = subscription_plan[user_doc.get("subscription_plan", {})].get("ttl", 300)
        cache_user_detail_r(user_id, user_doc, ttl_limit)

        return user_doc
    
    # --- User not found ---
    raise RuntimeError("Please register to use the service.")