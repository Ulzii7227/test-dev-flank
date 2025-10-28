import os
import faiss
import pickle
from openai import OpenAI
import tiktoken
import numpy as np
from dotenv import load_dotenv

load_dotenv()

print("Building FAISS index...")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_chunks(text, chunk_size=500, overlap=50):
    words = text.split()
    for i in range(0, len(words), chunk_size - overlap):
        yield " ".join(words[i:i + chunk_size])

def build_faiss_index(folder="docs"):
    texts, metadata = [], []
    for file in os.listdir(folder):
        with open(os.path.join(folder, file), "r", encoding="utf-8") as f:
            content = f.read()
            for chunk in get_chunks(content):
                texts.append(chunk)
                metadata.append({
                    "source": file,
                    "content": chunk  # store actual text chunk
                })

    # create embeddings
    embeddings = []
    for txt in texts:
        resp = client.embeddings.create(
            model="text-embedding-3-small", # free-tier friendly
            input=txt
        )
        embeddings.append(resp.data[0].embedding)

    # store in FAISS
    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(embeddings, dtype="float32"))

    faiss.write_index(index, "vector.index")
    with open("metadata.pkl", "wb") as f:
        pickle.dump(metadata, f)

if __name__ == "__main__":
    build_faiss_index()