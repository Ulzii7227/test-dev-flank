import os
import json
import pickle
import re
import faiss
import numpy as np
import openai
import logging

from service.redis import detect_tools_r, set_user_stage_r

logger = logging.getLogger("handlers")

from prompt_engine.user_stage import build_messages, find_stage, get_user_stage

# ------------------ CONFIG ------------------
openai.api_key = os.getenv("OPENAI_API_KEY")

PROMPT_PATH = "prompt_engine/prompt.txt"
JSONL_PATH = "prompt_engine/emotional_support_knowledge.jsonl"
INDEX_PATH = "prompt_engine/faiss_index.bin"
VECTORS_PATH = "prompt_engine/vectors.pkl"
EMBED_MODEL = "text-embedding-3-small"

# ------------------ FAISS INDEX ------------------
def build_faiss_index_jsonl():
    """Load FAISS index + data if exists, otherwise build from JSONL."""
    if os.path.exists(INDEX_PATH) and os.path.exists(VECTORS_PATH):
        index = faiss.read_index(INDEX_PATH)
        with open(VECTORS_PATH, "rb") as f:
            data = pickle.load(f)
        print("✅ FAISS JSONL index loaded")
        return index, data

    # Build index from scratch
    data = []
    texts = []
    if not os.path.exists(JSONL_PATH):
        raise FileNotFoundError(f"{JSONL_PATH} not found. Add your JSONL RAG knowledge.")

    with open(JSONL_PATH, "r") as f:
        for line in f:
            obj = json.loads(line.strip())
            data.append(obj)
            texts.append(f"{obj['situation']} - {obj['response']}")

    embeddings = []
    for t in texts:
        emb = openai.embeddings.create(model=EMBED_MODEL, input=t).data[0].embedding
        embeddings.append(np.array(emb, dtype=np.float32))

    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.vstack(embeddings))

    os.makedirs(os.path.dirname(VECTORS_PATH), exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    with open(VECTORS_PATH, "wb") as f:
        pickle.dump(data, f)

    print("✅ FAISS JSONL index built")
    return index, data

def retrieve_context_jsonl(query, index, data, top_k=3):
    """Retrieve top-k emotional responses for the query."""
    q_emb = openai.embeddings.create(model=EMBED_MODEL, input=query).data[0].embedding
    D, I = index.search(np.array([q_emb], dtype=np.float32), top_k)
    return "\n".join([data[i]['response'] for i in I[0]])


# ------------------ MAIN PROMPT FUNCTION ------------------
def prompt_LLM(user_id, conversation, current_convo=""):
    print(f"💬 Prompting model for user {user_id}", conversation)

    # Load RAG / FAISS
    index, data = build_faiss_index_jsonl()

    # Retrieve top relevant emotional support responses
    # context_text = retrieve_context_jsonl(conversation, index, data)
    # print(f"🧠 Retrieved RAG context for user {user_id}:", context_text)

    if "Hello" in current_convo or "Hi" in current_convo or "Hey" in current_convo:
        set_user_stage_r(user_id, "initial", 1)
    elif "<1>" in conversation:
        set_user_stage_r(user_id, "Greeting", 1)
    # Load refined prompt
    if not os.path.exists(PROMPT_PATH):
        raise FileNotFoundError(f"{PROMPT_PATH} not found. Add refined prompt.txt.")
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    # Append RAG context to system prompt
    # system_prompt += f"\n\nRelevant emotional context from knowledge base:\n{context_text}"

    # Prompting stages
    stage = get_user_stage(user_id)
    logger.info(f"User {user_id} at old stage {stage}")
    curr_stage, stage_step = find_stage(user_id, stage, current_convo)
    logger.info(f"User {user_id} at stage {curr_stage}")
    set_user_stage_r(user_id, curr_stage, stage_step)

    # Build the chat messages
    message = build_messages(conversation, curr_stage, stage_step,user_id)

    logger.info(f"User {user_id} at stage {curr_stage}")
    # Attempt GPT-4o-mini can add fallback logic here
    model_list = ["gpt-4o-mini"]
    for model_name in model_list:
        try:
            response = openai.chat.completions.create(
                model=model_name,
                messages=message,
                temperature=0.8,
                max_tokens=300
            )

            total_tokens = response.usage.total_tokens
            answer = response.choices[0].message.content.strip()
            detect_tools_r(answer,user_id)
            return answer, total_tokens
        except openai.error.InvalidRequestError as e:
            print(f"⚠️ Model {model_name} unavailable, trying next. {str(e)}")
        except openai.error.OpenAIError as e:
            print(f"⚠️ OpenAI API error: {str(e)}")
            break

    return "Sorry, the model is temporarily unavailable. Please try again later.", 0
