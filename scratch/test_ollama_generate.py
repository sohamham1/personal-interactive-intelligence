import httpx
import json

url = "http://localhost:11434/api/generate"
payload = {
    "model": "llama3.2:3b",
    "prompt": "Say hello in 3 words.",
    "stream": False
}

try:
    print("Calling Ollama generate...")
    r = httpx.post(url, json=payload, timeout=30.0)
    print("Status code:", r.status_code)
    print("Response JSON:")
    print(r.json())
except Exception as e:
    print("Error calling Ollama:", e)
