# core/database.py

import sqlite3
import os

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "kb.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. notes table (FTS source)
    cursor.execute("""
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
    """)
    
    # 2. FTS index over notes
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
        title, body, source,
        content='notes',
        content_rowid='rowid'
    );
    """)
    
    # 3. sync trigger
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
        INSERT INTO notes_fts(rowid, title, body, source)
        VALUES (new.rowid, new.title, new.body, new.source);
    END;
    """)
    
    # 4. conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT PRIMARY KEY,
        title       TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    """)
    
    # 5. turns table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turns (
        id              TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        query           TEXT NOT NULL,
        answer          TEXT,
        mode            TEXT NOT NULL,
        sources         TEXT,
        created_at      TEXT NOT NULL,
        feedback        TEXT
    );
    """)
    
    # Dynamic migration for existing DB
    try:
        cursor.execute("ALTER TABLE turns ADD COLUMN feedback TEXT;")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    conn.commit()
    conn.close()

def save_chunks_to_db(chunks: list[dict]):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        for chunk in chunks:
            meta = chunk["metadata"]
            chunk_id = f"{chunk['source_id']}_chunk_{chunk['chunk_index']}"
            source_id = chunk["source_id"]
            source = meta.get("source", "")
            title = meta.get("title", "")
            body = chunk["text"]
            
            created_at = meta.get("created_at") or meta.get("saved_at") or ""
            if source == "twitter" and not created_at:
                date_range = meta.get("date_range", "")
                if date_range:
                    created_at = date_range.split(" to ")[0]
            url = meta.get("url") or ""
            
            try:
                cursor.execute("""
                INSERT INTO notes (chunk_id, source_id, source, title, body, created_at, url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    source=excluded.source,
                    title=excluded.title,
                    body=excluded.body,
                    created_at=excluded.created_at,
                    url=excluded.url;
                """, (chunk_id, source_id, source, title, body, created_at, url))
            except Exception as e:
                print(f"Error saving chunk {chunk_id} to SQLite: {e}")
                
        conn.commit()
    finally:
        conn.close()
