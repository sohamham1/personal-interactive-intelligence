import os
import re
import httpx
import json
import uuid
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from core.search import retrieve, db
from core.embedder import OLLAMA_BASE_URL, EMBEDDING_MODEL
from core.ollama import check_ollama, check_model
from core.database import get_connection, init_db

app = FastAPI(title="Personal Knowledge Base API")

# Ensure UI directory exists
os.makedirs("ui", exist_ok=True)

# Mount static files folder
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

from typing import Optional

class QueryRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    mode: str = "ai"  # "ai" or "verbatim"
    k: Optional[int] = None
    turn_id: Optional[str] = None

class RenameRequest(BaseModel):
    title: str

class FeedbackRequest(BaseModel):
    feedback: str

# Global state for server errors and ingestion
ERROR_LOG = []
INGEST_STATUS = {
    "status": "idle",  # "idle", "syncing", "failed", "success"
    "error": None,
    "progress": ""
}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
        
    error_detail = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "path": request.url.path,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc()
    }
    global ERROR_LOG
    ERROR_LOG.append(error_detail)
    ERROR_LOG = ERROR_LOG[-20:] # Keep last 20
    
    print(f"Global Exception Handled: {exc}")
    traceback.print_exc()
    
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )

def get_relative_time(iso_str: str) -> str:
    """
    Converts ISO timestamp string to relative time (e.g., "2 months ago", "Apr 2024").
    """
    if not iso_str:
        return ""
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        
        seconds = diff.total_seconds()
        
        if seconds < 0:
            return "just now"
            
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24
        weeks = days / 7
        months = days / 30
        years = days / 365
        
        if seconds < 60:
            return "just now"
        elif minutes < 60:
            m = int(minutes)
            return f"{m} minute{'s' if m > 1 else ''} ago"
        elif hours < 24:
            h = int(hours)
            return f"{h} hour{'s' if h > 1 else ''} ago"
        elif days < 7:
            d = int(days)
            return f"{d} day{'s' if d > 1 else ''} ago"
        elif weeks < 4:
            w = int(weeks)
            return f"{w} week{'s' if w > 1 else ''} ago"
        elif months < 12:
            mo = int(months)
            return f"{mo} month{'s' if mo > 1 else ''} ago"
        else:
            return dt.strftime("%b %Y")
    except Exception as e:
        print(f"Error parsing date {iso_str}: {e}")
        return iso_str

def get_verbatim_date(meta: dict, source: str) -> str:
    """
    Returns simple lowercase date string for verbatim block headers.
    """
    if source == "keep":
        val = meta.get("created_at")
        if val:
            try:
                if val.endswith("Z"):
                    val = val[:-1] + "+00:00"
                dt = datetime.fromisoformat(val)
                return dt.strftime("%b %Y").lower()
            except Exception:
                return val
    elif source == "twitter":
        val = meta.get("date_range")
        if val:
            try:
                start_date_str = val.split(" to ")[0]
                dt = datetime.fromisoformat(start_date_str)
                return f"week of {dt.strftime('%b %d').lower()}"
            except Exception:
                return val
    elif source == "bookmark":
        val = meta.get("saved_at")
        if val:
            try:
                if val.endswith("Z"):
                    val = val[:-1] + "+00:00"
                dt = datetime.fromisoformat(val)
                return dt.strftime("%b %Y").lower()
            except Exception:
                return val
    return ""

def highlight_query(text: str, query: str) -> str:
    """
    Wraps matched query strings in <em> tags case-insensitively.
    """
    if not query:
        return text
    escaped_query = re.escape(query)
    pattern = re.compile(f"({escaped_query})", re.IGNORECASE)
    return pattern.sub(r"<em>\1</em>", text)

def make_snippet(text: str, query: str) -> str:
    """
    Generates a short snippet of the text containing the matching query words if possible,
    or falls back to the beginning of the text.
    """
    if not query:
        return text[:200] + "..." if len(text) > 200 else text
        
    lines = text.split("\n")
    matching_lines = []
    
    for line in lines:
        if query.lower() in line.lower():
            matching_lines.append(line.strip())
            if len(matching_lines) >= 3:
                break
                
    if matching_lines:
        snippet = " ... ".join(matching_lines)
    else:
        snippet = text[:200]
        if len(text) > 200:
            snippet += "..."
            
    if len(snippet) > 300:
        snippet = snippet[:300] + "..."
        
    return highlight_query(snippet, query)

