# Project 1: RAG Fixes + UI Updates

## Problems being solved

1. **Inconsistent retrieval** — same query returns different results on different runs
2. **Shallow retrieval** — broad queries ("love", "life") only surface 5 chunks, missing hundreds of relevant notes
3. **Poor chunking** — one note = one chunk means long notes are poorly represented
4. **Slow AI answers** — LLM generation latency is noticeable on every query
5. **UI: mode switching** — replace keyboard shortcuts with explicit mode toggle buttons
6. **UI: AI mode as default** — AI answer should be the default selected mode

---

## Fix 1: Chunking strategy overhaul

**File: `ingest/` — all ingest scripts**

### The problem

One note = one embedding vector. A 300-word Keep note gets a single vector that represents the average meaning of the whole note. When you query "pomegranate", if that word is one line in a long note about food and health, the note's overall embedding drifts away from the query and gets missed entirely.

### The fix: sliding window chunking with overlap

Replace the one-note-one-chunk approach with this chunking function, shared across all ingest scripts:

```python
# core/chunker.py

def chunk_text(text: str, source_id: str, metadata: dict,
               chunk_size: int = 150, overlap: int = 30) -> list[dict]:
    """
    Splits text into overlapping word-window chunks.
    Returns list of {text, source_id, chunk_index, metadata}
    
    chunk_size: 150 words (not tokens — simpler, fast enough)
    overlap: 30 words — ensures boundary context isn't lost
    """
    words = text.split()
    
    if len(words) <= chunk_size:
        # Short note: keep as single chunk, no splitting needed
        return [{
            "text": text,
            "source_id": source_id,
            "chunk_index": 0,
            "metadata": metadata
        }]
    
    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append({
            "text": chunk_text,
            "source_id": source_id,
            "chunk_index": idx,
            "metadata": metadata
        })
        start += chunk_size - overlap
        idx += 1
    
    return chunks
```

Apply `chunk_text()` in every ingest script before calling `embedder.embed()`.

### Special case: Twitter

Tweets are too short to chunk individually (avg 20 words). Keep the existing weekly grouping — group tweets by week into a single document, then pass that through `chunk_text()`. This way a week of 50 tweets gets 2-3 chunks instead of one giant vector.

### ChromaDB schema update

The `chunk_index` field must be stored in metadata so the retriever can group chunks from the same source when displaying results:

```python
# vectorstore.py — updated metadata structure
{
    "source": "keep",           # data source type
    "source_id": "note_abc123", # original note/document ID
    "chunk_index": 2,           # which chunk of that document
    "title": "...",             # original title if available
    "created_at": "...",        # original timestamp
    "url": "..."                # for bookmarks
}
```

### Re-ingestion

After updating chunking logic, the vector store must be rebuilt from scratch:

```bash
# Wipe existing ChromaDB collection
python -c "import chromadb; c = chromadb.PersistentClient('data/chroma_db'); c.delete_collection('personal_kb')"

# Re-run all ingest scripts
python ingest/ingest_keepnotes.py
python ingest/ingest_twitter.py
# etc.
```

---

## Fix 2: Retrieval depth — dynamic k

**File: `core/retriever.py`**

### The problem

Top 5 is hardcoded. "What have I said about love" has hundreds of relevant notes. The LLM sees 5 and summarises 5. The user experience feels like the system barely knows them.

### The fix: query-length-aware dynamic k

```python
# core/retriever.py

def retrieve(query: str) -> list[dict]:
    """
    Dynamic k based on query type:
    - Short/specific query (1-2 words): k=20, then deduplicate to top 10 unique sources
    - Longer/conversational query (3+ words): k=30, deduplicate to top 15 unique sources
    
    Deduplication: if multiple chunks from same source_id are retrieved,
    keep only the highest-scoring chunk per source, but include a
    `chunk_count` field so the LLM knows "there were 8 relevant notes,
    showing top 5 unique sources."
    """
    
    words = len(query.split())
    k = 30 if words >= 3 else 20
    
    raw_results = vectorstore.query(query, n_results=k)
    
    # Deduplicate: best chunk per source_id
    seen = {}
    for result in raw_results:
        sid = result["metadata"]["source_id"]
        if sid not in seen:
            seen[sid] = result
    
    deduped = list(seen.values())
    
    # Return top N unique sources
    limit = 15 if words >= 3 else 10
    return deduped[:limit]
```

### Context window note for the LLM prompt

Pass the total match count to the LLM so it can be honest in its answer:

```python
# api/server.py — updated prompt construction

total_matches = len(raw_results)
unique_sources = len(deduped)

prompt = f"""You are a personal knowledge assistant. The user is asking about their own notes, tweets, and saved content.

Retrieved {unique_sources} unique sources (from {total_matches} total matches) relevant to the query.

Sources:
{formatted_chunks}

Query: {query}

Answer directly and specifically. If there are many relevant notes, summarise the themes across them. Always mention the source types you drew from (keep, twitter, bookmark, etc.). Be concise — 3-5 sentences max."""
```

---

## Fix 3: Speed — reduce LLM latency

**File: `api/server.py`**

The LLM is slow because: (a) the context window passed to it is too large, and (b) streaming isn't being used properly so the user waits for the full response before seeing anything.

### Fix A: Cap context length

Before building the prompt, truncate each retrieved chunk to 100 words max. The LLM doesn't need the full chunk text — it needs enough to answer. This cuts context size by ~60%.

```python
def truncate_chunk(text: str, max_words: int = 100) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."
```

