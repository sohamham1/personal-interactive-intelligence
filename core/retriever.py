from core.embedder import embed
from core.vectorstore import VectorStore

# Single reusable vector store instance
db = VectorStore()

class SearchResultsList(list):
    def __init__(self, *args, total_matches=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_matches = total_matches

def retrieve(query_text: str, n_results: int = None) -> list[dict]:
    """
    Dynamic k based on query type:
    - Short/specific query (1-2 words): k=20, then deduplicate to top 10 unique sources
    - Longer/conversational query (3+ words): k=30, deduplicate to top 15 unique sources
    
    Deduplication: if multiple chunks from same source_id are retrieved,
    keep only the highest-scoring chunk per source, but include a
    `chunk_count` field so the LLM knows how many matches there were.
    """
    if not query_text or not query_text.strip():
        return []

    # Get query embedding
    query_vector = embed(query_text)
    if not query_vector:
        return []

    words = len(query_text.split())
    k = 30 if words >= 3 else 20
    
    limit = n_results if n_results is not None else (15 if words >= 3 else 10)
    k = max(k, limit)

    # Query vectorstore
    results = db.query(query_embeddings=[query_vector], n_results=k)
    
    # Process results into flat list of dicts
    formatted_results = []
    
    # results format is a dictionary with lists of lists for documents, metadatas, ids, distances
    if not results or "ids" not in results or not results["ids"] or not results["ids"][0]:
        return []
        
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0] if "distances" in results else [0.0] * len(ids)
    
    for i in range(len(ids)):
        formatted_results.append({
            "id": ids[i],
            "text": documents[i],
            "metadata": metadatas[i],
            "distance": float(distances[i])
        })
        
    # Deduplicate: best chunk per source_id
    seen = {}
    source_counts = {}
    for res in formatted_results:
        meta = res["metadata"]
        # Fallback if source_id is not in metadata
        sid = meta.get("source_id") or meta.get("url") or meta.get("filename") or res["id"]
        
        source_counts[sid] = source_counts.get(sid, 0) + 1
        if sid not in seen:
            seen[sid] = res
            
    # Add chunk_count to the selected unique chunks
    for sid, res in seen.items():
        res["chunk_count"] = source_counts[sid]
        
    deduped = list(seen.values())
    
    # Return top N unique sources
    final_results = SearchResultsList(deduped[:limit], total_matches=len(formatted_results))
    
    return final_results
