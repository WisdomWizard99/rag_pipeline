"""
api.py
FastAPI RAG endpoint — POST /query returns grounded answers.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
import os
import time

from retriever import retrieve

load_dotenv()

app = FastAPI(
    title="RAG Pipeline API",
    description="Query ArXiv AI papers using RAG",
    version="1.0.0",
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Request / Response models ──────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5

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

# ── Routes ─────────────────────────────────────────────────

@app.get("/health")
def health():
    """Check if the API is running."""
    return {"status": "ok", "service": "rag-pipeline"}


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

    # Step 1 + 2 — retrieve
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    chunks = retrieve(request.question, top_k=request.top_k)

    if not chunks:
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

    return QueryResponse(
        question=request.question,
        answer=answer,
        sources=[SourceDoc(**{k: v for k, v in c.items() if k != "text"}) for c in chunks],
        latency_ms=latency,
    )