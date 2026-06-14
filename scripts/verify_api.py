# scripts/verify_api.py

import os
import sys
import httpx

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db

def test_endpoints():
    print("Initializing Database tables (in case)...")
    init_db()
    
    print("Verifying server endpoints locally by running direct queries...")
    
    # We can test the functions directly or run a temporary server thread.
    # To be extremely simple and robust, let's query the local uvicorn server if it's running.
    # If not running, we'll try to run direct function tests.
    
    try:
        r = httpx.get("http://localhost:8000/status", timeout=2.0)
        print("FastAPI local server is RUNNING.")
        print(f"/status: {r.status_code} - {r.json()}")
        
        r_greet = httpx.get("http://localhost:8000/greeting")
        print(f"/greeting: {r_greet.status_code} - {r_greet.json()}")
        
        r_search = httpx.get("http://localhost:8000/search?q=love")
        print(f"/search (love): {r_search.status_code} - Retrieved {len(r_search.json())} items.")
        
        r_fts = httpx.get("http://localhost:8000/search/source?q=love")
        print(f"/search/source (love): {r_fts.status_code} - Total FTS matches: {r_fts.json().get('total')}")
        
    except (httpx.ConnectError, httpx.HTTPError) as e:
        print(f"FastAPI local server is not accessible ({e}). Testing components directly via Python imports...")
        
        from core.search import retrieve
        from core.ollama import check_ollama, check_model
        
        print("Testing check_ollama()...")
        import asyncio
        loop = asyncio.get_event_loop()
        ollama_res = loop.run_until_complete(check_ollama())
        print(f"Ollama running check: {ollama_res}")
        
        print("Testing check_model()...")
        model_res = loop.run_until_complete(check_model())
        print(f"Model llama3.2:3b check: {model_res}")
        
        print("Testing hybrid retriever on query 'love'...")
        results = retrieve("love", n_results=5)
        print(f"Retrieved {len(results)} chunks. Total matches in index: {results.total_matches}")
        if results:
            print("Sample match title:", results[0]["metadata"].get("title"))

if __name__ == "__main__":
    test_endpoints()
