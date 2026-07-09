"""
Run this script once to load your hotel knowledge base into Pinecone.
Supports: PDF files, plain text files, and website URLs.

Usage:
    python knowledge_base/ingest.py
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pinecone import Pinecone

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY")
PINECONE_HOST      = os.getenv("PINECONE_HOST")
PINECONE_INDEX     = os.getenv("PINECONE_INDEX_NAME")
EMBED_MODEL        = os.getenv("PINECONE_EMBED_MODEL", "llama-text-embed-v2")

pc    = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=PINECONE_HOST)


def chunk_text(text: str, chunk_size: int = 100, overlap: int = 20) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return [c for c in chunks if len(c.strip()) > 30]


def load_pdf(filepath: str) -> str:
    reader = PdfReader(filepath)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_url(url: str) -> str:
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def load_text_file(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Use Pinecone's built-in llama-text-embed-v2 to embed text chunks."""
    result = pc.inference.embed(
        model=EMBED_MODEL,
        inputs=chunks,
        parameters={"input_type": "passage", "truncate": "END"}
    )
    return [item["values"] for item in result.data]


def ingest_documents(sources: dict):
    """
    sources = {
        "pdfs":  ["data/hotel_brochure.pdf"],
        "urls":  ["https://yourhotel.com/rooms"],
        "texts": ["data/faq.txt"],
    }
    """
    all_chunks = []

    for pdf_path in sources.get("pdfs", []):
        print(f"Loading PDF: {pdf_path}")
        text = load_pdf(pdf_path)
        for i, chunk in enumerate(chunk_text(text)):
            all_chunks.append({"id": f"pdf-{os.path.basename(pdf_path)}-{i}", "text": chunk})

    for url in sources.get("urls", []):
        print(f"Loading URL: {url}")
        text = load_url(url)
        for i, chunk in enumerate(chunk_text(text)):
            slug = url.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
            all_chunks.append({"id": f"url-{slug}-{i}", "text": chunk})

    for txt_path in sources.get("texts", []):
        print(f"Loading text file: {txt_path}")
        text = load_text_file(txt_path)
        for i, chunk in enumerate(chunk_text(text)):
            all_chunks.append({"id": f"txt-{os.path.basename(txt_path)}-{i}", "text": chunk})

    if not all_chunks:
        print("No documents found. Add your files/URLs to the sources dict and re-run.")
        return

    print(f"\nTotal chunks: {len(all_chunks)} — embedding with {EMBED_MODEL}...")

    # Embed and upsert in batches of 50
    batch_size = 50
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [item["text"] for item in batch]

        embeddings = embed_chunks(texts)

        vectors = [
            {
                "id": batch[j]["id"],
                "values": embeddings[j],
                "metadata": {"text": batch[j]["text"]}
            }
            for j in range(len(batch))
        ]

        index.upsert(vectors=vectors)
        print(f"  Upserted batch {i // batch_size + 1} / {(len(all_chunks) + batch_size - 1) // batch_size}")

    print("\nKnowledge base ingestion complete!")
    stats = index.describe_index_stats()
    print(f"Total records in index: {stats.total_vector_count}")


if __name__ == "__main__":
    sources = {
        "pdfs":  [],
        "urls":  [],
        "texts": [
            "data/hotel_knowledge.txt",
        ],
    }
    ingest_documents(sources)
