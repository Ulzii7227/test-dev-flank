import logging
import json
import os
import threading
from datetime import datetime
from dotenv import load_dotenv

from utils.mongo_client import get_meta, upsert_user_if_needed, get_mongo_client
from utils.redis_client import RedisClient

logger = logging.getLogger("handlers")
logger.setLevel(logging.INFO)

load_dotenv()

# Redis client
r_ = RedisClient().get_client()
MONGODB_DB  = os.getenv("MONGODB_DB", "flank_chatbot")
# MongoDB client and collection
mongo_client = get_mongo_client()
db = mongo_client[MONGODB_DB]
_meta = db.user_metadata

# In-memory backup for expired Redis keys
redis_backup = {}

# -------------------------------
# Helper: sanitize metadata for Redis
# -------------------------------
def sanitize_metadata(metadata: dict) -> dict:
    sanitized = {}
    for k, v in metadata.items():
        if isinstance(v, (int, float, str, bool)):
            sanitized[k] = v
        elif isinstance(v, list) or isinstance(v, dict):
            sanitized[k] = json.dumps(v)
        elif hasattr(v, "isoformat"):
            sanitized[k] = v.isoformat()
        else:
            sanitized[k] = str(v)
    return sanitized

# -------------------------------
# Pull metadata from MongoDB and store in Redis
# -------------------------------
def pull_meta_store(wa_id: str, ttl: int = 5):
    if not wa_id:
        logger.warning("No WhatsApp ID provided.")
        return

    logger.info("Pulling metadata for WhatsApp ID: %s", wa_id)

    # Ensure user exists in MongoDB
    upsert_user_if_needed(wa_id)

    # Fetch metadata from MongoDB
    metadata = get_meta(wa_id)
    logger.info("Fetched metadata from MongoDB: %s", metadata)

    # Sanitize and store in Redis
    redis_ready_metadata = sanitize_metadata(metadata)
    key = f"user:{wa_id}:metadata"
    r_.hset(key, mapping=redis_ready_metadata)
    r_.expire(key, ttl)

    # Store backup for expiry
    redis_backup[wa_id] = redis_ready_metadata

    logger.info("Metadata for %s stored in Redis with TTL %ds.", wa_id, ttl)

# -------------------------------
# Increment tokens in Redis
# -------------------------------
def increment_tokens(wa_id: str, amount: int = 1):
    key = f"user:{wa_id}:metadata"
    new_count = r_.hincrby(key, "tokens_used", amount)

    # Update backup for expiry
    data = r_.hgetall(key)
    redis_backup[wa_id] = {k: v for k, v in data.items()}
    logger.info("Incremented tokens for",redis_backup[wa_id])
    return new_count

# -------------------------------
# Get remaining tokens
# -------------------------------clea
def get_remaining_tokens(wa_id: str):
    key = f"user:{wa_id}:metadata"
    data = r_.hgetall(key)
    if not data:
        return 0

    token_used = int(data.get("tokens_used", 0))
    token_limit = int(data.get("token_limit", 1000))
    return token_limit - token_used

# -------------------------------
# Get user metadata from Redis
# -------------------------------
def get_user_metadata(wa_id: str):
    key = f"user:{wa_id}:metadata"
    data = r_.hgetall(key)
    if not data:
        return None

    logger.info("User %s metadata: %s", wa_id, data)
    return data

# -------------------------------
# Listener for Redis key expiration
# -------------------------------
def listen_for_expired_keys():
    try:
        r_.config_set("notify-keyspace-events", "Ex")
    except Exception as e:
        logger.error("Failed to enable Redis keyspace notifications: %s", e)
        return

    pubsub = r_.pubsub()
    pubsub.psubscribe("__keyevent@0__:expired")

    for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        expired_key = message["data"]
        if expired_key.startswith("user:") and expired_key.endswith(":metadata"):
            wa_id = expired_key.split(":")[1]
            logger.info("Redis key expired for user_id: %s", wa_id)

            metadata = redis_backup.pop(wa_id, None)
            if metadata:
                # Persist to MongoDB on expiry
                _meta.update_one(
                    {"user_id": wa_id},
                    {"$set": {
                        "tokens_used": int(metadata.get("tokens_used", 0)),
                        "last_updated": datetime.utcnow()
                    }},
                    upsert=True
                )
                logger.info("MongoDB updated for user_id: %s on Redis expiry.", wa_id)

# -------------------------------
# Start listener in background thread
# -------------------------------
threading.Thread(target=listen_for_expired_keys, daemon=True).start()
