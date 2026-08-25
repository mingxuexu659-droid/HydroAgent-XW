"""Retrieve relevant Xinwu report paragraphs from the local Chroma store."""
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parents[2]
VECTOR_DIR = BASE_DIR / "vector_store" / "xinwu_reports"

COLLECTION_NAME = "xinwu_report_paragraphs"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def retrieve_report_chunks(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    if not VECTOR_DIR.exists():
        raise FileNotFoundError(
            f"找不到向量库：{VECTOR_DIR}。请先运行 hydro_agent/rag/build_report_vector_store.py"
        )

    model = SentenceTransformer(MODEL_NAME)
    query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()

    client = chromadb.PersistentClient(path=str(VECTOR_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for document, metadata, distance in zip(documents, metadatas, distances):
        chunks.append({
            "text": document,
            "source": metadata.get("source", ""),
            "paragraph_index": metadata.get("paragraph_index", ""),
            "distance": distance
        })

    return chunks


if __name__ == "__main__":
    for item in retrieve_report_chunks("新吴区水环境整治目标是什么？", top_k=3):
        print(item)
