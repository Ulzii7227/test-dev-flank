import re
from service.redis import get_tools_r, get_user_stage_r, get_user_stage_step_r, set_user_stage_r, set_user_stage_step_r


STAGES = {
    'GREETING': ("Greeting", "Validation"),
    'VALIDATION': ("Validation", "Reflection"),
    'REFLECTION': ("Reflection", "Tools"),
    'TOOLS': ("Tools", "Next Steps"),
    'NEXT_STEPS': "Next Steps",
}

max_step = {
    STAGES["REFLECTION"][0]: 1,
    STAGES["TOOLS"][0]: 5,
}

STAGE_PROMPTS = {
    "Greeting": """
        Stage: Greeting.
        Respond warmly to the user’s hello. Introduce yourself casually, e.g., 
        "Hey! I'm Flank, your conflict companion."
        Ask how you can help them with their situation.
        Clearly say: "You can share the forwarded message or type out your own."
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

        If the user agrees to for the tool, guide a short, interactive practice (2–4 steps) using micro-role-play, reflective rehearsal, or guided fill-in, depending on the tool and the user’s comfort.
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
    
def get_user_stage(user_id):
    """Retrieve the user's current stage from Redis."""
    stage = get_user_stage_r(user_id)
    if stage is None:
        set_user_stage_r(user_id, STAGES['GREETING'][0])
    return stage

def advance_stage(user_id: str):
    """Move the user to the next stage in the conversation flow."""
    current = get_user_stage(user_id)

    user_stages = STAGES[current][1] if current in STAGES else STAGES['GREETING'][0]

    if user_stages:
        set_user_stage_r(user_id, user_stages)

def find_stage(user_id, current_stage, text):
    """Find the current stage of the user."""
    if current_stage == "initial":
        return STAGES["GREETING"][0], 1
    
    if current_stage == STAGES["GREETING"][0]:
        return STAGES["GREETING"][1], 1
    
    if current_stage == STAGES["VALIDATION"][0]:
        return STAGES["VALIDATION"][1], 1
    
    if detect_tools_trigger(text) and current_stage in ["Reflection", "Next Steps"]:
        return STAGES["TOOLS"][0], 1
    
    stage_step = int(get_user_stage_step_r(user_id))
    if current_stage == STAGES["REFLECTION"][0] and stage_step > max_step[current_stage]:
        return STAGES["TOOLS"][0], 1
    
    if current_stage == STAGES["TOOLS"][0] and stage_step > max_step[current_stage]:
        return STAGES["NEXT_STEPS"], 1
    
    stage_step += 1

    return current_stage, stage_step

def build_messages(conversation, curr_stage, stage_step,user_id) -> list:
    """
    Build the structured OpenAI chat message list for the conversation.
    - Includes forwarded messages.
    - Includes previous assistant reply to avoid repetition.
    - Passes reflection turn info so LLM knows how many times reflection has occurred.
    """
    messages = []
    messages.append({"role": "user", "content": conversation})

    

    stage_prompt = STAGE_PROMPTS.get(curr_stage, "")

    # Reflection-specific enhancement
    if curr_stage == "Reflection":
        stage_prompt += (
            f"\nImportant: This is reflection turn {stage_step} out of {max_step[curr_stage]}.\n"
            "Do not repeat previous questions or rephrase earlier prompts. "
            "Build upon what the user has already shared. "
            "If reflection_turn >= max_reflection_turns, gently invite the user to try something practical."
        )
    elif curr_stage == "Validation":
        stage_prompt += (
            "\nImportant: Do NOT repeat or rephrase earlier questions. "
            "Build upon what the user has already shared."
        )
    elif curr_stage == "Tools":
        curr_tool = get_tools_r(user_id)
        messages.append({"role": "system", "content": stage_prompt})
        # if stage_step == 1:
        if curr_tool == "None":
            
            messages.append({
                        "role": "system",
                        "content": (
                            "You are in the Tools stage. Suggest ONE practical, evidence-based therapeutic tool "
                            "relevant to the user's situation. Keep tone conversational and concise."
                            "Do NOT suggest a second tool. Important: Do NOT repeat or rephrase earlier questions."
                            "If the user declines, end this stage gracefully with a warm acknowledgment."
                            "IMPORTANT: Add the following format at the last [tool_name=<tool_name>]. If user declines approach, suggest new tool with the format [tool_name=<tool_name>]."
                        )
                    })
        else:
            print("Current tool detected:", curr_tool)
            messages.append({
                "role": "system",
                "content": (f"The user is currently practicing '{curr_tool}'. "
                            "Do NOT suggest a new tool unless user reject the tool. Only guide them interactively through the next step. "
                            "Keep instructions short and supportive.")
                })

    if curr_stage != "Tools":
        messages.append({"role": "system", "content": stage_prompt})

    print(f"Built messages for stage {curr_stage} step {stage_step}:", messages)
    return messages