import sys

# Add project root to path
sys.path.append(".")

from core.embedder import embed
from core.vectorstore import VectorStore
from core.database import get_connection

print("Initializing VectorStore...")
db = VectorStore()
print("VectorStore initialized.")

print("\nStep 1: Testing embed('ambition')...")
try:
    v = embed("ambition")
    print("Embed success. Length of vector:", len(v) if v else None)
except Exception as e:
    print("Embed failed:", e)
    v = None

print("\nStep 2: Testing ChromaDB db.query()...")
if v:
    try:
        res = db.query(query_embeddings=[v], n_results=5)
        print("ChromaDB query success. Results IDs:", res.get("ids") if res else None)
    except Exception as e:
        print("ChromaDB query failed:", e)
else:
    print("Skipping ChromaDB test since embedding failed/returned None.")

print("\nStep 3: Testing SQLite FTS5 database connection...")
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("SQLite query success. Tables:", [r[0] for r in cursor.fetchall()])
    conn.close()
    print("SQLite connection closed.")
except Exception as e:
    print("SQLite connection/query failed:", e)

print("\nStep 4: Testing SQLite Notes table query...")
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM notes")
    print("SQLite notes count:", cursor.fetchone()[0])
    conn.close()
except Exception as e:
    print("SQLite notes count query failed:", e)
