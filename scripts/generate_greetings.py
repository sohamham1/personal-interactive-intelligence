# scripts/generate_greetings.py

import os
import sys
import json
import httpx
import random

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vectorstore import VectorStore
from core.embedder import OLLAMA_BASE_URL

USER_NAME = os.getenv("USER_NAME", "User")
USER_BIO = os.getenv("USER_BIO", "a tech enthusiast and thinker who likes to keep notes and document ideas")
USER_TOPICS = os.getenv("USER_TOPICS", "writing, projects, learning, ambition, life, ideas")

GREETING_PROMPT = """
You are generating personalised home screen greetings and suggested prompt questions for {user_name}'s personal knowledge base app.
The user is {user_name} — {user_bio}.

Here are some samples from their notes and tweets:
{sample_chunks}

Generate exactly 30 greetings and exactly 10 suggested prompts.
Return ONLY a valid JSON object matching this structure (no markdown fences, no preamble):
{{
  "greetings": [
     {{
       "time": "morning",
       "greeting": "Good morning, {user_name}.",
       "subline": "another day, another opportunity to build something cool.",
       "mood": "funny"
     }},
     ... (exactly 30 items) ...
  ],
  "suggested_prompts": [
     "what have I written about ambition?",
     "find my notes on a specific project",
     "what are my main goals?",
     ... (exactly 10 items) ...
  ]
}}

Rules for greetings:
- "time" must be one of: "morning", "afternoon", "evening", "night", "any"
- "mood" must be one of: "warm", "funny", "reflective", "motivating", "random"
- Never be cringe or overly motivational
- Dry > wholesome
- Occasionally (not always) reference something specific from the sample notes
- Keep sublines under 12 words
- No em dashes
- Mix of all time slots and moods

Rules for suggested prompts:
- Must be interesting questions that {user_name} would ask their knowledge base
- Should cover topics like: {user_topics}
- Kept short and engaging (under 8 words)
"""

def generate():
    print("Initializing VectorStore to pull sample chunks...")
    db = VectorStore()
    count = db.get_count()
    print(f"Total documents in ChromaDB: {count}")
    
    sample_texts = []
    if count > 0:
        try:
            res = db.collection.get(limit=min(200, count))
            docs = res.get("documents", [])
            if docs:
                sample_texts = random.sample(docs, min(20, len(docs)))
        except Exception as e:
            print(f"Error getting chunks: {e}")
            
    sample_str = "\n---\n".join(sample_texts) if sample_texts else "No sample notes available."
    
    prompt = GREETING_PROMPT.format(
        user_name=USER_NAME,
        user_bio=USER_BIO,
        user_topics=USER_TOPICS,
        sample_chunks=sample_str
    )
    
    print("Calling Ollama to generate greetings (this can take up to 30 seconds)...")
    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": "llama3.2:3b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }
            )
            response.raise_for_status()
            response_data = response.json()
            response_text = response_data.get("response", "").strip()
            
            # Clean markdown code fences if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parse JSON
            parsed = json.loads(response_text)
            
            # Validate structure
            greetings = parsed.get("greetings", [])
            prompts = parsed.get("suggested_prompts", [])
            print(f"Generated {len(greetings)} greetings and {len(prompts)} suggested prompts.")
            
            # Save to file
            os.makedirs("data", exist_ok=True)
            output_file = "data/greetings.json"
            with open(output_file, "w") as f:
                json.dump(parsed, f, indent=2)
                
            print(f"Generated {len(greetings)} greetings → {output_file}")
            
    except Exception as e:
        print(f"Failed to generate greetings: {e}")
        # Write default file if we failed
        fallback_data = {
            "greetings": [
                {"time": "morning", "greeting": f"Good morning, {USER_NAME}.", "subline": "Let's check the notes.", "mood": "warm"},
                {"time": "afternoon", "greeting": f"Good afternoon, {USER_NAME}.", "subline": "Hope the day is going well.", "mood": "warm"},
                {"time": "evening", "greeting": f"Good evening, {USER_NAME}.", "subline": "Time to reflect.", "mood": "reflective"},
                {"time": "night", "greeting": f"Good night, {USER_NAME}.", "subline": "Still coding or reading?", "mood": "funny"}
            ],
            "suggested_prompts": [
                "what are my key projects?",
                "what notes do I have on startup ideas?",
                "summarize my recent thoughts",
                "what have I written about ambition?",
                "what do I think about love?",
                "my goals for this month"
            ]
        }
        output_file = "data/greetings.json"
        os.makedirs("data", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(fallback_data, f, indent=2)
        print(f"Wrote fallback greetings to {output_file}")

if __name__ == "__main__":
    generate()
