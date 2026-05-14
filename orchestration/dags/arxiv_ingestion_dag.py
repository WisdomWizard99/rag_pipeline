"""
arxiv_ingestion_dag.py
Daily pipeline — fetches ArXiv papers, chunks them,
validates quality, and stores vectors in Qdrant.
"""

from datetime import datetime, timedelta
from airflow.decorators import dag, task
import logging

logger = logging.getLogger(__name__)

default_args = {
    "owner"           : "rag-pipeline",
    "retries"         : 2,
    "retry_delay"     : timedelta(minutes=5),
    "email_on_failure": False,
}

@dag(
    dag_id="arxiv_ingestion_pipeline",
    description="Fetch ArXiv papers daily and store in Qdrant",
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["rag", "ingestion", "arxiv"],
)
def arxiv_ingestion_pipeline():

    @task()
    def fetch_papers() -> list[dict]:
        import arxiv
        search = arxiv.Search(
            query="retrieval augmented generation large language models",
            max_results=10,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        client = arxiv.Client()
        papers = []
        for result in client.results(search):
            papers.append({
                "title"    : result.title,
                "abstract" : result.summary,
                "url"      : result.entry_id,
                "pdf_url"  : result.pdf_url,
                "published": str(result.published.date()),
            })
            logger.info(f"Fetched: {result.title[:60]}")
        logger.info(f"Total papers fetched: {len(papers)}")
        return papers

    @task()
    def download_pdfs(papers: list[dict]) -> list[dict]:
        import urllib.request
        import os
        import time
        os.makedirs("/tmp/arxiv_papers", exist_ok=True)
        for i, paper in enumerate(papers):
            filepath = f"/tmp/arxiv_papers/paper_{i}.pdf"
            if os.path.exists(filepath):
                paper["local_path"] = filepath
                continue
            try:
                urllib.request.urlretrieve(paper["pdf_url"], filepath)
                paper["local_path"] = filepath
                logger.info(f"Downloaded: {paper['title'][:50]}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed: {paper['title'][:50]} → {e}")
                paper["local_path"] = None
        return papers

    @task()
    def extract_and_chunk(papers: list[dict]) -> list[dict]:
        import fitz
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        chunker = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " "],
        )
        all_chunks = []
        for paper in papers:
            if not paper.get("local_path"):
                continue
            try:
                doc = fitz.open(paper["local_path"])
                full_text = ""
                for page_num, page in enumerate(doc):
                    full_text += f"\n[Page {page_num + 1}]\n{page.get_text()}"
                doc.close()
                all_chunks.append({
                    "text"     : f"Abstract: {paper['abstract']}",
                    "source"   : paper["title"],
                    "url"      : paper["url"],
                    "published": paper["published"],
                    "chunk_id" : -1,
                })
                for i, chunk in enumerate(chunker.split_text(full_text)):
                    all_chunks.append({
                        "text"     : chunk,
                        "source"   : paper["title"],
                        "url"      : paper["url"],
                        "published": paper["published"],
                        "chunk_id" : i,
                    })
            except Exception as e:
                logger.error(f"Failed to process {paper['title']}: {e}")
        logger.info(f"Total chunks: {len(all_chunks)}")
        return all_chunks

    @task()
    def validate_quality(chunks: list[dict]) -> list[dict]:
        valid = []
        quarantined = 0
        for chunk in chunks:
            text = chunk.get("text", "")
            if not text.strip():
                quarantined += 1
                continue
            if len(text) < 50:
                quarantined += 1
                continue
            try:
                text.encode("utf-8").decode("utf-8")
            except UnicodeDecodeError:
                quarantined += 1
                continue
            alpha_ratio = sum(c.isalpha() for c in text) / len(text)
            if alpha_ratio < 0.3:
                quarantined += 1
                continue
            valid.append(chunk)
        logger.info(f"Quality: {len(valid)} passed, {quarantined} quarantined")
        if len(valid) == 0:
            raise ValueError("All chunks failed quality check!")
        return valid

    @task()
    def embed_and_store(chunks: list[dict]) -> str:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        import os
        embedder = SentenceTransformer("all-MiniLM-L6-v2")
        qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "host.docker.internal"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
        )
        COLLECTION = "arxiv_rag"
        if qdrant.collection_exists(COLLECTION):
            qdrant.delete_collection(COLLECTION)
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        total_stored = 0
        for batch_start in range(0, len(chunks), 64):
            batch = chunks[batch_start : batch_start + 64]
            embeddings = embedder.encode([c["text"] for c in batch], show_progress_bar=False)
            points = [
                PointStruct(
                    id=batch_start + i,
                    vector=emb.tolist(),
                    payload={k: chunk[k] for k in ["text","source","url","published","chunk_id"]}
                )
                for i, (chunk, emb) in enumerate(zip(batch, embeddings))
            ]
            qdrant.upsert(collection_name=COLLECTION, points=points)
            total_stored += len(points)
        result = f"Stored {total_stored} vectors in Qdrant"
        logger.info(result)
        return result

    # Wire up dependencies
    papers = fetch_papers()
    papers_with_paths = download_pdfs(papers)
    chunks = extract_and_chunk(papers_with_paths)
    valid_chunks = validate_quality(chunks)
    embed_and_store(valid_chunks)

arxiv_ingestion_pipeline()