@app.get("/")
def read_root():
    return FileResponse("ui/index.html")

@app.get("/status")
async def get_status():
    ollama_status = await check_ollama()
    model_status = await check_model()
    
    doc_count = db.get_count()
    
    return {
        "documents_indexed": doc_count,
        "ollama_running": ollama_status["running"],
        "ollama_error": ollama_status["error"],
        "model_available": model_status["available"],
        "model_error": model_status["error"],
        "model": "llama3.2:3b"
    }

@app.get("/greeting")
def get_greeting():
    greetings_file = "data/greetings.json"
    state_file = "data/greeting_state.json"
    
    default_resp = {
        "greeting": "Welcome back.",
        "subline": "What are we working on today?",
        "mood": "warm",
        "suggestions": [
            "what notes do I have on startup ideas?",
            "summarize my recent thoughts",
            "what are my goals for this month?"
        ]
    }
    
    if not os.path.exists(greetings_file):
        return default_resp
        
    try:
        with open(greetings_file, "r") as f:
            data = json.load(f)
            
        greetings = data.get("greetings", [])
        suggested_prompts = data.get("suggested_prompts", [])
        
        if not greetings:
            return default_resp
            
        hour = datetime.now().hour
        if 5 <= hour <= 11:
            time_slot = "morning"
        elif 12 <= hour <= 16:
            time_slot = "afternoon"
        elif 17 <= hour <= 20:
            time_slot = "evening"
        else:
            time_slot = "night"
            
        eligible = [g for g in greetings if g.get("time") == time_slot or g.get("time") == "any"]
        if not eligible:
            eligible = greetings
            
        last_served = []
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as sf:
                    last_served = json.load(sf)
            except Exception:
                pass
                
        filtered = [g for g in eligible if g.get("greeting") not in last_served]
        if not filtered:
            filtered = eligible
            last_served = []
            
        import random
        chosen = random.choice(filtered)
        
        last_served.append(chosen.get("greeting"))
        last_served = last_served[-5:]
        try:
            with open(state_file, "w") as sf:
                json.dump(last_served, sf)
        except Exception:
            pass
            
        import random
        suggestions = random.sample(suggested_prompts, min(3, len(suggested_prompts))) if suggested_prompts else default_resp["suggestions"]
        
        return {
            "greeting": chosen.get("greeting"),
            "subline": chosen.get("subline"),
            "mood": chosen.get("mood"),
            "suggestions": suggestions
        }
    except Exception as e:
        print(f"Error in /greeting: {e}")
        return default_resp

@app.get("/search")
def search_endpoint(q: str = "", limit: int = 8):
    if not q or not q.strip():
        return []
        
    results = retrieve(q, n_results=limit)
    formatted = []
    
    for res in results:
        metadata = res["metadata"]
        source = metadata.get("source", "keep")
        
        url = metadata.get("url")
        if source == "twitter":
            tweet_ids = metadata.get("tweet_ids", "")
            if tweet_ids:
                first_id = tweet_ids.split(",")[0]
                url = f"https://twitter.com/any/status/{first_id}"
                
        title = metadata.get("title")
        if not title:
            if source == "twitter":
                title = f"Tweets: {metadata.get('date_range')}"
            elif source == "bookmark":
                title = f"Bookmark: {url}"
            else:
                title = "Untitled note"
                
        timestamp_str = ""
        if source == "keep":
            timestamp_str = get_relative_time(metadata.get("created_at"))
        elif source == "twitter":
            date_range = metadata.get("date_range", "")
            if date_range:
                start_date_str = date_range.split(" to ")[0]
                timestamp_str = get_relative_time(start_date_str)
        elif source == "bookmark":
            timestamp_str = get_relative_time(metadata.get("saved_at"))
            
        formatted.append({
            "id": res["id"],
            "source": source,
            "title": title,
            "snippet": make_snippet(res["text"], q),
            "text": res["text"],
            "timestamp": timestamp_str,
            "url": url
        })
        
    return formatted

