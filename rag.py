from flask import Flask, request, jsonify
import faiss, pickle, numpy as np
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load FAISS + metadata
index = faiss.read_index("vector.index")
metadata = pickle.load(open("metadata.pkl", "rb"))

def search_docs(query, k=3):
    emb = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    ).data[0].embedding
    emb = np.array(emb).astype("float32").reshape(1, -1)
    D, I = index.search(emb, k)
    return [metadata[i] for i in I[0]], I[0]

@app.route("/ask", methods=["POST"])
def ask():
    data = request.json
    query = data.get("query") if data is not None else None

    soruce, idxs = search_docs(query)
    context = "\n\n".join([metadata[i]["content"] for i in idxs])

    response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an assistant helping to figure out his career path. use the context and provide a answer evaluating the real-world scenarios. If the answer is not in the context, say 'Not found in documents'."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
            ]
        )

    return jsonify({
            "answer": response.choices[0].message.content
        })


if __name__ == "__main__":
    app.run(debug=True)
