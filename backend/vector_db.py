"""Simple, pure-Python vector database using NumPy for Cosine Similarity.

Utilizes Gemini or OpenRouter API to fetch document/query embeddings.
Saves/loads embeddings from a local JSON file.
"""

import os
import json
import httpx
import numpy as np
from typing import List, Dict, Any, Optional

from .config import OPENROUTER_API_KEY, KNOWLEDGE_BASE_INDEX


def get_embedding(text: str) -> Optional[List[float]]:
    """Fetch text embedding from Gemini API or OpenRouter API based on key prefix."""
    if not OPENROUTER_API_KEY:
        print("[VectorDB] API Key not set. Cannot fetch embeddings.")
        return None

    # Clean text to prevent control character errors
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None

    # Check key format to determine routing
    is_gemini_direct = OPENROUTER_API_KEY.startswith("AIza")

    if is_gemini_direct:
        # Query Gemini API directly
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={OPENROUTER_API_KEY}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text}]
            }
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("embedding", {}).get("values")
        except Exception as e:
            print(f"[VectorDB] Gemini embedding error: {e}")
            return None
    else:
        # Query OpenRouter API (OpenAI compatibility)
        url = "https://openrouter.ai/api/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "google/gemini-embedding-001",
            "input": text
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # OpenRouter returns choices/embeddings in data['data'][0]['embedding']
                return data.get("data", [{}])[0].get("embedding")
        except Exception as e:
            print(f"[VectorDB] OpenRouter embedding error: {e}")
            return None


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(v1)
    b = np.array(v2)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class SimpleVectorDB:
    """Zero-dependency vector search engine using JSON storage."""

    def __init__(self, index_path: str = KNOWLEDGE_BASE_INDEX):
        self.index_path = index_path
        self.documents: List[Dict[str, Any]] = []
        self.load_index()

    def load_index(self):
        """Load document index from JSON file."""
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                print(f"[VectorDB] Loaded {len(self.documents)} chunks from index.")
            except Exception as e:
                print(f"[VectorDB] Error loading index: {e}")
                self.documents = []
        else:
            self.documents = []

    def save_index(self):
        """Save documents and embeddings to JSON file."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)
            print(f"[VectorDB] Saved {len(self.documents)} chunks to index.")
        except Exception as e:
            print(f"[VectorDB] Error saving index: {e}")

    def add_document(self, text: str, metadata: Dict[str, Any]) -> bool:
        """Fetch embedding and add document to the database."""
        emb = get_embedding(text)
        if emb is None:
            return False
        
        self.documents.append({
            "text": text,
            "metadata": metadata,
            "embedding": emb
        })
        return True

    def clear(self):
        """Clear database documents."""
        self.documents = []
        if os.path.exists(self.index_path):
            try:
                os.remove(self.index_path)
            except Exception:
                pass

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search top K relevant chunks using cosine similarity."""
        if not self.documents:
            print("[VectorDB] Database is empty.")
            return []

        query_emb = get_embedding(query)
        if query_emb is None:
            return []

        results = []
        for doc in self.documents:
            sim = cosine_similarity(query_emb, doc["embedding"])
            results.append({
                "text": doc["text"],
                "metadata": doc["metadata"],
                "score": sim
            })

        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    # Test CLI search
    import sys
    db = SimpleVectorDB()
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
        print(f"Searching for: '{query_text}'")
        res = db.search(query_text, top_k=2)
        for i, r in enumerate(res):
            print(f"\n[{i+1}] Score: {r['score']:.4f} (Source: {r['metadata'].get('source')})")
            print(r['text'])
    else:
        print("Usage: python -m backend.vector_db <search query>")