@app.get("/search/source")
def search_source_endpoint(q: str = "", limit: int = 20, offset: int = 0, source_group: str = "all"):
    """
    Pure SQLite FTS5 search (no Chroma, no embeddings) with pagination.
    """
    if not q or not q.strip():
        return {"results": [], "total": 0, "has_more": False, "next_offset": offset}
        
    from core.search import sanitize_fts_query
    sanitized_q = sanitize_fts_query(q)
    if not sanitized_q:
        return {"results": [], "total": 0, "has_more": False, "next_offset": offset}
        
    source_clause = ""
    params = [sanitized_q]
    
    if source_group == "notes":
        source_clause = " AND notes.source IN ('keep', 'markdown', 'pdf', 'notion') "
    elif source_group == "tweets":
        source_clause = " AND notes.source = 'twitter' "
        
    total = 0
    formatted = []
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        count_sql = f"""
            SELECT count(*) as total
            FROM notes
            JOIN notes_fts ON notes.rowid = notes_fts.rowid
            WHERE notes_fts MATCH ? {source_clause}
        """
        cursor.execute(count_sql, params)
        total = cursor.fetchone()["total"]
        
        search_sql = f"""
            SELECT notes.chunk_id, notes.source_id, notes.source, notes.title, notes.body, notes.created_at, notes.url
            FROM notes
            JOIN notes_fts ON notes.rowid = notes_fts.rowid
            WHERE notes_fts MATCH ? {source_clause}
            ORDER BY bm25(notes_fts) ASC
            LIMIT ? OFFSET ?
        """
        cursor.execute(search_sql, params + [limit, offset])
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            source = row["source"]
            url = row["url"]
            if source == "twitter":
                url = f"https://twitter.com/any/status"
                
            title = row["title"]
            if not title:
                if source == "twitter":
                    title = "Tweets"
                else:
                    title = "Untitled note"
                    
            timestamp_str = get_relative_time(row["created_at"])
            
            formatted.append({
                "id": row["chunk_id"],
                "source": source,
                "title": title,
                "snippet": make_snippet(row["body"], q),
                "text": row["body"],
                "timestamp": timestamp_str,
                "url": url
            })
            
    except Exception as e:
        print(f"Error in /search/source: {e}")
        
    has_more = offset + len(formatted) < total
    return {
        "results": formatted,
        "total": total,
        "has_more": has_more,
        "next_offset": offset + len(formatted)
    }

@app.get("/conversations")
def list_conversations():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 50")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r["id"], "title": r["title"] or "New Conversation", "updated_at": r["updated_at"]} for r in rows]
    except Exception as e:
        print(f"Error listing conversations: {e}")
        return []

