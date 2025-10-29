from datetime import datetime
from utils.mongo_client import MongoDB
import logging

logger = logging.getLogger("handlers")

user_meta_collection = "user_meta"
user_chat_collection ="temp_user_chats"

def get_user_detail_m(user_id):
    """
    Fetch user details from the user_meta collection by user_id.
    """
    db = MongoDB.get_db()
    user_collection = db[user_meta_collection]
    
    # Fetch user document
    user_doc = user_collection.find_one({"user_id": user_id})
    
    if user_doc is None:
        logger.info(f"No user found with user_id: {user_id}")
        return None
    else:
        logger.info("Fetched user details for user_id: %s", user_id)
        return user_doc
    
def add_new_user(user_id, user_data):
    """
    Add a new user to the user_meta collection.
    """
    db = MongoDB.get_db()
    user_collection = db[user_meta_collection]
    
    # Prepare user document
    user_doc = {"user_id": user_id}
    user_doc.update(user_data)
    
    # Insert new user document
    user_collection.insert_one(user_doc)
    logger.info("Added new user with user_id: %s", user_id)

def store_user_conversation_m(user_id, chat_entry):
    """
    Store a single message in the user's conversation history.
    Each user has one document with a 'messages' list.
    """
    db = MongoDB.get_db()
    chat_collection = db[user_chat_collection]

    print(f"Storing chat entry for user_id: {user_id}: {chat_entry}")
    # Append message to the user's document, create document if it doesn't exist
    chat_collection.update_one(
        {"user_id": user_id},                # filter
        {"$push": {"messages": {"$each":chat_entry}}}, # push new messages to messages array
        upsert=True                          # create document if not exists
    )

    logger.info(f"Stored message for user {user_id}.")

def get_user_conversation(user_id):
    """
    Retrieve the conversation history for a user.
    """
    db = MongoDB.get_db()
    chat_collection = db[user_chat_collection]

    # Fetch user conversation document
    chat_doc = chat_collection.find_one({"user_id": user_id})

    if chat_doc is None:
        logger.info(f"No conversation history found for user_id: {user_id}")
        return []
    else:
        logger.info(f"Fetched conversation history for user_id: {user_id}")
        return chat_doc.get("messages", [])
    
def update_user_metadata(user_id, update_data):
    """
    Update user metadata in the user_meta collection.
    """
    db = MongoDB.get_db()
    user_collection = db[user_meta_collection]
    
    # Update user document
    result = user_collection.update_one(
        {"user_id": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        logger.info(f"No user found with user_id: {user_id} to update.")
    else:
        logger.info(f"Updated user metadata for user_id: {user_id}.")

def update_user_token_usage(user_id, tokens_used):
    """
    Increment the token usage count for a user.
    """
    db = MongoDB.get_db()
    user_collection = db[user_meta_collection]
    
    # Increment token usage
    result = user_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"token_used": tokens_used}}
    )
    
    if result.matched_count == 0:
        logger.info(f"No user found with user_id: {user_id} to update token usage.")
    else:
        logger.info(f"Incremented token usage by {tokens_used} for user_id: {user_id}.")

def update_user_summary_m(user_id, summary_text):
    """
    Update or add the 'summary' field in the user's metadata document.
    """
    db = MongoDB.get_db()
    user_collection = db[user_meta_collection]

    result = user_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "summary": summary_text,
            "summary_updated_at": datetime.utcnow()
        }}
    )

    if result.matched_count:
        logger.info(f"✅ Summary updated for user {user_id}.")
    else:
        logger.warning(f"⚠️ No user found with user_id {user_id} to update summary.")


def delete_user_conversation_m(user_id):
    """
    Delete all chat messages belonging to a user from user_chat_collection.
    """
    db = MongoDB.get_db()
    chat_collection = db[user_chat_collection]

    result = chat_collection.delete_many({"user_id": user_id})

    logger.info(f"🧹 Deleted {result.deleted_count} chat messages for user {user_id}.")

