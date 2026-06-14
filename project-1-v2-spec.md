# Personal KB — v2 Spec
## For: Antigravity Coding Agent

This document outlines all changes to be made to the existing Personal KB project. Read the entire document before writing a single line of code. Changes span the UI, backend, RAG pipeline, and data architecture. Some changes require schema migrations.

---

## Environment context

- **OS:** Windows
- **Server:** FastAPI + uvicorn, running locally on port 8000
- **Virtual env:** `venv\Scripts\python.exe` in project root
- **Models:** Ollama running locally — `llama3.2:3b` (LLM) + `nomic-embed-text` (embeddings)
- **Vector store:** ChromaDB (persistent, file-based)
- **Frontend:** Plain HTML/CSS/JS, no framework

---

## 1. Home screen redesign — Claude/Perplexity style

### What to build

Replace the current blank state (empty search box on a dark screen) with a proper home screen that renders when the input is empty and no conversation is active. It should feel like Claude's home screen — centred greeting, suggested prompts, warm tone.

### Layout

```
┌─────────────────────────────────────────┐
│  PERSONAL KB              ● 2,693 · 3b  │  ← top bar unchanged
├─────────────────────────────────────────┤
│                                         │
│                                         │
│         Good evening, Soham.            │  ← greeting (large, #c8ffc8)
│         what's on your mind?            │  ← subline (#555)
│                                         │
│  [ suggested prompt ]  [ suggested ]    │  ← 3–4 chips
│  [ suggested prompt ]                   │
│                                         │
│  ───────────────────────────────────    │  ← divider
│                                         │
│  › [search input]              Ctrl+K   │  ← search, always visible
│                                         │
│  [ ▸ answer with AI ]  [ ↗ open source ]│  ← mode toggle
│                                         │
└─────────────────────────────────────────┘
```

When the user types or selects a conversation from the sidebar, the home screen slides away and the results/conversation view takes over.

### Personalised greetings

**Do not generate greetings on every page load.** Generate a batch of 30 greetings once (on first run or when the user triggers a refresh), store them in a JSON file, and serve them from disk forever. Generation uses the LLM + a sample of ingested content.

#### Generation script: `scripts/generate_greetings.py`

```python
# 1. Pull 20 random chunks from ChromaDB (diverse sources — keep, twitter, etc.)
# 2. Send to LLM with this prompt:
GREETING_PROMPT = """
You are generating personalised home screen greetings for a personal knowledge base app.
The user is Soham — a 20-something from Mumbai, funny, dry humour, works in tech/startups, 
writes comedy, watches a lot of films, works out, thinks a lot.

Here are some samples from his notes and tweets:
{sample_chunks}

Generate exactly 30 greetings. Each greeting is a JSON object with:
- "time": one of "morning", "afternoon", "evening", "night", "any"
- "greeting": the main line (e.g. "Good morning, Soham.")
- "subline": a second line — warm, funny, occasionally referencing something from his notes/life
- "mood": one of "warm", "funny", "reflective", "motivating", "random"

Rules:
- Never be cringe or overly motivational
- Dry > wholesome
- Occasionally (not always) reference something specific from the sample notes
- Keep sublines under 12 words
- No em dashes
- Mix of all time slots and moods

Return ONLY a valid JSON array. No preamble, no markdown fences.
"""
# 3. Parse JSON, save to data/greetings.json
# 4. Log: "Generated 30 greetings → data/greetings.json"
```

`data/greetings.json` is gitignored (it may reference personal note content).

#### Serving greetings: `api/server.py`

```python
GET /greeting
# Logic:
# 1. Load data/greetings.json
# 2. Get current hour → map to time slot:
#    5–11 = morning, 12–16 = afternoon, 17–20 = evening, 21–4 = night
# 3. Filter greetings matching time slot OR "any"
# 4. Pick one at random — but track last 5 served (store in data/greeting_state.json)
#    to avoid repeating. Reset when all have been shown.
# 5. Return { greeting, subline, mood }
```

#### Suggested prompt chips

On home screen, show 3–4 suggested query chips below the greeting. These are generated alongside greetings and stored in `data/greetings.json` as a `suggested_prompts` array (10 total, pick 3 random each load).

Examples of good suggested prompts based on Soham's content:
- "what have I written about ambition?"
- "find my notes on a specific company or person"
- "what films did I want to watch?"
- "what do I think about love?"

Clicking a chip populates the search input and fires the query in the current mode.

---

## 2. Conversation history — sidebar like Claude

### Architecture

