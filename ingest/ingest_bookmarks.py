import os
from html.parser import HTMLParser
from datetime import datetime, timezone
from core.embedder import embed
from core.vectorstore import VectorStore
from core.chunker import chunk_text
from core.database import save_chunks_to_db

db = VectorStore()

class BookmarksParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bookmarks = []
        self.in_link = False
        self.current_bookmark = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.in_link = True
            self.current_bookmark = {
                "url": "",
                "add_date": "",
                "title": ""
            }
            for attr, val in attrs:
                if attr.lower() == "href":
                    self.current_bookmark["url"] = val
                elif attr.lower() == "add_date":
                    self.current_bookmark["add_date"] = val

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.in_link:
            self.in_link = False
            if self.current_bookmark.get("url"):
                self.bookmarks.append(self.current_bookmark)

    def handle_data(self, data):
        if self.in_link:
            self.current_bookmark["title"] = (self.current_bookmark.get("title", "") + data).strip()

def ingest_bookmarks_file(filepath: str) -> int:
    """
    Parses a browser bookmarks HTML file and indexes the links.
    """
    if not os.path.exists(filepath):
        return 0
        
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading bookmarks file {filepath}: {e}")
        return 0
        
    parser = BookmarksParser()
    parser.feed(html_content)
    
    print(f"Parsed {len(parser.bookmarks)} bookmarks from {filepath}...")
    
    all_chunks = []
    for i, bm in enumerate(parser.bookmarks):
        title = bm.get("title", "Untitled Bookmark")
        url = bm.get("url", "")
        
        # Combine title and URL for the document text
        doc_text = f"Bookmark: {title}\nURL: {url}"
        
        # Format add_date
        add_date_str = bm.get("add_date")
        if add_date_str and add_date_str.isdigit():
            dt = datetime.fromtimestamp(int(add_date_str), tz=timezone.utc)
            saved_at = dt.isoformat()
        else:
            saved_at = datetime.now(timezone.utc).isoformat()
            
        sanitized_url = url.split("?")[0].replace("/", "_").replace(":", "_")[:100]
        source_id = f"bookmark_{sanitized_url}_{i}"
        
        chunks = chunk_text(doc_text, source_id, {
            "source": "bookmark",
            "url": url,
            "saved_at": saved_at,
            "title": title
        })
        all_chunks.extend(chunks)
        
    total_chunks = len(all_chunks)
    success_count = 0
    
    # Batch ChromaDB indexing (size 50)
    batch_size = 50
    for i in range(0, total_chunks, batch_size):
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
                print(f"Error embedding bookmark chunk: {e}")
                
        if ids:
            db.add_documents(texts, metadatas, ids, embeddings)
            
    print(f"Syncing {len(all_chunks)} bookmark chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("Bookmark chunks synced to SQLite.")
    
    return success_count

def ingest_bookmarks(directory: str = "data/raw/bookmarks"):
    """
    Walks directory and indexes bookmarks HTML files.
    """
    if not os.path.exists(directory):
        print(f"Bookmarks directory '{directory}' does not exist. Skipping.")
        return
        
    total_indexed = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith((".html", ".htm")) and "bookmark" in file.lower():
                filepath = os.path.join(root, file)
                print(f"Ingesting bookmarks: {filepath}...")
                indexed = ingest_bookmarks_file(filepath)
                total_indexed += indexed
                
    print(f"Indexed {total_indexed} bookmarks total.")

if __name__ == "__main__":
    ingest_bookmarks()
