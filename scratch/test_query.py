import urllib.request
import json
import sys

url = "http://localhost:8001/query"
data = {
    "question": "What is ambition?",
    "conversation_id": None,
    "mode": "ai",
    "k": 15
}
headers = {"Content-Type": "application/json"}

req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)

            chunk = response.read(1024)
            if not chunk:
                break
            print(chunk.decode("utf-8", errors="ignore"), end="")
except Exception as e:
    print(f"Error occurred: {e}", file=sys.stderr)
    if hasattr(e, "read"):
        print(f"Server response error body: {e.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
