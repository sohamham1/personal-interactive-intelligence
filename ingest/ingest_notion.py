import os
import csv
from core.embedder import embed
from core.vectorstore import VectorStore
from ingest.ingest_markdown import ingest_markdown_file
from core.chunker import chunk_text
from core.database import save_chunks_to_db

db = VectorStore()

def ingest_notion_csv(filepath: str) -> int:
    """
    Ingests a Notion CSV database export. Each row is indexed as a document.
    """
    if not os.path.exists(filepath):
        return 0
        
    filename = os.path.basename(filepath)
    success_count = 0
    
    all_chunks = []
    
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                # Construct document text from columns
                row_items = []
                title = ""
                
                # Try to find a Name or Title column
                possible_title_keys = ["Name", "Title", "Page", "Topic"]
                for key in possible_title_keys:
                    for r_key in row.keys():
                        if r_key.strip().lower() == key.lower():
                            title = row[r_key]
                            break
                    if title:
                        break
                        
                for k, v in row.items():
                    if v and v.strip():
                        row_items.append(f"{k}: {v.strip()}")
                        
                if not row_items:
                    continue
                    
                doc_text = "\n".join(row_items)
                source_id = f"notion_csv_{filename.replace('.', '_')}_{i}"
                chunks = chunk_text(doc_text, source_id, {
                    "source": "notion",
                    "page_title": title or filename.replace(".csv", ""),
                    "filename": filename,
                    "title": title or filename.replace(".csv", "")
                })
                all_chunks.extend(chunks)
                
    except Exception as e:
        print(f"Error parsing Notion CSV {filepath}: {e}")
        
    # Batch ChromaDB indexing (size 50)
    batch_size = 50
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = []
        metadatas = []
        ids = []
        embeddings = []
        
        for chunk in batch:
            try:
                vector = embed(chunk["text"])
                if vector:
                    texts.append(chunk["text"])
                    metadatas.append(chunk["metadata"])
                    ids.append(f"{chunk['source_id']}_chunk_{chunk['chunk_index']}")
                    embeddings.append(vector)
                    success_count += 1
            except Exception as e:
                print(f"Error embedding Notion CSV chunk: {e}")
                
        if ids:
            db.add_documents(texts, metadatas, ids, embeddings)
            
    print(f"Syncing {len(all_chunks)} Notion chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("Notion chunks synced to SQLite.")
    
    return success_count

def ingest_notion(directory: str = "data/raw/notion"):
    """
    Walks Notion export directory, ingesting CSV databases and MD notes.
    """
    if not os.path.exists(directory):
        print(f"Notion export directory '{directory}' does not exist. Skipping.")
        return
        
    total_indexed = 0
    for root, _, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            if file.endswith(".csv"):
                print(f"Ingesting Notion CSV: {filepath}...")
                indexed = ingest_notion_csv(filepath)
                total_indexed += indexed
            elif file.endswith((".md", ".markdown")):
                print(f"Ingesting Notion MD: {filepath}...")
                # Reuses markdown ingestion file parser
                indexed = ingest_markdown_file(filepath)
                # Modify source metadata to indicate it came from Notion
                # (For simplicity, ingest_markdown_file sets source to "markdown", which is fine,
                # but we can also handle Notion MD separately or let it merge)
                total_indexed += indexed
                
    print(f"Indexed {total_indexed} Notion documents total.")

if __name__ == "__main__":
    ingest_notion()