Store conversations in SQLite (same DB as LinkMemory pattern, or a new `data/kb.db`). A conversation is a series of turns: user query → AI response + sources retrieved.

#### Schema additions to `data/kb.db`

```sql
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,  -- UUID
    title       TEXT,              -- auto-generated from first query (truncated to 50 chars)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE turns (
    id              TEXT PRIMARY KEY,  -- UUID
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    query           TEXT NOT NULL,
    answer          TEXT,              -- full AI answer text, null if open-source mode
    mode            TEXT NOT NULL,     -- "ai" or "source"
    sources         TEXT,              -- JSON array of source metadata
    created_at      TEXT NOT NULL
);
```

Keep last **50 conversations** max. When a new conversation is created and count > 50, delete the oldest by `updated_at`.

#### New API endpoints

```
GET  /conversations                     → list of {id, title, updated_at}, newest first, limit 50
GET  /conversations/{id}                → full conversation: {id, title, turns: [...]}
POST /conversations                     → create new conversation, returns {id}
DELETE /conversations/{id}              → delete conversation + all its turns
```

Modify `POST /query` to accept an optional `conversation_id`. If provided, append the turn to that conversation. If not provided, create a new conversation and return its ID in the response header (`X-Conversation-Id`).

#### UI: sidebar

Add a left sidebar to the layout, collapsed by default, toggleable via a `≡` button in the top bar.

```
┌──────────────────┬──────────────────────────────────────┐
│ ≡  PERSONAL KB   │                              ● 2,693  │
├──────────────────┼──────────────────────────────────────┤
│                  │                                      │
│  today           │         Good evening, Soham.         │
│  › pomegranates  │         what's on your mind?         │
│  › love          │                                      │
│                  │  [suggested]  [suggested]  [suggested]│
│  yesterday       │                                      │
│  › sleep notes   │  ──────────────────────────────────  │
│  › ambition      │  › [                        ] Ctrl+K │
│                  │                                      │
│  + new chat      │  [▸ answer with AI] [↗ open source]  │
│                  │                                      │
└──────────────────┴──────────────────────────────────────┘
```

Sidebar specs:
- Width: 200px when open, 0 when closed (CSS transition)
- Background: `#0a0a0a`, right border: 1px `#1a1a1a`
- Section labels ("today", "yesterday", "earlier"): 9px uppercase `#444`
- Conversation items: 11px `#555`, hover `#888`, active `#c8ffc8`
- Active conversation: left border 2px `#c8ffc8`, background `#111`
- `+ new chat` button at bottom: 10px, `#444`, hover `#c8ffc8`
- `≡` toggle button in top bar: leftmost element, `#555`, hover `#888`

When a conversation is clicked, load all its turns and render them in sequence in the main area (query → answer → sources, repeated for each turn). The search input at the bottom continues that conversation.

Multi-turn conversation context: when sending a new query in an existing conversation, send the last 3 turns as context to the LLM:

```python
context = "\n\n".join([
    f"User: {t['query']}\nAssistant: {t['answer']}"
    for t in last_3_turns if t['answer']
])
prompt = f"Previous context:\n{context}\n\nCurrent question: {query}\n\nSources:\n{chunks}"
```

---

## 3. RAG overhaul — retrieval quality

### 3a. The core problem

The current setup retrieves top 5 chunks and passes them verbatim to the LLM. This fails for:
- Broad queries ("love", "dancing") — too few chunks
- Exact phrase queries ("she say do you love me") — semantic search misses exact matches
- Deep-dive queries (all notes on a company/founder) — needs exhaustive retrieval, not sampling

### 3b. Hybrid search — BM25 + semantic, always both

**File: `core/search.py`** (new file, replaces retriever.py logic)

The new retrieval pipeline runs two searches in parallel and merges results:

```python
# 1. Semantic search via ChromaDB (existing)
# 2. BM25 keyword search via SQLite FTS5 (exact + fuzzy keyword matching)
# Merge with Reciprocal Rank Fusion (RRF):
#   score = 1/(k + rank_semantic) + 1/(k + rank_bm25), k=60
# Deduplicate by source_id, keep highest RRF score per source
# Return merged, sorted list
```

Install: `pip install rank-bm25` for the BM25 index, OR use SQLite FTS5 (already available, preferred — no new dependency).

