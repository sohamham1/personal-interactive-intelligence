# Project 1: Personal Knowledge Base Q&A

## What this is

A local RAG (Retrieval-Augmented Generation) system that lets you chat with your own notes, tweets, and documents through a browser UI. Everything runs on your machine. No API keys, no cloud, no data leaves your computer.

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| LLM | Ollama + `llama3.2:3b` | Lightweight, fast on CPU, free |
| Embeddings | `nomic-embed-text` via Ollama | Local embedding model, no cost |
| Vector store | ChromaDB | Simple, file-based, no server needed |
| Backend | Python + FastAPI | Minimal, clean API layer |
| Frontend | Plain HTML/CSS/JS | No framework overhead, easy to read |
| Data parsing | Python scripts per source type | One ingestion script per data source |

---

## Project Structure

```
personal-kb/
├── README.md
├── requirements.txt
├── .gitignore                  # IMPORTANT: ignore /data/ entirely
│
├── ingest/
│   ├── ingest_keepnotes.py     # Parses Google Keep JSON export
│   ├── ingest_twitter.py       # Parses Twitter archive tweets.js
│   ├── ingest_markdown.py      # Walks a folder of .md files
│   ├── ingest_notion.py        # Parses Notion CSV/markdown export
│   ├── ingest_pdf.py           # Extracts text from PDFs
│   └── ingest_bookmarks.py     # Parses browser bookmarks HTML export
│
├── core/
│   ├── embedder.py             # Wraps Ollama embedding calls
│   ├── vectorstore.py          # ChromaDB read/write helpers
│   └── retriever.py            # Query → top-k chunks → context
│
├── api/
│   └── server.py               # FastAPI app, /query and /status endpoints
│
├── ui/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
└── data/                       # .gitignored — your actual notes live here
    └── chroma_db/              # Vector store persisted here
```

---

## .gitignore (critical)

```
data/
*.json
*.csv
*.pdf
*.html
__pycache__/
.env
```

The `data/` folder is where all personal content lives. It must never be committed.

---

## Setup Flow (for the coding agent)

### Step 1: Install and configure Ollama

#### macOS

```bash
# Option A: Direct download
# Go to https://ollama.com/download and download the macOS installer
# Open the .dmg, drag Ollama to Applications, launch it
# Ollama runs as a menu bar app and starts the local server automatically

# Option B: Homebrew
brew install ollama
ollama serve   # starts the server at http://localhost:11434
```

#### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
# This installs ollama as a systemd service that starts automatically
# Verify it's running:
systemctl status ollama
```

#### Windows

```
Download the installer from https://ollama.com/download/windows
Run the .exe — Ollama installs and starts automatically as a background service
```

#### Verify Ollama is running

```bash
curl http://localhost:11434
# Should return: "Ollama is running"
```

#### Pull the required models

```bash
# The LLM for answering questions (~2GB download)
ollama pull llama3.2:3b

# The embedding model for semantic search (~270MB download)
ollama pull nomic-embed-text

# Verify both are available
ollama list
```

**RAM guidance:**
- `llama3.2:3b` needs ~4GB RAM minimum, 8GB comfortable
- If your machine has less than 8GB RAM total, use `llama3.2:1b` instead (less accurate but faster)
- The embedding model (`nomic-embed-text`) is small and always fast

#### Test that models work

```bash
# Quick test for the LLM
ollama run llama3.2:3b "say hello in one sentence"

# Quick test for embeddings
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "test sentence"
}'
# Should return a JSON object with an "embedding" array of floats
```

---

### Step 2: Python environment

```bash
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn chromadb httpx python-dotenv
```

### Step 3: Ingest data

```bash
# User drops their export files into data/raw/
python ingest/ingest_keepnotes.py
python ingest/ingest_twitter.py
# etc.
```

### Step 4: Run

```bash
uvicorn api.server:app --reload --port 8000
# Open browser at http://localhost:8000
```

---

## Data Sources: Ingest Specs

### Google Keep (JSON export)

- Export via Google Takeout → select Keep → download
- Each note is a `.json` file with fields: `title`, `textContent`, `labels`, `createdTimestampUsec`
- Chunk strategy: one note = one document (Keep notes are short)
- Metadata to store: `source: "keep"`, `title`, `created_at`, `labels`

### Twitter Archive

- Export from Twitter Settings → `tweets.js`
- Each tweet has: `full_text`, `created_at`, `id_str`
- Filter out: retweets (`full_text` starts with `RT @`)
- Chunk strategy: group tweets by week into single documents (tweets are too short to embed individually)
- Metadata: `source: "twitter"`, `date_range`, `tweet_ids[]`

### Markdown files

- Walk a folder recursively, find all `.md` files
- Chunk by heading sections (split on `##` or `###`)
- Fallback: chunk by 500 tokens with 50 token overlap if no headings
- Metadata: `source: "markdown"`, `filename`, `heading`

### Notion export

- Export as Markdown & CSV from Notion settings
- Reuse `ingest_markdown.py` for `.md` files
- For CSV database exports: each row = one document
- Metadata: `source: "notion"`, `page_title`

### PDFs

- Use `pypdf` to extract text page by page
- Chunk: 500 tokens, 50 token overlap
- Metadata: `source: "pdf"`, `filename`, `page_number`

### Browser bookmarks

- Export as HTML from Chrome/Firefox
- Parse `<a>` tags: extract `href`, link text, and `add_date`
- One bookmark = one document
- Metadata: `source: "bookmark"`, `url`, `saved_at`

---

## Core Logic

### embedder.py

```python
# POST to http://localhost:11434/api/embeddings
# model: "nomic-embed-text"
# returns: list of floats
# wrap in a simple embed(text: str) -> list[float] function
```

### vectorstore.py

```python
# Use chromadb.PersistentClient(path="data/chroma_db")
# Collection name: "personal_kb"
# Store: document text, embedding, metadata dict
# Methods needed: add_documents(), query(text, n_results=5)
```

### retriever.py

```python
# 1. Embed the query
# 2. Query ChromaDB for top 5 chunks
# 3. Return list of {text, metadata, distance}
```

### server.py (FastAPI)

```python
# GET  /         → serves ui/index.html
# POST /query    → body: {question: str} → returns {answer: str, sources: list}
# GET  /status   → returns {documents_indexed: int, ollama_running: bool}

# Query flow:
# 1. Retrieve top 5 chunks from ChromaDB
# 2. Build prompt: "Given these notes: {chunks}\n\nAnswer: {question}"
# 3. POST to http://localhost:11434/api/generate (llama3.2:3b, stream=false)
# 4. Return answer + source metadata
```

---

## UI Spec (ui/)

Single page. No frameworks.

- Text input at the bottom (like a chat box)
- Chat history scrolls above
- Each answer shows source tags below it (e.g. `keep · 2023` or `twitter · week of Mar 4`)
- `/status` endpoint drives a small indicator: "● 1,842 notes indexed"
- No login, no settings page, nothing fancy

---

## README must include

- What it is (one paragraph)
- Setup instructions (Ollama install link, Python steps)
- How to export data from each source (links to Google Takeout, Twitter archive, etc.)
- Explicit note: "Your data stays in `/data/` which is gitignored. Never commit this folder."
- How to add a new data source (point to `ingest/` folder pattern)

---

## What this project demonstrates (for resume/GitHub)

- RAG pipeline built from scratch (not LangChain abstractions)
- Local LLM integration via Ollama
- Vector embeddings + semantic search
- Multi-source data ingestion with different chunking strategies
- FastAPI backend + clean separation of concerns
- Responsible handling of personal data in open source projects
