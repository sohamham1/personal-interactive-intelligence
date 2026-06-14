import sys
import asyncio
import httpx

# Add project root to path
sys.path.append(".")

from core.search import retrieve
from core.ollama import check_ollama, check_model

async def test():
    try:
        print("Checking Ollama status...")
        status = await check_ollama()
        print("Ollama status:", status)
        
        print("\nChecking model status...")
        model_status = await check_model()
        print("Model status:", model_status)
        
        print("\nRetrieving chunks for query 'ambition'...")
        chunks = retrieve("ambition", n_results=15)
        print(f"Retrieved {len(chunks)} chunks.")
        for i, c in enumerate(chunks[:3]):
            print(f"Chunk {i+1}: ID={c['id']}, Source={c['metadata'].get('source')}")
            print("Text preview:", c['text'][:100])
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
