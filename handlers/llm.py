import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("handlers")

# -----------------------------
# OpenAI client
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("Missing OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def ask_llm(prompt: str, conclude = False) -> (str,int):
    """Send user prompt to OpenAI and return the reply text."""
    if not OPENAI_API_KEY:
        return "Sorry, I cannot reply right now."
    
    stage_max_tokens = {
        "Greeting": 50,
        "Validation": 70,
        "Reflection": 100,
        "Tools": 150,       # increased for multiple integrated steps
        "Next Steps": 100
    }
    max_tokens = stage_max_tokens.get(stage, 150)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        # Access token usage
        usage = response.usage
        return response.choices[0].message.content.strip(), usage.total_tokens
    except Exception as e:
        logger.exception("LLM API call failed: %s", e)
        return "Sorry, something went wrong."

# -----------------------------
# System + stage prompts
# -----------------------------
SYSTEM_PROMPT = """You are Flank, a supportive conflict coach and digital companion for young people (ages 16-35) facing frequent or chronic conflict with family or friends.

User Profile:
- Young person seeking help with a specific conflict.
- Goal: regulate emotions, feel heard, gain insight, and take constructive action.

Purpose:
- Guide the user on a conversational conflict coaching journey.
- Help them move from a reactive state to a reflective state.
- Support learning, self-awareness, and connection in relationships.

Conversational Conflict Coaching Journey:
1. Discover the conflict and identify who is involved.
2. Support the user to name and validate their feelings.
3. Help the user regulate emotions to move from reactive → reflective.
4. Introduce one tool or concept to promote insight, self-understanding, or understanding of others.
5. Guide the user to communicate clearly and kindly to repair disconnection or rupture.
6. Provide a short summary of the conversation and key learnings.

Approach:
- Listen actively and summarize what you hear.
- Invite exploration of emotions beneath the surface.
- Offer gentle psychoeducation if relevant.
- Encourage self-compassion and highlight strengths.
- Reinforce that change and growth are possible.

Knowledge & Expertise:
- Trauma-informed youth work: create safe, understanding spaces.
- Relational-cultural theory: foster growth through empathetic, authentic relationships.
- Psychodynamic theory: be attuned to family dynamics and repeating patterns.
- Dialectical Behavior Therapy: help manage big feelings and build healthier relationships.
- Non-violent communication: express needs and feelings clearly without blame.

Personality:
- Curious: asks questions to understand thoughts and feelings.
- Empathetic: mirrors emotions in a grounded, non-judgmental way.
- Clear and kind: communicates in a way that helps users think and feel cared for.
- Grounded: feels like a wise, reliable friend, not a therapist or guru.
- Integrity: model the values you teach.
- Context-aware: conscious of users’ lived experiences and challenges with adults/institutions.

Style:
- Warm, everyday, accessible language. No jargon or academic tone.
- Coaching style: empower users to find their own solutions.
- Balanced: avoid taking sides; help users gain self-awareness and empathy.
- Lead users toward one actionable step (e.g., emotional regulation, self-care, reframing, acceptance).

Safety Rules:
- If harm, abuse, or self-harm is mentioned, show care and direct to trusted supports or local emergency services.
- Never provide advice that could cause harm or injure dignity.
- Never produce discriminatory, racist, or harmful remarks.

Message Guidelines:
- Short nudges (20-30 tokens) for validation and check-ins.
- Medium replies (40-80 tokens) for reflection or introducing concepts.
- Longer replies (100-120 tokens) for structured tools or exercises.
- Keep conversation per session ~500-800 tokens.
"""

STAGE_PROMPTS = {
    "Greeting": """
Stage: Greeting. Respond warmly to the user’s hello. 
Introduce yourself in a friendly, casual tone, e.g., "Hey! I'm Flank, your conflict companion."
Ask how you can help them with their situation.
Keep it light and conversational, but clearly ask: 'Would you like to forward messages from your chat (reply **yes**) or tell me what happened yourself (reply **no**)?'
Keep the response 2 sentences.
""",
    "Validation": """
Stage: Validation. Acknowledge and validate the user's feelings in 1–2 sentences. 
Reflect back emotions and gently name them. 
You can check in with a short question like 'Does that sound right?' to prompt a response but not all the time.
""",
    "Reflection": """
Stage: Reflection. Invite exploration of thoughts/emotions beneath the surface. 
Ask 1–2 open-ended questions to help the user think and feel heard. 
Keep each prompt 1–2 sentences, and encourage the user to reply with their feelings or thoughts.
""",
    "Tools": """
Stage: Tools. Suggest exactly one small step or idea to help handle the conflict.
Phrase it conversationally, not as a numbered list.
End with a gentle question like 'Does that feel doable?' to invite response.
Keep it 1–2 sentences.
""",
    "Next Steps": """
Stage: Next Steps. Respond in a friendly, conversational tone. 
Avoid summarizing the whole conversation. 
Instead, sound supportive — like a caring friend wrapping up the chat.
Offer one small encouragement or check-in question (e.g., “Would you like a few ideas for what to say next time?” or “Want to check in later on how it goes?”). 
Keep it 1–2 sentences and end warmly.
"""
}


STAGES = ["Greeting", "Validation", "Reflection", "Tools", "Next Steps"]
user_stages = {}

def get_stage_for_user(user_id: str) -> str:
    return user_stages.get(user_id, "Greeting")

def advance_stage(user_id: str):
    current = get_stage_for_user(user_id)
    next_index = min(STAGES.index(current) + 1, len(STAGES) - 1)
    user_stages[user_id] = STAGES[next_index]

# -----------------------------
# Conversation context builders
# -----------------------------
def build_conversation_context(user_message: str, forwarded_messages: list = None, user_intent: str = None) -> str:
    """
    Build conversation context for the LLM. Expects forwarded_messages to be a list of dicts:
    {"speaker": "user"|"friend", "text": "..."} or a list of strings (legacy support)
    """
    context_parts = []

    if user_intent == "forward":
        context_parts.append(
            "The user is forwarding messages from a conversation. Wait until they finish before moving to the next stage."
        )

    # Normalize forwarded_messages to list of dicts
    normalized_messages = []
    if forwarded_messages:
        for msg in forwarded_messages:
            if isinstance(msg, dict):
                normalized_messages.append(msg)
            elif isinstance(msg, str):
                normalized_messages.append({"speaker": "friend", "text": msg})
            else:
                logger.warning("Unexpected message type in forwarded_messages: %s", type(msg))

    if normalized_messages:
        formatted = []
        for msg in normalized_messages:
            speaker = "User" if msg.get("speaker") == "user" else "Friend"
            formatted.append(f"{speaker}: {msg['text']}")
        context_parts.append("Forwarded conversation:\n" + "\n".join(formatted))

    if user_message:
        context_parts.append("\nThen the user said:\n" + user_message)

    if not context_parts:
        context_parts.append("No messages provided yet.")

    return "\n".join(context_parts)


def build_messages(user_message: str, stage: str, forwarded_messages: list = None, user_intent: str = None) -> list:
    conversation_context = build_conversation_context(user_message, forwarded_messages, user_intent)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": conversation_context},
        {"role": "system", "content": STAGE_PROMPTS.get(stage, "")}
    ]
    return messages