Use FTS5 for BM25. The `links_fts` virtual table already exists for bookmarks — create an equivalent for notes:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title,
    body,
    source,
    content='notes',
    content_rowid='rowid'
);
```

Add a `notes` table to `kb.db` that mirrors what's in ChromaDB but is optimised for FTS:

```sql
CREATE TABLE IF NOT EXISTS notes (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT UNIQUE,        -- ChromaDB chunk ID
    source_id   TEXT,               -- original note/doc ID
    source      TEXT,               -- keep, twitter, bookmark, etc.
    title       TEXT,
    body        TEXT,               -- chunk text
    created_at  TEXT,
    url         TEXT
);
```

Populate this table during ingest (alongside ChromaDB). Keep them in sync.

### 3c. Dynamic retrieval depth by query type

```python
def get_retrieval_params(query: str) -> dict:
    words = query.split()
    
    # Exact phrase query (quoted or short phrase likely to be verbatim)
    # Detection: query is 3–8 words AND contains common lyric/quote patterns
    # OR user wraps in quotes: "she say do you love me"
    if query.startswith('"') and query.endswith('"'):
        return {"k": 200, "mode": "exact", "dedupe": False}
    
    # Broad/thematic query (1–2 words or clearly thematic)
    if len(words) <= 2:
        return {"k": 50, "mode": "hybrid", "dedupe": True, "max_unique": 30}
    
    # Deep-dive query (specific entity — person, company, topic)
    # Heuristic: 3–6 words, no question words
    if len(words) <= 6 and not any(w in query.lower() for w in ["what", "how", "why", "when", "did i"]):
        return {"k": 100, "mode": "hybrid", "dedupe": True, "max_unique": 50}
    
    # Conversational / question query
    return {"k": 30, "mode": "hybrid", "dedupe": True, "max_unique": 15}
