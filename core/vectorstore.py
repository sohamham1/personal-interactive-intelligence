import chromadb
import os

DB_PATH = os.path.join("data", "chroma_db")

class VectorStore:
    def __init__(self, path: str = DB_PATH):
        # Create directories if they do not exist
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name="personal_kb")

    def add_documents(self, texts: list[str], metadatas: list[dict], ids: list[str], embeddings: list[list[float]]):
        """
        Adds documents with pre-computed embeddings and metadata to the collection.
        """
        if not ids:
            return
            
        self.collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings
        )

    def query(self, query_embeddings: list[list[float]], n_results: int = 5) -> dict:
        """
        Queries ChromaDB collection with query embeddings and returns nearest matches.
        """
        return self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results
        )

    def get_count(self) -> int:
        """
        Returns the total number of documents indexed in the collection.
        """
        try:
            return self.collection.count()
        except Exception:
            return 0
