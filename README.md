# Recall (Local RAG Knowledge Base)

Interactive AI Assistant built on a local RAG ecosystem, transforming fragmented personal data into actionable, context-aware insights. 

Featuring a terminal spotlight-inspired browser interface, the system supports hybrid semantic-lexical search, multi-turn AI chat, verbatim source viewing, and dynamic, context-aware personalized greetings.

**Everything runs entirely on your local machine.** No API keys, no cloud calls, and no data ever leaves your computer.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Data_Sources["Data Sources"]
        Keep[Google Keep JSON]
        Tweets[Twitter Archive]
        MD[Markdown/PDF/Notion]
    end

    subgraph Ingestion_Pipeline["Ingestion Pipeline"]
        Chunker[Text Chunker]
        Embedder[Ollama Embeddings nomic-embed-text]
        SQLiteSync[SQLite FTS5 Storage]
        ChromaSync[ChromaDB Vector Store]
    end

    subgraph Backend_FastAPI_Server["FastAPI Backend Server"]
        SearchAPI[Hybrid Retriever RRF]
        LLM[Ollama Llama 3.2:3b]
        DbAPI[SQLite History & Session Manager]
    end

    subgraph Frontend_Client["Spotlight UI"]
        ChatMode["▸ Answer with AI"]
        VerbatimMode["Verbatim Source"]
        SourceMode["↗ Open Source FTS"]
    end

    %% Data Pipeline Connections
    Keep --> Chunker
    Tweets --> Chunker
    MD --> Chunker
    Chunker --> Embedder
    Embedder --> ChromaSync
    Chunker --> SQLiteSync

    %% Search and Retrieval flow
    ChatMode -- "User Queries" --> SearchAPI
    VerbatimMode -- "User Queries" --> SearchAPI
    SourceMode -- "User Queries" --> SearchAPI

    SearchAPI -- "Lexical Results" --> SQLiteSync
    SearchAPI -- "Vector Matches" --> ChromaSync
    SearchAPI -- "Combined Context" --> LLM
    LLM -- "Streamed Response" --> ChatMode
    DbAPI -- "Save History" --> SQLiteSync
```

### 1. Ingestion Pipeline
* **Source Parsers**: Dedicated ingestion modules parse structured exports like Google Keep notes (extracting metadata, lists, tags) and Twitter archives (filtering retweets, grouping tweets chronologically into weekly digest documents).
* **Chunking Strategy**: Smart chunk size limits with overlap ensure semantic continuity across passages without exceeding LLM context windows.
* **Vector Store**: Texts are converted to 768-dimensional dense vectors using Ollama's `nomic-embed-text` model and indexed in a local ChromaDB collection.
* **Lexical Index**: The same text chunks are stored in a local SQLite database utilizing the `FTS5` (Full-Text Search) virtual table extension for high-performance prefix and token matching.

### 2. Hybrid Retrieval & RRF
* When a query is made, the engine performs a **hybrid search**:
  1. A semantic search on ChromaDB.
  2. A lexical keyword search on SQLite FTS5.
* The two result sets are merged using **Reciprocal Rank Fusion (RRF)** to score and rank documents, ensuring that passages with both semantic relevance and precise keyword overlap float to the top.

### 3. Dynamic Personalization Engine
* The app features a home screen with dynamic greetings and suggestions customized to the user.
* It uses local LLM generations based on random samplings of your indexed documents to construct context-aware, witty, or reflective greetings tailored to your writing style, schedule, and interests.
* Personalization is fully parameterized via environment variables to keep your name and bio out of the source code.

---

## Security & Privacy First

> [!IMPORTANT]
> **Data Isolation**: Raw data exports (`Keep/`, `Tweets/`), SQLite DB (`data/kb.db`), and the Chroma vector database (`data/chroma_db/`) reside entirely within your local workspace root. 
> These directories are strictly excluded via `.gitignore` to prevent accidental commits of personal data to public repositories.

---

## Tech Stack

* **LLM Engine**: [Ollama](https://ollama.com/) running `llama3.2:3b` locally (CPU/GPU-accelerated).
* **Embedding Model**: `nomic-embed-text` via Ollama.
* **Vector Database**: ChromaDB (File-based local persistent client).
* **Database & Indexing**: SQLite with `FTS5` virtual tables.
* **Backend Framework**: Python 3.10+ & FastAPI.
* **Frontend Web App**: Vanilla HTML5, CSS3 (featuring sleek glassmorphic aesthetics, a light theme, and console panels), and asynchronous ES6 Javascript.

---

## Setup & Ingest Instructions

### 1. Install Ollama
Download and install [Ollama](https://ollama.com/). Pull the required models:
```bash
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

### 2. Prepare Virtual Environment
Clone the repository, enter the root directory, create a Python virtual environment, and install the required dependencies:
```bash
# Create venv
python -m venv venv

# Activate on Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Activate on macOS/Linux
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Place Raw Data
Create folders in the root of the project to drop in your raw data exports:
* **Google Keep**: Export your data via Google Takeout. Place the individual note `.json` files inside a folder named `Keep/` in the root.
* **Twitter**: Request and download your Twitter/X data archive. Extract it and place `tweets.js` (found in the `data/` folder of your export) inside a folder named `Tweets/` in the root.

### 4. Custom Personalization
To customize greetings without hardcoding your personal information, set the following environment variables (or save them in a `.env` file in the root):
```env
USER_NAME="Alex"
USER_BIO="a software developer from San Francisco who loves retro video games, sci-fi movies, and writing"
USER_TOPICS="programming, books, gaming, ideas, goals, reviews"
```

### 5. Run Ingestion
Run the ingestion scripts to index and embed your data:
```bash
# Ingest Google Keep JSON Notes
python -m ingest.ingest_keepnotes

# Ingest Twitter Archive
python -m ingest.ingest_twitter
```

### 6. Start the Server
Run the startup script:
* **Windows**: Double-click `start.bat` or run:
  ```powershell
  .\start.bat
  ```
  *Note: The `start.bat` script will automatically open your default web browser to the application.*

* **macOS/Linux / Manual**:
  ```bash
  python -m uvicorn api.server:app --port 8000
  ```
  Open your browser and navigate to **`http://localhost:8000`**.

### 7. Stop the Server
To safely stop the server and cleanly release the port:
* **Windows**: Double-click `stop.bat` or run `.\stop.bat`. The script actively hunts down the specific `start.bat` terminal window and terminates it. The browser UI features a 2-second heartbeat and will automatically detect the server shutdown to help close out your session.
* **macOS/Linux / Manual**: Terminate the `uvicorn` process (e.g., via `Ctrl+C` in your terminal).

---

## Key Features

- **Graceful AI Concurrency**: Start a complex AI query and freely navigate to your notes or collections. The LLM runs in the background with a global "thinking" indicator.
- **Snappy Context Switching**: Navigating to a new chat instantly fires an `AbortController` signal to drop the active generation, instantly freeing up your GPU and preventing queue bottlenecks.
- **Fail-safe Partial Saves**: If a generation is aborted or the server stops, partial streams are still safely preserved to your SQLite history database. No lost data.
- **Aggressive Cache Control**: The FastAPI backend serves your UI with strict zero-cache middleware so layout updates apply instantly on refresh.
- **Robust Launch Scripts**: `start.bat` features an auto-version check, and `stop.bat` accurately kills both the python server and the terminal window hosting it.
