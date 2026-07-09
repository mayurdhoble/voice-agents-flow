import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(host=os.getenv("PINECONE_HOST"))
EMBED_MODEL = os.getenv("PINECONE_EMBED_MODEL", "llama-text-embed-v2")


def retrieve_context(query: str, top_k: int = 4) -> str:
    """Embed the caller's query using Pinecone's llama-text-embed-v2
    and return the most relevant hotel knowledge chunks."""

    result = pc.inference.embed(
        model=EMBED_MODEL,
        inputs=[query],
        parameters={"input_type": "query", "truncate": "END"}
    )
    query_vector = result.data[0]["values"]

    matches = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True
    )

    if not matches.matches:
        return "No specific information found in the knowledge base."

    chunks = [m.metadata["text"] for m in matches.matches]
    return "\n\n".join(chunks) if chunks else "No relevant information found."
