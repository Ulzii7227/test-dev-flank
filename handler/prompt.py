import os
import json
import pickle
import re
import faiss
import numpy as np
import openai

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

# ------------------ CONVERSATION PARSING ------------------
def parse_conversation(conversation):
    """Parse <1>/<2>/<3> tags into friend, user, and current messages."""
    friend_msgs, user_msgs, current_msgs,  = [], [], []
    for line in conversation.strip().splitlines():
        if line.startswith("<1>"):
            friend_msgs.append(line.replace("<1>", "").strip())
        elif line.startswith("<2>"):
            user_msgs.append(line.replace("<2>", "").strip())
        elif line.startswith("<3>"):
            current_msgs.append(line.replace("<3>", "").strip())
        else:
            bot_messages = re.findall(r"<bot>(.*)", line)
            for msg in bot_messages:
                current_msgs.append(msg.strip())
                
    return friend_msgs, user_msgs, current_msgs

# ------------------ MAIN PROMPT FUNCTION ------------------
def prompt_LLM(user_id, conversation):
    print(f"💬 Prompting model for user {user_id}", conversation)

    # Load RAG / FAISS
    index, data = build_faiss_index_jsonl()

    # Retrieve top relevant emotional support responses
    context_text = retrieve_context_jsonl(conversation, index, data)

    # Load refined prompt
    if not os.path.exists(PROMPT_PATH):
        raise FileNotFoundError(f"{PROMPT_PATH} not found. Add refined prompt.txt.")
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    # Append RAG context to system prompt
    system_prompt += f"\n\nRelevant emotional context from knowledge base:\n{context_text}"

    # Attempt GPT-4o-mini can add fallback logic here
    model_list = ["gpt-4o-mini"]
    for model_name in model_list:
        try:
            response = openai.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Hi, I’m Flank. The user says:\n{conversation}"}
                ],
                temperature=0.8,
                max_tokens=300
            )

            total_tokens = response.usage.total_tokens
            answer = response.choices[0].message.content.strip()
            return answer, total_tokens
        except openai.error.InvalidRequestError as e:
            print(f"⚠️ Model {model_name} unavailable, trying next. {str(e)}")
        except openai.error.OpenAIError as e:
            print(f"⚠️ OpenAI API error: {str(e)}")
            break

    return "Sorry, the model is temporarily unavailable. Please try again later.", 0
