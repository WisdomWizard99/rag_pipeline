"""
retriever.py
Handles embedding queries and retrieving chunks from Qdrant.
"""

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
import os

# Load once at startup — not on every request
embedder = SentenceTransformer("all-MiniLM-L6-v2")

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST", "localhost"),
    port=int(os.getenv("QDRANT_PORT", 6333)),
)

COLLECTION = os.getenv("COLLECTION_NAME", "arxiv_rag")
TOP_K = 5


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    """
    Embed the question and retrieve top-k matching chunks from Qdrant.
    """
    # Embed the question
    q_vector = embedder.encode([question])[0].tolist()

    # Search Qdrant — using .search() for compatibility
    hits = qdrant.search(
        collection_name=COLLECTION,
        query_vector=q_vector,
        limit=top_k,
    )

    # Return clean list of results
    return [
        {
            "text"     : hit.payload["text"],
            "source"   : hit.payload["source"],
            "url"      : hit.payload["url"],
            "published": hit.payload["published"],
            "score"    : round(hit.score, 4),
        }
        for hit in hits
    ]