Apply to all chunks before building the prompt string.

### Fix B: Enable true streaming to the UI

The UI already handles streaming (blinking cursor, token-by-token rendering). Make sure the server is actually streaming:

```python
# api/server.py

from fastapi.responses import StreamingResponse
import httpx

@app.post("/query")
async def query(body: QueryRequest):
    chunks = retriever.retrieve(body.question)
    prompt = build_prompt(body.question, chunks)
    
    async def stream_ollama():
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", "http://localhost:11434/api/generate", json={
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": True
            }) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
                        if data.get("done"):
                            # Send source metadata as final JSON chunk
                            sources = [{"source": c["metadata"]["source"],
                                        "title": c["metadata"].get("title", ""),
                                        "created_at": c["metadata"].get("created_at", "")}
                                       for c in chunks[:5]]
                            yield f"\n\n__SOURCES__{json.dumps(sources)}"
                            break
    
    return StreamingResponse(stream_ollama(), media_type="text/plain")
```

The UI parses the `__SOURCES__` sentinel at the end to extract and render the source pills.

### Fix C: Warm up the model on server start

Ollama loads the model into memory on first use, which adds ~2-3 seconds to the first query cold start. Fix this by sending a dummy request at server startup:

```python
# api/server.py — on startup

@app.on_event("startup")
async def warm_up_model():
    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:11434/api/generate", json={
                "model": "llama3.2:3b",
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 1}  # generate exactly 1 token, just to load
            }, timeout=30)
    except Exception:
        pass  # if Ollama isn't running, fail silently
```

---

## Fix 4: UI — mode toggle buttons

**File: `ui/index.html` + `ui/app.js` + `ui/style.css`**

### Replace keyboard shortcut hints with explicit toggle

Remove the footer keyboard hint `⌘↵ ask AI`. Replace with two pill buttons that sit between the search input and the results area.

#### HTML (insert after `.search-row`, before `.results`)

```html
<div class="mode-toggle">
  <button class="mode-btn active" id="modeAI" onclick="setMode('ai')">
    ▸ answer with AI
  </button>
  <button class="mode-btn" id="modeSource" onclick="setMode('source')">
    ↗ open source
  </button>
</div>
```

#### CSS

```css
.mode-toggle {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.mode-btn {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 5px 12px;
  border-radius: 4px;
  border: 1px solid #2a2a2a;
  background: transparent;
  color: #555;
  cursor: pointer;
  letter-spacing: 0.04em;
  transition: all 0.1s;
}

.mode-btn:hover {
  border-color: #444;
  color: #888;
}

.mode-btn.active {
  border-color: #1a2e1a;
  background: #0a1a0a;
  color: #c8ffc8;
}
```

#### JS logic (app.js)

```javascript
let currentMode = 'ai'; // AI is default

function setMode(mode) {
  currentMode = mode;
  document.getElementById('modeAI').classList.toggle('active', mode === 'ai');
  document.getElementById('modeSource').classList.toggle('active', mode === 'source');
}

// On Enter key press in search input:
searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (currentMode === 'ai') {
      fireAIQuery(searchInput.value);
    } else {
      openActiveSource();
    }
  }
  // Arrow key nav stays the same
});
```

### Updated footer

Remove `⌘↵ ask AI` from the footer. Keep:

```
↑↓ navigate    ↵ confirm    esc clear
```

---

## Fix 5: Prompt quality

**File: `api/server.py`**

The current prompt is generic. Replace it with one that's tuned for personal notes retrieval:

```python
def build_prompt(query: str, chunks: list, total_matches: int) -> str:
    formatted = ""
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        source = meta.get("source", "unknown")
        created = meta.get("created_at", "")
        title = meta.get("title", "")
        text = truncate_chunk(chunk["text"])
        formatted += f"[{i+1}] ({source}{', ' + created if created else ''}{', ' + title if title else ''})\n{text}\n\n"
    
    return f"""You are a personal memory assistant. These are the user's own notes, tweets, and saved content — written by them or saved by them.

{total_matches} pieces of content matched this query. Here are the most relevant ones:

{formatted}
Question: {query}

Instructions:
- Answer as if you know this person well, because you're drawing from their own words
- If the query is broad (e.g. "what have I said about love"), identify themes across the sources
- Mention specific examples from the notes where relevant
- Be honest if coverage seems partial: "you have {total_matches} notes on this — here are the main themes"
- Do not make up content not present in the sources
- Keep the answer to 4-6 sentences"""
```

---

## Summary: what each fix addresses

| Issue | Fix |
|---|---|
| Pomegranate not found sometimes | Fix 1 (chunking) + Fix 2 (higher k) |
| "Love" only showing one result | Fix 2 (dynamic k + deduplication) |
| LLM feels slow | Fix 3A (shorter context) + Fix 3B (true streaming) + Fix 3C (warmup) |
| Keyboard shortcuts feel hidden | Fix 4 (mode toggle buttons) |
| AI mode not default | Fix 4 (default mode = 'ai') |
| Generic/dumb answers | Fix 5 (better prompt) |

---

## Order of implementation

Do these in order — each fix builds on the previous one:

1. `core/chunker.py` — write shared chunking utility
2. Update all ingest scripts to use `chunk_text()`
3. Wipe and re-ingest the vector store
4. `core/retriever.py` — dynamic k + deduplication
5. `api/server.py` — streaming response + warmup + new prompt + context truncation
6. `ui/` — mode toggle buttons, update app.js default mode, clean up footer
