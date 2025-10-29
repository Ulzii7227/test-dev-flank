import os
import logging
import re
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


# -----------------------------
# LLM call function
# -----------------------------
def ask_llm(messages, stage: str = None) -> str:
    """
    Send user prompt to OpenAI and return the reply text.
    """
    if not OPENAI_API_KEY:
        return "Sorry, I cannot reply right now."

    stage_max_tokens = {
        "Greeting": 80,
        "Validation": 70,
        "Reflection": 120,
        "Tools": 200,
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
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("LLM API call failed: %s", e)
        return "Sorry, something went wrong."


# -----------------------------
# Tag Parsing Helpers
# -----------------------------
def parse_stage_signal(text: str):
    """
    Detects [stage_ready: true] or [stage_next: Reflection] etc.
    Returns (cleaned_text, stage_ready: bool, next_stage: str or None)
    """
    stage_ready = False
    next_stage = None

    ready_match = re.search(r"\[stage_ready:\s*true\]", text, re.IGNORECASE)
    if ready_match:
        stage_ready = True
        text = re.sub(r"\[stage_ready:\s*true\]", "", text, flags=re.IGNORECASE)

    next_match = re.search(r"\[stage_next:\s*(.*?)\]", text, re.IGNORECASE)
    if next_match:
        next_stage = next_match.group(1).strip()
        text = re.sub(r"\[stage_next:\s*.*?\]", "", text, flags=re.IGNORECASE)

    return text.strip(), stage_ready, next_stage


# -----------------------------
# Optional user-initiated “go back” detector
# -----------------------------
def detect_user_stage_request(text: str):
    """Detects if user explicitly wants to revisit a previous stage."""
    text = text.lower()
    if "go back" in text or "revisit" in text or "talk more about" in text:
        if "validation" in text:
            return "Validation"
        elif "reflection" in text:
            return "Reflection"
        elif "tools" in text:
            return "Tools"
    return None


# -----------------------------
# System & Stage Prompts
# -----------------------------
SYSTEM_PROMPT = """
You are Flank, a supportive conflict coach and digital companion for young people (ages 16–35)
facing frequent or chronic conflict with family or friends.

User Profile:
- Young person seeking help with a specific conflict.
- Goal: regulate emotions, feel heard, practice therapeutic tools and techniques that will help the user to take constructive action.

Purpose:
- Guide the user on a conversational conflict coaching journey.
- Help them move from a reactive state to a reflective state.
- Support learning, self-awareness, and connection in relationships through the deployment of helpful tools and techniques.
- Help the user walk away with an actionable next step.

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
- Trauma-informed youth work
- Relational-cultural theory
- Psychodynamic theory
- DBT (emotional regulation)
- Non-violent communication

Personality:
- Curious, empathetic, grounded, kind, and clear.
- Feels like a wise, reliable friend, not a therapist.
- Uses warm, everyday, accessible language.
- Always empowers users to find their own solutions.

Safety:
- If harm, abuse, or self-harm is mentioned, show care and direct to supports or emergency services.
- Never give advice that could cause harm or diminish dignity.
- Never make discriminatory or harmful remarks.
- Don't hallucinate facts or make up resources.

Message Guidelines:
- Keep responses short and human.
- Allow multiple exchanges per stage until the user seems emotionally ready to move on.
- When you feel the user is ready for the next stage, include [stage_ready: true].
- Do NOT show these tags in your text — they are for the system only.
- Don't repeat or rephrase what has been previously said. Build upon what the user has already shared.
- If the user uses conditional, hypothetical, or uncertain language (e.g. “if,” “maybe,” “I guess,” “I hope”), respond carefully and avoid treating those as facts.
- Don't hallucinate
"""

STAGE_PROMPTS = {
    "Greeting": """
Stage: Greeting.
Respond warmly to the user’s hello. Introduce yourself casually, e.g., 
"Hey! I'm Flank, your conflict companion."
Ask how you can help them with their situation.
Clearly ask: "Did you know you can forward messages to me? (reply 'yes' to forward, 'no' to tell me what happened in your own words)"  
Keep it light and two sentences max.
[stage_done: true]  # allows moving to next stage after user responds
""",

    "Validation": """
Stage: Validation.
Acknowledge and validate the user's feelings in 1–2 sentences.
Reflect emotions gently and optionally check in with: "Does that sound right?"
Do NOT signal stage readiness unless user confirms readiness explicitly.
Keep it natural and brief.
""",

    "Reflection": """
Stage: Reflection.
Encourage thoughtful self-exploration by building on what the user has already said.
Avoid repeating or rephrasing earlier questions — instead, reference the user's previous words and guide the user to greater understanding.
Be relevant and use accessible words and phrases. Don't be too intellectual or clinical.
Ask only one helpful question to help the user reach greater clarity, don't be too abstract. 
If the user says they want to keep reflecting, continue exploring for a couple more exchanges.
After a few reflections, gently invite them to try something practical and include [stage_ready: true].
Keep tone warm, grounded, and curious.
""",

    "Tools": """
Stage: Tools.
Suggest one practical, therapeutic tool or technique to help with the conflict.

Ensure that the tool or technique is evidence-based, relevant, and appropriate for the situation.
Keep tone conversational, not clinical.
End with a warm question like, “Does that feel doable?” or “Would you like to try that?”

If the user agrees, guide a short, interactive practice (2–4 steps) using micro-role-play, reflective rehearsal, or guided fill-in, depending on the tool and the user’s comfort.
Offer gentle feedback, encouragement, and reflection at each step.
Keep the exercise brief, emotionally safe, and supportive.

If the user declines to practice, end this stage gracefully with a warm acknowledgment and append [stage_ready: true].
Do not introduce new tools unless the user explicitly requests one.
When the practice or reflection is complete, append [stage_ready: true]
""",

    "Next Steps": """
Stage: Next Steps.
Respond like a caring friend wrapping up the chat.
Offer one supportive or encouraging statement — e.g., "Want to check in later on how it goes?"
Do not end the conversation automatically; wait for user to indicate they are done.
Restate the tool you've provided and encourage them to try it out.
Keep it short, kind, and natural.
Be concise 
"""
}



# -----------------------------
# Stage management
# -----------------------------
STAGES = ["Greeting", "Validation", "Reflection", "Tools", "Next Steps"]
user_stages = {}


def get_stage_for_user(user_id: str) -> str:
    """Return the current stage for a user."""
    return user_stages.get(user_id, "Greeting")


def advance_stage(user_id: str):
    """Move the user to the next stage in the conversation flow."""
    current = get_stage_for_user(user_id)
    next_index = min(STAGES.index(current) + 1, len(STAGES) - 1)
    user_stages[user_id] = STAGES[next_index]


# -----------------------------
# Context Builders
# -----------------------------
# def build_conversation_context(user_message: str, forwarded_messages: list = None, user_intent: str = None) -> str:
#     """
#     Build conversation context for the LLM.
#     Expects forwarded_messages as list of dicts: {"speaker": "user"|"friend", "text": "..."}
#     """
#     context_parts = []

#     if user_intent == "forward":
#         context_parts.append(
#             "The user is forwarding messages from a conversation. Wait until they finish before moving to the next stage."
#         )

#     normalized_messages = []
#     if forwarded_messages:
#         for msg in forwarded_messages:
#             if isinstance(msg, dict):
#                 normalized_messages.append(msg)
#             elif isinstance(msg, str):
#                 normalized_messages.append({"speaker": "friend", "text": msg})
#             else:
#                 logger.warning("Unexpected message type in forwarded_messages: %s", type(msg))

#     if normalized_messages:
#         formatted = []
#         for msg in normalized_messages:
#             speaker = "User" if msg.get("speaker") == "user" else "Friend"
#             formatted.append(f"{speaker}: {msg['text']}")
#         context_parts.append("Forwarded conversation:\n" + "\n".join(formatted))

#     if user_message:
#         context_parts.append("\nThen the user said:\n" + user_message)

#     if not context_parts:
#         context_parts.append("No messages provided yet.")

#     return "\n".join(context_parts)


def build_messages(
    user_message: str,
    stage: str,
    forwarded_messages: list = None,
    user_intent: str = None,
    last_reply_text: str = None,
    reflection_turn: int = 0,
    max_reflection_turns: int = 2
) -> list:
    """
    Build the structured OpenAI chat message list for the conversation.
    - Includes forwarded messages.
    - Includes previous assistant reply to avoid repetition.
    - Passes reflection turn info so LLM knows how many times reflection has occurred.
    """
    conversation_context = build_conversation_context(user_message, forwarded_messages, user_intent)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Provide last assistant reply so LLM doesn't repeat itself
    if last_reply_text:
        messages.append({
            "role": "assistant",
            "content": f"(Previous message you wrote: \"{last_reply_text}\")"
        })

    # Include user message
    messages.append({"role": "user", "content": conversation_context})

    # Stage-specific prompt
    stage_prompt = STAGE_PROMPTS.get(stage, "")

    # Reflection-specific enhancement
    if stage == "Reflection":
        stage_prompt += (
            f"\nImportant: This is reflection turn {reflection_turn} out of {max_reflection_turns}.\n"
            "Do not repeat previous questions or rephrase earlier prompts. "
            "Build upon what the user has already shared. "
            "If reflection_turn >= max_reflection_turns, gently invite the user to try something practical and include [stage_ready: true]."
        )
    elif stage == "Validation":
        stage_prompt += (
            "\nImportant: Do NOT repeat or rephrase earlier questions. "
            "Build upon what the user has already shared."
        )

    messages.append({"role": "system", "content": stage_prompt})

    return messages


def detect_tools_trigger(user_message: str) -> bool:
    """
    Detects if the user is asking for advice, guidance, or solutions — triggers Tools stage.
    """
    text = user_message.lower().strip()

    # Broader set of triggers (covers question variants)
    patterns = [
        r"\bwhat should i do\b",
        r"\bwhat do i do\b",
        r"\bwhat can i do\b",
        r"\bhow can i fix\b",
        r"\bhow do i handle\b",
        r"\bany advice\b",
        r"\bwhat advice do you have\b",
        r"\bcan you help me decide\b",
        r"\bwhat would you suggest\b",
        r"\bwhat would you recommend\b",
        r"\bhow should i approach\b",
        r"\bwhat are my options\b",
        r"\bi dont know\b",
        r"\bi'm stuck\b",
        r"\btool\b",
        r"\bsomething practical\b",
    ]

    return any(re.search(p, text) for p in patterns)