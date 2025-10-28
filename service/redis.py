from datetime import datetime
import logging
import threading 
from handler.summarize_user import summarize_user_session
from utils.redis_client import RedisClient
from bson import ObjectId


logger = logging.getLogger("handlers")

def get_user_detail_r(user_id):
    redis_client = RedisClient().get_client()
    redis_key = f"user:{user_id}:metadata"
    
    return redis_client.hgetall(redis_key) 

def sanitize_for_redis(data):
    """
    Convert MongoDB document to Redis-safe dictionary.
    Handles ObjectId, bool, datetime recursively.
    """
    sanitized = {}
    for k, v in data.items():
        if isinstance(v, ObjectId):
            sanitized[k] = str(v)
        elif isinstance(v, bool):
            sanitized[k] = int(v)   # True -> 1, False -> 0
        elif isinstance(v, datetime):
            sanitized[k] = v.isoformat()
        elif isinstance(v, dict):
            sanitized[k] = sanitize_for_redis(v)  # recurse
        elif isinstance(v, list):
            # Convert list elements if needed
            sanitized[k] = [
                sanitize_for_redis(item) if isinstance(item, dict) else
                str(item) if isinstance(item, ObjectId) else
                int(item) if isinstance(item, bool) else
                item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized

def cache_user_detail_r(user_id, user_doc, ttl=300):
    redis_client = RedisClient().get_client()
    redis_key = f"user:{user_id}:metadata"

    user_data = sanitize_for_redis(user_doc)

    redis_client.hset(redis_key, mapping=user_data)

    # Set an expiration time of 5 minutes
    redis_client.expire(redis_key, ttl)

def append_conversation_redis(user_id, new_convo_str,ttl_seconds = 3600):
    """
    Append a new conversation string to existing conversation in Redis with TTL.
    """
    redis_client = RedisClient().get_client()
    redis_key = f"user:{user_id}:conversation"

    # Get existing conversation if any
    existing_convo = redis_client.get(redis_key)
    if existing_convo:
        updated_convo = existing_convo + "\n" + new_convo_str # type: ignore
    else:
        updated_convo = new_convo_str
        
    # Store back in Redis with TTL
    redis_client.set(redis_key, updated_convo)
    print(f"Appended conversation for user {user_id} in Redis")

    return updated_convo

def update_token_usage_redis(user_id, tokens_used):
    """
    Update token usage count for a user in Redis.
    """
    redis_client = RedisClient().get_client()
    redis_key = f"user:{user_id}:metadata"

    # Increment token usage
    redis_client.hincrby(redis_key, "token_usage", tokens_used)

def delete_user_conversation_redis(user_id):
    """
    Delete the Redis conversation key for a user.
    Key format: user:{user_id}:conversation
    """
    redis_client = RedisClient().get_client()
    redis_key = f"user:{user_id}:conversation"

    try:
        result = redis_client.delete(redis_key)
        if result == 1:
            logger.info(f"🧹 Deleted Redis conversation key for user {user_id}.")
        else:
            logger.info(f"ℹ️ No Redis conversation key found for user {user_id}.")
    except Exception as e:
        logger.error(f"❌ Error deleting Redis conversation key for user {user_id}: {e}")


def listen_for_expiry():
    client = RedisClient().get_client()
    pubsub = client.pubsub()
    pubsub.psubscribe("__keyevent@0__:expired")  # DB 0
    
    print("🔔 Listening for key expiry events...")
    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            expired_key = message["data"]
            print("Expired key:", expired_key)
            if expired_key.startswith("user:") and expired_key.endswith(":metadata"):
                user_id = expired_key.split(":")[1]
                logger.info(f"Metadata for user {user_id} has expired in Redis.")
                # Handle expiry event as needed
                summarize_user_session(user_id)
                # Remove the conversation from Redis
                delete_user_conversation_redis(user_id)

# Run in background
threading.Thread(target=listen_for_expiry, daemon=True).start()