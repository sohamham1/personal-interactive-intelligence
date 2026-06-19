# core/search.py

import re
from core.embedder import embed
from core.vectorstore import VectorStore
from core.database import get_connection

# Single reusable vector store instance
db = VectorStore()

class SearchResultsList(list):
    def __init__(self, *args, total_matches=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.total_matches = total_matches

def sanitize_fts_query(query: str) -> str:
    query_stripped = query.strip()
    if not query_stripped:
        return ""
    
    phrases = re.findall(r'"([^"]+)"', query_stripped)
    unquoted = re.sub(r'"[^"]+"', ' ', query_stripped)
    
    terms = []
    for p in phrases:
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', p)
        cleaned = ' '.join(cleaned.split())
        if cleaned:
            terms.append(f'"{cleaned}"')
            
    cleaned_unquoted = re.sub(r'[^a-zA-Z0-9\s]', ' ', unquoted)
    words = cleaned_unquoted.split()
    for w in words:
        terms.append(f"{w}*")
        
    if not terms:
        return ""
    return " OR ".join(terms)

def get_retrieval_params(query: str) -> dict:
    words = query.split()
    
    if '"' in query:
        return {"k": 30, "mode": "hybrid", "dedupe": True, "max_unique": 15}
    
    # Exact phrase query (quoted or short phrase likely to be verbatim)
    # Detection: query is 3–8 words AND contains common lyric/quote patterns
    # OR user wraps in quotes: "she say do you love me"
    if query.startswith('"') and query.endswith('"'):
        return {"k": 30, "mode": "exact", "dedupe": False}
    
    # Broad/thematic query (1–2 words or clearly thematic)
    if len(words) <= 2:
        return {"k": 15, "mode": "hybrid", "dedupe": True, "max_unique": 12}
    
    # Deep-dive query (specific entity — person, company, topic)
    if len(words) <= 6 and not any(w in query.lower() for w in ["what", "how", "why", "when", "did i"]):
        return {"k": 20, "mode": "hybrid", "dedupe": True, "max_unique": 15}
    
    # Conversational / question query
    return {"k": 15, "mode": "hybrid", "dedupe": True, "max_unique": 10}

def retrieve(query_text: str, n_results: int = None, deduplicate: bool = None) -> list[dict]:
    if not query_text or not query_text.strip():
        return SearchResultsList([], total_matches=0)

    # 1. Get parameters
    params = get_retrieval_params(query_text)
    k = params["k"]
    do_dedupe = deduplicate if deduplicate is not None else params["dedupe"]
    
    # If caller specifies limit, use it, else use max_unique if deduping, else k
    limit = n_results
    if limit is None:
        limit = params.get("max_unique", k) if do_dedupe else k

    # 2. Run Semantic Search
    semantic_chunks = []
    query_vector = embed(query_text)
    if query_vector:
        results = db.query(query_embeddings=[query_vector], n_results=k)
        if results and "ids" in results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results else [0.0] * len(ids)
            for i in range(len(ids)):
                semantic_chunks.append({
                    "chunk_id": ids[i],
                    "text": documents[i],
                    "metadata": metadatas[i],
                    "distance": float(distances[i])
                })

    # 3. Run Keyword Search (FTS5)
    keyword_chunks = []
    sanitized_q = sanitize_fts_query(query_text)
    if sanitized_q:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT notes.chunk_id, notes.source_id, notes.source, notes.title, notes.body, notes.created_at, notes.url
                FROM notes
                JOIN notes_fts ON notes.rowid = notes_fts.rowid
                WHERE notes_fts MATCH ?
                ORDER BY bm25(notes_fts) ASC
                LIMIT ?
            """, (sanitized_q, k))
            rows = cursor.fetchall()
            for row in rows:
                metadata = {
                    "source": row["source"],
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "url": row["url"]
                }
                # If there are chunk index details, they might be embedded or we can extract them
                # But typically chunk_id contains the chunk_index suffix: source_id + "_chunk_" + chunk_index
                chunk_index = 0
                if "_chunk_" in row["chunk_id"]:
                    try:
                        chunk_index = int(row["chunk_id"].split("_chunk_")[-1])
                    except ValueError:
                        pass
                metadata["chunk_index"] = chunk_index
                
                keyword_chunks.append({
                    "chunk_id": row["chunk_id"],
                    "text": row["body"],
                    "metadata": metadata
                })
        except Exception as e:
            print(f"Error querying FTS5: {e}")
        finally:
            conn.close()

    # 4. Merge using Reciprocal Rank Fusion (RRF, k=60)
    # First, collect all unique chunk_ids and build a mapping of chunk_id -> dict
    all_chunks_map = {}
    
    # Store ranks (1-indexed)
    semantic_ranks = {chunk["chunk_id"]: idx + 1 for idx, chunk in enumerate(semantic_chunks)}
    keyword_ranks = {chunk["chunk_id"]: idx + 1 for idx, chunk in enumerate(keyword_chunks)}
    
    # Populate the main chunks dictionary
    for chunk in semantic_chunks:
        cid = chunk["chunk_id"]
        all_chunks_map[cid] = {
            "id": cid,
            "text": chunk["text"],
            "metadata": chunk["metadata"]
        }
        
    for chunk in keyword_chunks:
        cid = chunk["chunk_id"]
        if cid not in all_chunks_map:
            all_chunks_map[cid] = {
                "id": cid,
                "text": chunk["text"],
                "metadata": chunk["metadata"]
            }

    # Calculate RRF score for each chunk
    RRF_K = 60.0
    merged_results = []
    for cid, chunk_data in all_chunks_map.items():
        score = 0.0
        if cid in semantic_ranks:
            score += 1.0 / (RRF_K + semantic_ranks[cid])
        if cid in keyword_ranks:
            score += 1.0 / (RRF_K + keyword_ranks[cid])
            
        chunk_data["rrf_score"] = score
        merged_results.append(chunk_data)

    # Sort merged results by RRF score descending
    merged_results.sort(key=lambda x: x["rrf_score"], reverse=True)
    total_matches = len(merged_results)

    # 5. Deduplicate if needed
    if do_dedupe:
        seen_sources = {}
        source_counts = {}
        for chunk in merged_results:
            meta = chunk["metadata"]
            sid = meta.get("source_id") or chunk["id"]
            
            source_counts[sid] = source_counts.get(sid, 0) + 1
            if sid not in seen_sources:
                seen_sources[sid] = chunk
                
        # Add chunk_count to the selected unique chunks
        for sid, chunk in seen_sources.items():
            chunk["chunk_count"] = source_counts[sid]
            
        final_list = list(seen_sources.values())[:limit]
    else:
        # Just return sorted list up to limit
        final_list = merged_results[:limit]

    return SearchResultsList(final_list, total_matches=total_matches)
