# core/chunker.py

def chunk_text(text: str, source_id: str, metadata: dict,
               chunk_size: int = 150, overlap: int = 30) -> list[dict]:
    """
    Splits text into overlapping word-window chunks.
    Returns list of {text, source_id, chunk_index, metadata}
    
    chunk_size: 150 words (not tokens — simpler, fast enough)
    overlap: 30 words — ensures boundary context isn't lost
    """
    words = text.split()
    
    if len(words) <= chunk_size:
        # Short note: keep as single chunk, no splitting needed
        chunk_metadata = metadata.copy()
        chunk_metadata["source_id"] = source_id
        chunk_metadata["chunk_index"] = 0
        return [{
            "text": text,
            "source_id": source_id,
            "chunk_index": 0,
            "metadata": chunk_metadata
        }]
    
    chunks = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = " ".join(words[start:end])
        chunk_metadata = metadata.copy()
        chunk_metadata["source_id"] = source_id
        chunk_metadata["chunk_index"] = idx
        chunks.append({
            "text": chunk_text,
            "source_id": source_id,
            "chunk_index": idx,
            "metadata": chunk_metadata
        })
        start += chunk_size - overlap
        idx += 1
    
    return chunks