@app.get("/conversations/{id}")
def get_conversation(id: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (id,))
        conv = cursor.fetchone()
        if not conv:
            conn.close()
            raise HTTPException(status_code=404, detail="Conversation not found")
            
        cursor.execute("""
            SELECT id, query, answer, mode, sources, created_at, feedback FROM turns
            WHERE conversation_id = ? ORDER BY created_at ASC
        """, (id,))
        turns = cursor.fetchall()
        conn.close()
        
        formatted_turns = []
        for t in turns:
            parsed_sources = []
            if t["sources"]:
                try:
                    parsed_sources = json.loads(t["sources"])
                except Exception:
                    pass
            formatted_turns.append({
                "id": t["id"],
                "query": t["query"],
                "answer": t["answer"],
                "mode": t["mode"],
                "sources": parsed_sources,
                "created_at": t["created_at"],
                "feedback": t["feedback"]
            })
            
        return {
            "id": conv["id"],
            "title": conv["title"] or "New Conversation",
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "turns": formatted_turns
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching conversation {id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations")
def create_conversation(body: dict = None):
    try:
        cid = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        title = body.get("title") if body else None
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (cid, title, now_str, now_str))
        conn.commit()
        conn.close()
        return {"id": cid}
    except Exception as e:
        print(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/conversations/{id}")
def rename_conversation(id: str, body: RenameRequest):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (body.title, datetime.now(timezone.utc).isoformat(), id))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        print(f"Error renaming conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{id}")
def delete_conversation(id: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        print(f"Error deleting conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/turns/{id}/feedback")
def save_turn_feedback(id: str, body: FeedbackRequest):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE turns SET feedback = ? WHERE id = ?", (body.feedback, id))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        print(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/notes/{source_id}/chunks")
def get_note_chunks(source_id: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT chunk_id, title, body, source, created_at, url FROM notes WHERE source_id = ?", (source_id,))
        rows = cursor.fetchall()
        conn.close()
        
        chunks = []
        for r in rows:
            chunk_id = r["chunk_id"]
            chunk_index = 0
            if "_chunk_" in chunk_id:
                try:
                    chunk_index = int(chunk_id.split("_chunk_")[-1])
                except ValueError:
                    pass
            chunks.append({
                "id": chunk_id,
                "index": chunk_index,
                "title": r["title"] or "Untitled note",
                "text": r["body"],
                "source": r["source"],
                "timestamp": get_relative_time(r["created_at"]),
                "url": r["url"]
            })
            
        chunks.sort(key=lambda x: x["index"])
        return chunks
    except Exception as e:
        print(f"Error fetching chunks for source_id {source_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def run_ingestion():
    global INGEST_STATUS
    INGEST_STATUS["status"] = "syncing"
    INGEST_STATUS["error"] = None
    INGEST_STATUS["progress"] = "Starting note sync..."
    
    try:
        INGEST_STATUS["progress"] = "Syncing Google Keep notes..."
        p1 = subprocess.run([sys.executable, "-m", "ingest.ingest_keepnotes"], capture_output=True, text=True)
        if p1.returncode != 0:
            raise Exception(f"Keep notes sync failed: {p1.stderr}")
            
        INGEST_STATUS["progress"] = "Syncing Twitter archive..."
        p2 = subprocess.run([sys.executable, "-m", "ingest.ingest_twitter"], capture_output=True, text=True)
        if p2.returncode != 0:
            raise Exception(f"Twitter sync failed: {p2.stderr}")
            
        INGEST_STATUS["status"] = "success"
        INGEST_STATUS["progress"] = "Sync complete. All notes and tweets are up to date."
    except Exception as e:
        INGEST_STATUS["status"] = "failed"
        INGEST_STATUS["error"] = str(e)
        INGEST_STATUS["progress"] = f"Sync failed: {str(e)}"

@app.post("/ingest")
def trigger_ingest(background_tasks: BackgroundTasks):
    global INGEST_STATUS
    if INGEST_STATUS["status"] == "syncing":
        return {"status": "syncing", "message": "Ingestion is already running"}
        
    background_tasks.add_task(run_ingestion)
    return {"status": "started"}

@app.get("/ingest/status")
def get_ingest_status():
    return INGEST_STATUS

@app.get("/errors")
def get_errors():
    return ERROR_LOG

@app.delete("/errors")
def clear_errors():
    global ERROR_LOG
    ERROR_LOG = []
    return {"status": "success"}

def truncate_chunk(text: str, max_words: int = 100) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."

def build_prompt(query: str, chunks: list, total_matches: int, context: str = "") -> str:
    formatted = ""
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        source = meta.get("source", "unknown")
        
        created = ""
        if source == "keep":
            created = meta.get("created_at", "")
        elif source == "twitter":
            date_range = meta.get("date_range", "")
            if date_range:
                created = date_range.split(" to ")[0]
        elif source == "bookmark":
            created = meta.get("saved_at", "")
            
        title = meta.get("title", "")
        text = truncate_chunk(chunk["text"])
        formatted += f"[{i+1}] ({source}{', ' + created if created else ''}{', ' + title if title else ''})\n{text}\n\n"
    
    prompt = ""
    if context:
        prompt += f"Previous context:\n{context}\n\n"
        
    prompt += f"""You are a personal memory assistant. These are the user's own notes, tweets, and saved content — written by them or saved by them.

{total_matches} pieces of content matched this query. Here are the most relevant ones:

{formatted}
Current question: {query}

Instructions:
- Answer as if you know this person well, because you're drawing from their own words
- If the query is broad (e.g. "what have I said about love"), identify themes across the sources
- Mention specific examples from the notes where relevant
- Be honest if coverage seems partial: "you have {total_matches} notes on this — here are the main themes"
- Do not make up content not present in the sources
- Keep the answer to 4-6 sentences
- You are summarising the user's own notes. Be concise (4–8 sentences). Reference specific examples. Do not fabricate anything not in the sources."""
    
    return prompt

@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        print("Database initialized successfully.")
    except Exception as db_err:
        print(f"Error initializing database: {db_err}")
        
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{OLLAMA_BASE_URL}/api/generate", json={
                "model": "llama3.2:3b",
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 1}
            }, timeout=10)
    except Exception:
        pass

