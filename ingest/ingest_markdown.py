import os
import re
from core.embedder import embed
from core.vectorstore import VectorStore
from core.chunker import chunk_text
from core.database import save_chunks_to_db

db = VectorStore()

def chunk_markdown_by_headings(content: str) -> list[tuple[str, str]]:
    """
    Chunks markdown text by headings (lines starting with ## or ###).
    Returns a list of (heading_title, chunk_text).
    """
    chunks = []
    # Split content by markdown heading levels 2 and 3
    pattern = re.compile(r'^(##{1,2}\s+.*)$', re.MULTILINE)
    parts = pattern.split(content)
    
    if len(parts) <= 1:
        return []
        
    # First part is intro before the first heading
    intro = parts[0].strip()
    if intro:
        chunks.append(("Intro", intro))
        
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i+1].strip() if i+1 < len(parts) else ""
        
        # Heading lines start with ## or ###
        heading_title = heading.lstrip('#').strip()
        chunk_text = f"{heading}\n\n{body}" if body else heading
        chunks.append((heading_title, chunk_text))
        
    return chunks

def chunk_by_sliding_window(content: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    Fallback chunking by simple word count (approx tokens).
    """
    words = content.split()
    chunks = []
    
    if not words:
        return []
        
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))
        if i + chunk_size >= len(words):
            break
            
    return chunks

def ingest_markdown_file(filepath: str) -> int:
    """
    Reads a markdown file, chunks it, and indexes to ChromaDB.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading markdown file {filepath}: {e}")
        return 0
        
    filename = os.path.basename(filepath)
    chunks = chunk_markdown_by_headings(content)
    
    # Fallback if no headings found
    if not chunks:
        fallback_chunks = chunk_by_sliding_window(content)
        chunks = [("General", c) for c in fallback_chunks]
        
    texts = []
    metadatas = []
    ids = []
    embeddings = []
    
    success_count = 0
    
    all_chunks = []
    for i, (heading, text) in enumerate(chunks):
        if not text.strip():
            continue
            
        source_id = f"markdown_{filename.replace('.', '_')}_{i}"
        sub_chunks = chunk_text(text, source_id, {
            "source": "markdown",
            "filename": filename,
            "heading": heading,
            "title": f"{filename} > {heading}"
        })
        all_chunks.extend(sub_chunks)
        
    texts = []
    metadatas = []
    ids = []
    embeddings = []
    success_count = 0
    
    for chunk in all_chunks:
        try:
            vector = embed(chunk["text"])
            if vector:
                texts.append(chunk["text"])
                metadatas.append(chunk["metadata"])
                ids.append(f"{chunk['source_id']}_chunk_{chunk['chunk_index']}")
                embeddings.append(vector)
                success_count += 1
        except Exception as e:
            print(f"Error embedding chunk of {filename}: {e}")
            
    if ids:
        db.add_documents(texts, metadatas, ids, embeddings)
        
    print(f"Syncing {len(all_chunks)} Markdown chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("Markdown chunks synced to SQLite.")
        
    return success_count

def ingest_markdown(directory: str = "data/raw/markdown"):
    """
    Recursively walks the directory and indexes all markdown files.
    """
    if not os.path.exists(directory):
        print(f"Markdown directory '{directory}' does not exist. Skipping.")
        return
        
    total_indexed = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith((".md", ".markdown")):
                filepath = os.path.join(root, file)
                print(f"Ingesting markdown: {filepath}...")
                indexed = ingest_markdown_file(filepath)
                total_indexed += indexed
                
    print(f"Indexed {total_indexed} Markdown chunks total.")

if __name__ == "__main__":
    ingest_markdown()
