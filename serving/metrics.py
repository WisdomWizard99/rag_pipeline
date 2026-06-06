"""
metrics.py
Prometheus metrics for the RAG API.
Tracks query count, latency, retrieval scores, errors.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

# ── Counters — things that only go up ──────────────────────

# Total queries received
QUERY_COUNTER = Counter(
    "rag_queries_total",
    "Total number of RAG queries received",
    ["status"]          # label: success or error
)

# Total unanswered queries
UNANSWERED_COUNTER = Counter(
    "rag_unanswered_total",
    "Total queries where LLM said I don't know"
)

# ── Histograms — track distributions ───────────────────────

# Query latency in milliseconds
QUERY_LATENCY = Histogram(
    "rag_query_latency_ms",
    "RAG query latency in milliseconds",
    buckets=[100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]
)

# Retrieval score distribution
RETRIEVAL_SCORE = Histogram(
    "rag_retrieval_score",
    "Qdrant retrieval similarity scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# ── Gauges — current value, can go up or down ──────────────

# Current top_k setting being used
CURRENT_TOP_K = Gauge(
    "rag_current_top_k",
    "Current top_k value used for retrieval"
)

