"""
api.py
FastAPI RAG endpoint — POST /query returns grounded answers.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import os
import time

from retriever import retrieve
from logger_db import init_db, log_query
from metrics import (
    QUERY_COUNTER,
    UNANSWERED_COUNTER,
    QUERY_LATENCY,
    RETRIEVAL_SCORE,
    CURRENT_TOP_K,
)

load_dotenv()

# Initialize DB on startup
init_db()

app = FastAPI(
    title="RAG Pipeline API",
    description="Query ArXiv AI papers using RAG",
    version="1.0.0",
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Request / Response models ───────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 8

class SourceDoc(BaseModel):
    source: str
    url: str
    score: float
    published: str

class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceDoc]
    latency_ms: float

# ── Routes ──────────────────────────────────────────────────

@app.get("/health")
def health():
    """Check if the API is running."""
    return {"status": "ok", "service": "rag-pipeline"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint — scraped every 15 seconds."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """
    Main RAG endpoint.
    1. Embed question
    2. Retrieve top-k chunks from Qdrant
    3. Ask Groq LLM with context
    4. Return answer + sources
    """
    start = time.time()

    # Validate input
    if not request.question.strip():
        QUERY_COUNTER.labels(status="error").inc()
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Step 1 + 2 — retrieve
    chunks = retrieve(request.question, top_k=request.top_k)

    if not chunks:
        QUERY_COUNTER.labels(status="error").inc()
        raise HTTPException(status_code=404, detail="No relevant chunks found")

    # Step 3 — build context
    context = "\n\n".join([
        f"[{c['source']}]\n{c['text']}"
        for c in chunks
    ])

    # Step 4 — ask LLM
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Answer using ONLY "
                    "the context provided. Always cite which paper your "
                    "answer comes from. If the context doesn't contain "
                    "the answer, say 'I don't know based on the provided context'."
                )
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {request.question}"
            }
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content
    latency = round((time.time() - start) * 1000, 2)

    # ── Track metrics ───────────────────────────────────────
    QUERY_COUNTER.labels(status="success").inc()
    QUERY_LATENCY.observe(latency)
    CURRENT_TOP_K.set(request.top_k)

    for chunk in chunks:
        RETRIEVAL_SCORE.observe(chunk["score"])

    if "don't know" in answer.lower():
        UNANSWERED_COUNTER.inc()

    # ── Log to DuckDB ───────────────────────────────────────
    log_query(
        question=request.question,
        answer=answer,
        latency_ms=latency,
        top_k=request.top_k,
        sources=chunks,
    )

    return QueryResponse(
        question=request.question,
        answer=answer,
        sources=[
            SourceDoc(**{k: v for k, v in c.items() if k != "text"})
            for c in chunks
        ],
        latency_ms=latency,
    )