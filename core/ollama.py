# core/ollama.py

import httpx

async def check_ollama() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://localhost:11434")
            if r.status_code == 200:
                return {"running": True, "error": None}
    except httpx.ConnectError:
        return {"running": False, "error": "ollama_not_running"}
    except httpx.TimeoutException:
        return {"running": False, "error": "ollama_timeout"}
    return {"running": False, "error": "ollama_unknown"}

async def check_model(model: str = "llama3.2:3b") -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if any(model in m for m in models):
                    return {"available": True, "error": None}
                return {"available": False, "error": f"model_{model}_not_pulled"}
            return {"available": False, "error": f"status_code_{r.status_code}"}
    except Exception as e:
        return {"available": False, "error": str(e)}
