import os
import json
import glob
from datetime import datetime, timezone
from core.embedder import embed_batch
from core.vectorstore import VectorStore
from core.chunker import chunk_text
from core.database import save_chunks_to_db

# Single reusable vector store instance
db = VectorStore()

def parse_keep_note(filepath: str) -> dict | None:
    """
    Parses a single Google Keep JSON file.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            note = json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None
        
    # Skip trashed notes
    if note.get("isTrashed", False):
        return None
        
    title = note.get("title", "").strip()
    
    # Extract text content
    content_parts = []
    
    # Check textContent field
    text_content = note.get("textContent", "").strip()
    if text_content:
        content_parts.append(text_content)
        
    # Check listContent field
    list_content = note.get("listContent", [])
    if list_content:
        for item in list_content:
            text = item.get("text", "").strip()
            if text:
                checked_box = "[x]" if item.get("isChecked", False) else "[ ]"
                content_parts.append(f"{checked_box} {text}")
                
    content = "\n".join(content_parts).strip()
    
    # If no content, skip note
    if not content and not title:
        return None
        
    # Handle timestamp (Keep uses microseconds)
    timestamp_usec = note.get("createdTimestampUsec")
    if timestamp_usec:
        dt = datetime.fromtimestamp(timestamp_usec / 1_000_000, tz=timezone.utc)
        created_at = dt.isoformat()
    else:
        created_at = datetime.now(timezone.utc).isoformat()
        
    # Labels
    labels_list = [label["name"] for label in note.get("labels", []) if "name" in label]
    labels_str = ",".join(labels_list)
    
    # Unique ID based on filename
    file_id = os.path.basename(filepath).replace(".json", "")
    
    # Document text to embed
    doc_text = f"Title: {title}\n\n{content}" if title else content
    
    return {
        "id": f"keep_{file_id}",
        "text": doc_text,
        "metadata": {
            "source": "keep",
            "title": title or "Untitled Keep Note",
            "created_at": created_at,
            "labels": labels_str
        }
    }

def ingest_keep_notes(keep_dir: str = "Keep", batch_size: int = 100):
    """
    Finds and processes all Keep JSON files in keep_dir in batches.
    """
    if not os.path.exists(keep_dir):
        print(f"Directory '{keep_dir}' not found.")
        return
        
    json_pattern = os.path.join(keep_dir, "*.json")
    json_files = glob.glob(json_pattern)
    
    print(f"Found {len(json_files)} JSON files in '{keep_dir}'...")
    
    all_chunks = []
    for filepath in json_files:
        parsed = parse_keep_note(filepath)
        if parsed:
            # Split the note text into overlapping chunks
            chunks = chunk_text(
                text=parsed["text"],
                source_id=parsed["id"],
                metadata=parsed["metadata"]
            )
            all_chunks.extend(chunks)
            
    total_chunks = len(all_chunks)
    print(f"Generated {total_chunks} Keep note chunks. Starting batch embedding with size {batch_size}...")
    
    success_count = 0
    
    for i in range(0, total_chunks, batch_size):
        batch = all_chunks[i : i + batch_size]
        batch_texts = [chunk["text"] for chunk in batch]
        
        try:
            # Generate embeddings in batch
            batch_embeddings = embed_batch(batch_texts)
            
            # Prepare batch for ChromaDB
            texts = []
            metadatas = []
            ids = []
            embeddings = []
            
            for j, chunk in enumerate(batch):
                if j < len(batch_embeddings):
                    texts.append(chunk["text"])
                    metadatas.append(chunk["metadata"])
                    ids.append(f"{chunk['source_id']}_chunk_{chunk['chunk_index']}")
                    embeddings.append(batch_embeddings[j])
                    success_count += 1
                    
            if ids:
                db.add_documents(texts, metadatas, ids, embeddings)
                print(f"Indexed {success_count}/{total_chunks} chunks...")
        except Exception as e:
            print(f"Failed to embed batch starting at index {i}: {e}")
            
    print(f"Successfully finished Keep ingestion. Indexed {success_count}/{total_chunks} chunks.")
    print("Syncing Keep chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("Keep chunks synced to SQLite.")

if __name__ == "__main__":
    ingest_keep_notes()
