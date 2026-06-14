import httpx
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generates vector embeddings for a list of texts in a single batch call.
    """
    if not texts:
        return []
        
    # Filter out empty or whitespace-only texts to avoid API issues,
    # but keep track of indices to return aligned lists.
    url = f"{OLLAMA_BASE_URL}/api/embed"
    payload = {
        "model": EMBEDDING_MODEL,
        "input": texts
    }
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["embeddings"]
    except Exception as e:
        print(f"Error calling Ollama batch embed API: {e}")
        raise e

def embed(text: str) -> list[float]:
    """
    Generates a vector embedding for the given single text.
    """
    if not text or not text.strip():
        return []
    try:
        embeddings = embed_batch([text])
        return embeddings[0] if embeddings else []
    except Exception as e:
        print(f"Error embedding single text: {e}")
        raise e
