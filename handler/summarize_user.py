import datetime
import logging

import openai
from service.mongo import delete_user_conversation_m, get_user_conversation, get_user_detail_m, update_user_summary_m

logger = logging.getLogger("handlers")

def summarize_with_llm(prompt,summary_limit, user_id):
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You are Flank, a supportive coach."},
                  {"role": "user", "content": prompt}],
        max_tokens= summary_limit * 50
    )
    return response.choices[0].message.content.strip() # type: ignore



def summarize_user_session(user_id):
    """
    Summarize the user's session when their metadata expires in Redis.
    Triggered automatically when the Redis TTL expires.
    """
    from service.mongo import get_user_conversation, get_user_detail_m

    logger.info(f"🔔 TTL expired for {user_id} — starting summary generation.")

    # 1. Fetch conversation and metadata
    conversation = get_user_conversation(user_id)
    user_meta = get_user_detail_m(user_id)

    if not conversation:
        logger.warning(f"No conversation found for user {user_id} — skipping summary.")
        return

    summary_limit = user_meta.get("summary_limit", 5)

    # 2. Generate a meaningful summary
    try:
        summary_prompt = f"""
        You are Flank, a supportive conflict coach. 
        Summarize the following conversation in 3–4 sentences highlighting:
        - The main conflict topic
        - Key emotions expressed
        - Insights gained
        - The suggested next step or reflection

        Conversation:
        {conversation}
        """

        # Call your LLM (if available)
        summary = summarize_with_llm(summary_prompt,summary_limit, user_id=user_id)

    except Exception as e:
        logger.error(f"❌ LLM summarization failed for {user_id}: {e}")
        # Fallback: generate basic text summary
        summary = f"Summary of conversation for user {user_id}: {conversation[:200]}..."

    # 3. Store summary back in MongoDB
    update_user_summary_m(user_id, summary)
    delete_user_conversation_m(user_id)
    logger.info(f"✅ Stored summary for user {user_id}.")