@app.post("/query")
async def query_endpoint(body: QueryRequest):
    ollama_status = await check_ollama()
    if not ollama_status["running"]:
        raise HTTPException(status_code=503, detail=ollama_status["error"])
        
    model_status = await check_model()
    if not model_status["available"]:
        raise HTTPException(status_code=503, detail=model_status["error"])

    conversation_id = body.conversation_id
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
        
    turn_id = body.turn_id or str(uuid.uuid4())
        
    now_str = datetime.now(timezone.utc).isoformat()
    title = body.question[:50]
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM conversations ORDER BY updated_at DESC")
        convs = cursor.fetchall()
        if len(convs) >= 50:
            to_delete = [c["id"] for c in convs[49:]]
            for c_id in to_delete:
                if c_id != conversation_id:
                    cursor.execute("DELETE FROM conversations WHERE id = ?", (c_id,))
                    
        cursor.execute("SELECT id, title FROM conversations WHERE id = ?", (conversation_id,))
        existing_conv = cursor.fetchone()
        if not existing_conv:
            cursor.execute("""
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, title, now_str, now_str))
        else:
            if not existing_conv["title"]:
                cursor.execute("""
                    UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?
                """, (title, now_str, conversation_id))
            else:
                cursor.execute("""
                    UPDATE conversations SET updated_at = ? WHERE id = ?
                """, (now_str, conversation_id))
        conn.commit()
        conn.close()
    except Exception as db_err:
        print(f"Error managing conversations: {db_err}")

    # Use client provided k count if specified
    k_val = body.k

    if body.mode == "verbatim":
        chunks = retrieve(body.question, deduplicate=False, n_results=k_val)
        total_matches = len(chunks)
        
        groups = {}
        for c in chunks:
            meta = c["metadata"]
            sid = meta.get("source_id") or meta.get("url") or meta.get("filename") or c["id"]
            if sid not in groups:
                groups[sid] = {
                    "chunks": [],
                    "max_score": c.get("rrf_score", 0.0),
                    "metadata": meta,
                    "source": meta.get("source", "keep"),
                    "title": meta.get("title", ""),
                    "url": meta.get("url") or ""
                }
            groups[sid]["chunks"].append(c)
            groups[sid]["max_score"] = max(groups[sid]["max_score"], c.get("rrf_score", 0.0))
            
        for sid, group in groups.items():
            group["chunks"].sort(key=lambda x: x["metadata"].get("chunk_index", 0))
            
        sorted_groups = list(groups.values())
        sorted_groups.sort(key=lambda x: x["max_score"], reverse=True)
        source_count = len(sorted_groups)
        
        html_out = f'<div class="verbatim-title">" VERBATIM — {total_matches} passages across {source_count} sources</div>\n\n'
        for group in sorted_groups:
            src_name = group["source"]
            title_name = group["title"]
            date_str = get_verbatim_date(group["metadata"], src_name)
            
            header_parts = [src_name]
            if title_name and title_name != "Untitled note":
                header_parts.append(title_name.lower())
            if date_str:
                header_parts.append(date_str)
                
            header_text = f" { ' · '.join(header_parts) } "
            html_out += f'<div class="verbatim-header"><span class="verbatim-sep">━━━</span> {header_text} <span class="verbatim-sep">{"━" * max(5, 50 - len(header_text))}</span></div>\n'
            for c in group["chunks"]:
                html_out += f'<div class="verbatim-body">{c["text"]}</div>\n'
            
            url = group["url"]
            if src_name == "twitter":
                tweet_ids = group["metadata"].get("tweet_ids", "")
                if tweet_ids:
                    first_id = tweet_ids.split(",")[0]
                    url = f"https://twitter.com/any/status/{first_id}"
                    
            if url:
                html_out += f'<a href="{url}" class="verbatim-link" target="_blank">↗ open original</a>\n\n'
            else:
                html_out += f'<span class="verbatim-link-disabled">↗ open original</span>\n\n'
                
        sources_list = []
        for g in sorted_groups:
            meta = g["metadata"]
            best_chunk = g["chunks"][0] if g["chunks"] else {"id": "", "text": ""}
            sources_list.append({
                "id": best_chunk.get("id") or best_chunk.get("chunk_id") or "",
                "source": g["source"],
                "title": g["title"] or "Untitled Note",
                "created_at": get_relative_time(meta.get("created_at") or meta.get("saved_at") or ""),
                "url": g["url"],
                "text": best_chunk.get("text", ""),
                "snippet": make_snippet(best_chunk.get("text", ""), body.question)
            })
            
        async def stream_verbatim():
            yield html_out
            yield f"\n\n__SOURCES__{json.dumps(sources_list)}"
            
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO turns (id, conversation_id, query, answer, mode, sources, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        answer=excluded.answer,
                        sources=excluded.sources,
                        mode=excluded.mode,
                        created_at=excluded.created_at;
                """, (turn_id, conversation_id, body.question, html_out, "verbatim", json.dumps(sources_list), datetime.now(timezone.utc).isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error saving verbatim turn to DB: {e}")

        return StreamingResponse(
            stream_verbatim(),
            media_type="text/plain",
            headers={"X-Conversation-Id": conversation_id}
        )
        
    else:
        context = ""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT query, answer FROM turns
                WHERE conversation_id = ? AND answer IS NOT NULL AND mode = 'ai'
                ORDER BY created_at DESC LIMIT 3
            """, (conversation_id,))
            turns_rows = cursor.fetchall()
            conn.close()
            
            last_3_turns = list(reversed(turns_rows))
            context = "\n\n".join([
                f"User: {t['query']}\nAssistant: {t['answer']}"
                for t in last_3_turns if t['answer']
            ])
        except Exception as ctx_err:
            print(f"Error fetching conversation context: {ctx_err}")

        chunks = retrieve(body.question, n_results=k_val)
        total_matches = getattr(chunks, "total_matches", len(chunks))
        prompt = build_prompt(body.question, chunks, total_matches, context)
        
        async def stream_ollama():
            sources = []
            for c in chunks:
                meta = c["metadata"]
                source = meta.get("source", "keep")
                
                title = ""
                created_at = ""
                url = meta.get("url", "")
                
                if source == "keep":
                    title = meta.get("title", "Untitled Note")
                    created_at = get_relative_time(meta.get("created_at", ""))
                elif source == "twitter":
                    title = f"Twitter • {meta.get('date_range')}"
                    date_range = meta.get("date_range", "")
                    if date_range:
                        created_at = get_relative_time(date_range.split(" weeg ")[0] if " weeg " in date_range else date_range.split(" to ")[0])
                elif source == "bookmark":
                    title = meta.get("url", "Bookmark")
                    created_at = get_relative_time(meta.get("saved_at", ""))
                else:
                    title = meta.get("title", "Untitled Note")
                    created_at = "recent"
                    
                sources.append({
                    "id": c.get("id") or c.get("chunk_id") or "",
                    "source": source,
                    "title": title,
                    "created_at": created_at,
                    "url": url,
                    "text": c.get("text", ""),
                    "snippet": make_snippet(c.get("text", ""), body.question)
                })
                
            full_answer = ""
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/generate", json={
                    "model": "llama3.2:3b",
                    "prompt": prompt,
                    "stream": True
                }) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    token = data["response"]
                                    full_answer += token
                                    yield token
                                if data.get("done"):
                                    yield f"\n\n__SOURCES__{json.dumps(sources)}"
                                    break
                            except Exception as parse_err:
                                print(f"Error parsing Ollama chunk: {parse_err}")
                                
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO turns (id, conversation_id, query, answer, mode, sources, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        answer=excluded.answer,
                        sources=excluded.sources,
                        mode=excluded.mode,
                        created_at=excluded.created_at;
                """, (turn_id, conversation_id, body.question, full_answer, "ai", json.dumps(sources), datetime.now(timezone.utc).isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error saving turn to DB: {e}")
                
        return StreamingResponse(
            stream_ollama(),
            media_type="text/plain",
            headers={"X-Conversation-Id": conversation_id}
        )
