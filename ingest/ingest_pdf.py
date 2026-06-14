import os
from pypdf import PdfReader
from core.embedder import embed
from core.vectorstore import VectorStore
from core.chunker import chunk_text
from core.database import save_chunks_to_db

db = VectorStore()

def ingest_pdf_file(filepath: str) -> int:
    """
    Extracts text from a single PDF and indexes it page by page.
    """
    if not os.path.exists(filepath):
        return 0
        
    filename = os.path.basename(filepath)
    success_count = 0
    
    all_chunks = []
    
    try:
        reader = PdfReader(filepath)
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if not page_text or not page_text.strip():
                continue
                
            source_id = f"pdf_{filename.replace('.', '_')}_p{page_idx + 1}"
            chunks = chunk_text(page_text, source_id, {
                "source": "pdf",
                "filename": filename,
                "page_number": page_idx + 1,
                "title": f"PDF: {filename} (Page {page_idx + 1})"
            })
            all_chunks.extend(chunks)
            
    except Exception as e:
        print(f"Error parsing PDF file {filepath}: {e}")
        
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
                print(f"Error embedding PDF page chunk: {e}")
                
        if ids:
            db.add_documents(texts, metadatas, ids, embeddings)
            
    print(f"Syncing {len(all_chunks)} PDF chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("PDF chunks synced to SQLite.")
    
    return success_count

def ingest_pdfs(directory: str = "data/raw/pdfs"):
    """
    Walks directory and processes all PDFs.
    """
    if not os.path.exists(directory):
        print(f"PDF directory '{directory}' does not exist. Skipping.")
        return
        
    total_indexed = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".pdf"):
                filepath = os.path.join(root, file)
                print(f"Ingesting PDF: {filepath}...")
                indexed = ingest_pdf_file(filepath)
                total_indexed += indexed
                
    print(f"Indexed {total_indexed} PDF chunks total.")

if __name__ == "__main__":
    ingest_pdfs()
