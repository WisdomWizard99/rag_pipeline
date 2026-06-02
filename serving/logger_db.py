"""
logger_db.py
Logs every RAG query to a local DuckDB database.
dbt will read from this to build analytics models.
"""

import duckdb
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("DUCKDB_PATH", os.path.join(BASE_DIR, "analytics", "rag_logs.duckdb"))

def init_db():
    """Create logs table if it doesn't exist."""
    os.makedirs("analytics", exist_ok=True)
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id          INTEGER PRIMARY KEY,
            question    TEXT,
            answer      TEXT,
            latency_ms  FLOAT,
            top_k       INTEGER,
            num_sources INTEGER,
            avg_score   FLOAT,
            timestamp   TIMESTAMP,
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_metadata (
            chunk_id    INTEGER,
            source      TEXT,
            url         TEXT,
            published   DATE,
            text_length INTEGER,
            ingested_at TIMESTAMP,
        )
    """)
    conn.close()

def log_query(
    question: str,
    answer: str,
    latency_ms: float,
    top_k: int,
    sources: list[dict],
):
    """Log one query + its results to DuckDB."""
    conn = duckdb.connect(DB_PATH)

    avg_score = round(
        sum(s["score"] for s in sources) / len(sources), 4
    ) if sources else 0.0

    conn.execute("""
        INSERT INTO query_logs
        VALUES (
            (SELECT COALESCE(MAX(id), 0) + 1 FROM query_logs),
            ?, ?, ?, ?, ?, ?, ?
        )
    """, [
        question,
        answer,
        latency_ms,
        top_k,
        len(sources),
        avg_score,
        datetime.utcnow(),
    ])
    conn.close()