```

### 3d. Verbatim mode vs AI summary mode

Add a third mode to the UI: **verbatim**. This sits alongside "answer with AI" and "open source".

```
[ ▸ answer with AI ]   [ " verbatim ]   [ ↗ open source ]
```

**Verbatim mode behaviour:**
- Retrieves chunks (using dynamic k above)
- Does NOT send to LLM
- Displays results as structured sections, preserving the user's exact words
- Groups by source_id (so a long note with 3 matching chunks appears as one block)
- Shows full chunk text, not truncated
- Links to original source at the bottom of each block

This is the mode for the VC use case ("everything I've written about this company") and the creative strategist use case ("all my ideas about dancing").

**Verbatim output format in UI:**

```
" VERBATIM — 12 passages across 8 sources

━━━ keep · food ideas · nov 2024 ━━━━━━━━━━━━━━━━━━━
[full chunk text, exact words, no summarisation]
[if multiple chunks from same note, render them in sequence]
↗ open original

━━━ twitter · week of apr 14 ━━━━━━━━━━━━━━━━━━━━━━━
[tweet text]
↗ open original

━━━ bookmark · article title ━━━━━━━━━━━━━━━━━━━━━━━
[saved snippet]
↗ open original
```

Each section header: 10px, `#4ade80`, `━` separators in `#2a2a2a`.
Chunk text: 12px, `#c8ffc8` (same as AI answer text — verbatim gets the green too).
Source link: 9px, `#555`, hover `#888`.

**AI summary mode** (existing "answer with AI") should explicitly instruct the LLM:

```
You are summarising the user's own notes. Be concise (4–8 sentences).
Reference specific examples. Do not fabricate anything not in the sources.
```

---

## 4. Open source mode — pure text search (no AI, no embeddings)

Open source mode must be completely decoupled from the AI/embedding pipeline. It is a Ctrl+F over notes, like Google Keep's native search.

### What it does

- Queries only the `notes_fts` FTS5 table (full-text search)
- No ChromaDB call
- No LLM call
- No embedding lookup
- Returns results ranked by FTS5 relevance score
- Works fully offline, instantly

### Pagination for large result sets

For queries that return many results (e.g. "she say do you love me" across 300 notes), implement cursor-based pagination:

```
GET /search/source?q=she+say+do+you+love+me&limit=20&offset=0
→ returns { results: [...], total: 312, has_more: true, next_offset: 20 }
```

UI renders a "load more" button at the bottom of the results grid:

```
showing 20 of 312 results
[ load more ]
```

`load more` appends the next 20 cards to the existing grid (no full re-render). This is a simple offset-based append, no infinite scroll complexity needed.

### Source filter toggle

Open source mode gets its own source filter, independent of the AI mode filters. Three options rendered as toggle buttons:

```
[ all ]  [ notes ]  [ tweets ]
```

- `notes` = sources: keep, markdown, pdf, notion
- `tweets` = source: twitter
- `all` = everything

These map to a `source_group` param: `GET /search/source?q=...&source_group=notes`

### Result display in open source mode

Cards show matched text with the query terms highlighted. No answer block, no AI section, no mode toggle visible (the toggle is above — user already chose "open source").

---

## 5. Card visibility — show/hide notes section

Currently notes appear automatically after every query. Change this:

- After an AI query: show answer block only. Notes section is hidden by default.
- A toggle button appears below the answer block: `[ show sources (12) ]`
- Clicking it expands the card grid below
- Button text changes to `[ hide sources ]`
- State persists per-conversation-turn (if sources were shown for turn 3, they stay shown when you scroll back to turn 3)

For verbatim mode: sources are always shown (that's the whole point).
For open source mode: sources are always shown (that's the whole point).

```
▸ ANSWER
[answer text]
[source tags]

[ show sources (12) ]     ← collapsed by default
```

---

## 6. Error handling — network errors and Ollama status

### The actual problem

The "network error" on AI queries is almost certainly one of:
1. Ollama process not running when the query fires
2. The model isn't loaded yet (cold start timeout)
3. The FastAPI server isn't running (less likely since search works)
4. Windows firewall blocking localhost:11434

### Fix A: Ollama health check before every AI query

```python
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
            models = [m["name"] for m in r.json().get("models", [])]
            if any(model in m for m in models):
                return {"available": True}
            return {"available": False, "error": f"model_{model}_not_pulled"}
    except Exception as e:
        return {"available": False, "error": str(e)}
```

Run both checks at server startup and expose via `/status`. Run `check_ollama()` before every `/query` call.

### Fix B: Specific, actionable error messages in the UI

Replace `[error executing query: network error]` with specific messages:

| Error | UI message |
|---|---|
| Ollama not running | `ollama isn't running — start it with: ollama serve` |
| Model not pulled | `model not found — run: ollama pull llama3.2:3b` |
| Server timeout | `ollama timed out — it may be loading the model, try again in 5s` |
| FastAPI server down | `local server offline — run: venv\Scripts\python.exe -m uvicorn api.server:app --port 8000` |
| Generic 500 | `something went wrong (500) — check the terminal for errors` |

Error messages appear in the answer block area, in `#ff4444`, styled like:

```
▸ ERROR
ollama isn't running — start it with: ollama serve
```

### Fix C: Top bar reflects live Ollama status

The top bar status dot already shows online/offline. Extend it:

- Page load: check `/status` → set dot colour
- Every 30 seconds: re-check `/status` in background → update dot
- If dot turns red mid-session, show a non-blocking toast at bottom: `ollama went offline`

### Fix D: Windows-specific note in README

Add a troubleshooting section to README:

```markdown
## Troubleshooting on Windows

If you get network errors on AI queries:

1. Open a terminal and run: `ollama serve`
   - Ollama on Windows doesn't always auto-start as a service
   - Keep this terminal open while using the app

2. Verify Ollama is running: open http://localhost:11434 in your browser
   - Should show: "Ollama is running"

3. If Windows Defender / firewall blocks it:
   - Allow ollama.exe through Windows Defender Firewall
   - Or temporarily disable firewall to test

4. Cold start: the first query after starting Ollama takes 3–5 seconds
   - The model is being loaded into memory
   - Subsequent queries are faster
```

---

## 7. UI updates summary

### Mode toggle — now three modes

```
[ ▸ answer with AI ]   [ " verbatim ]   [ ↗ open source ]
```

- All three are pill buttons, same style as before
- Default active: `answer with AI`
- `verbatim` uses the same `"` quote character to signal "exact words"

### Updated footer

```
↑↓ navigate    space open note    esc clear    ≡ history
```

Remove the `⌘↵ ask AI` hint (replaced by mode buttons). Add `≡ history` hint.

### Updated layout with sidebar

```
┌────┬──────────────────────────────────────────────────────┐
│    │  ≡  PERSONAL KB                        ● 2,693 · 3b  │
│    ├──────────────────────────────────────────────────────┤
│ S  │                                                      │
│ I  │  [home screen or conversation view]                  │
│ D  │                                                      │
│ E  │  ──────────────────────────────────────────────────  │
│ B  │  › [search input]                          Ctrl+K    │
│ A  │  [▸ answer with AI] [" verbatim] [↗ open source]     │
│ R  │                                                      │
└────┴──────────────────────────────────────────────────────┘
```

Sidebar starts collapsed. `≡` button toggles it.

---

## 8. File structure after all changes

```
personal-kb/
├── README.md                       ← update with Windows troubleshooting section
├── requirements.txt                ← add: rank-bm25 (if used), no other new deps
├── .gitignore                      ← add: data/greetings.json, data/kb.db, data/greeting_state.json
│
├── scripts/
│   └── generate_greetings.py       ← NEW: one-time greeting generation script
│
├── ingest/                         ← unchanged, chunking already updated in v1 fixes
│
├── core/
│   ├── chunker.py                  ← unchanged
│   ├── embedder.py                 ← unchanged
│   ├── vectorstore.py              ← unchanged
│   ├── ollama.py                   ← NEW: health check helpers
│   └── search.py                  ← NEW: replaces retriever.py — hybrid BM25 + semantic
│
├── api/
│   └── server.py                   ← major updates: new endpoints, conversation logic,
│                                      streaming fix, health checks, verbatim mode
│
├── ui/
│   ├── index.html                  ← add sidebar, home screen, mode toggle update
│   ├── style.css                   ← add sidebar styles, home screen styles,
│                                      verbatim output styles, error styles
│   └── app.js                     ← add: sidebar toggle, conversation loading,
│                                      home screen logic, greeting fetch,
│                                      verbatim render, pagination, error messages
│
└── data/                           ← all gitignored
    ├── chroma_db/
    ├── kb.db                       ← SQLite: notes_fts + conversations + turns
    ├── greetings.json              ← generated once, served forever
    └── greeting_state.json         ← tracks which greetings have been shown
```

---

## 9. Database migration

`kb.db` is new (or needs new tables added). Run these in order:

```sql
-- notes table (FTS source)
CREATE TABLE IF NOT EXISTS notes (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id    TEXT UNIQUE,
    source_id   TEXT,
    source      TEXT,
    title       TEXT,
    body        TEXT,
    created_at  TEXT,
    url         TEXT
);

-- FTS index over notes
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title, body, source,
    content='notes',
    content_rowid='rowid'
);

-- sync trigger
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, body, source)
    VALUES (new.rowid, new.title, new.body, new.source);
END;

-- conversations
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- turns
CREATE TABLE IF NOT EXISTS turns (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    query           TEXT NOT NULL,
    answer          TEXT,
    mode            TEXT NOT NULL,
    sources         TEXT,
    created_at      TEXT NOT NULL
);
```

After adding the `notes` table, **re-run all ingest scripts** — they must now write to both ChromaDB and `notes` table.

---

## 10. Order of implementation

Do these in this exact order to avoid breaking the working parts:

1. **`core/ollama.py`** — health check helpers (fixes the network error immediately)
2. **Update `api/server.py`** — add Ollama health check to `/query`, add specific error responses, update `/status`
3. **Update `README.md`** — Windows troubleshooting section
4. **DB migration** — create `notes` and `notes_fts` tables in `kb.db`
5. **Update ingest scripts** — write to `notes` table alongside ChromaDB
6. **Re-ingest** — wipe and rebuild (needed for notes table population)
7. **`core/search.py`** — hybrid BM25 + semantic retrieval, dynamic k, replaces retriever.py
8. **Update `api/server.py`** — new `/search/source` endpoint, pagination, verbatim mode endpoint, conversation endpoints
9. **`scripts/generate_greetings.py`** — run once after server is stable
10. **UI — `app.js` + `style.css` + `index.html`** — home screen, sidebar, three-mode toggle, verbatim render, show/hide sources, pagination, error messages, greeting fetch

---

## 11. Skills to use

The coding agent should reference the following from `skills.sh`:

- **SQLite FTS5** — for notes full-text search and the notes_fts virtual table setup
- **FastAPI streaming responses** — for the Ollama streaming fix (`StreamingResponse` + `aiter_lines`)
- **FastAPI BackgroundTasks** — for async embedding after save (already used, extend pattern)
- **ChromaDB persistent client** — already implemented, extend for hybrid merge
- **CSS transitions** — for sidebar open/close animation and answer block fade-in

No new pip packages are strictly required. `rank-bm25` is optional (FTS5 covers the BM25 use case without it). Do not add heavy dependencies — the entire stack runs on a local Windows machine and must stay lightweight.

---

## 12. What NOT to change

- Chunking strategy (already updated in v1 fixes spec — do not re-chunk)
- ChromaDB collection structure or embedding model
- The existing search debounce logic in app.js (extend, don't replace)
- Card visual design (colors, typography, source tag colors) — all stay the same
- The existing `/search` endpoint — keep it, add `/search/source` as a new endpoint alongside it
ENDOFFILE