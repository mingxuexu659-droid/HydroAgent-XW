"""Build a local Chroma vector store for Xinwu report paragraphs."""
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = BASE_DIR / "data_processed"
REPORT_FILE = PROCESSED_DIR / "reports.jsonl"
VECTOR_DIR = BASE_DIR / "vector_store" / "xinwu_reports"

COLLECTION_NAME = "xinwu_report_paragraphs"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_report_records():
    if not REPORT_FILE.exists():
        raise FileNotFoundError(f"找不到报告解析文件：{REPORT_FILE}")

    records = []
    with REPORT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = record.get("text", "").strip()
            if text:
                records.append(record)

    return records


def main():
    records = load_report_records()
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    print(f"读取报告段落数量：{len(records)}")
    print(f"加载 embedding 模型：{MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=str(VECTOR_DIR))

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Xinwu water environment report paragraphs"}
    )

    ids = []
    documents = []
    metadatas = []

    for index, record in enumerate(records):
        ids.append(f"{record.get('doc_id', 'report')}_{record.get('paragraph_index', index)}")
        documents.append(record["text"])
        metadatas.append({
            "source": record.get("source", ""),
            "doc_id": record.get("doc_id", ""),
            "paragraph_index": int(record.get("paragraph_index", index)),
            "data_type": record.get("metadata", {}).get("data_type", "report"),
            "domain": record.get("metadata", {}).get("domain", "water_environment"),
            "district": record.get("metadata", {}).get("district", "新吴区")
        })

    print("开始生成向量，这一步第一次会比较慢...")

    embeddings = model.encode(
        documents,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    ).tolist()

    existing = collection.get(include=[])
    if existing.get("ids"):
        collection.delete(ids=existing["ids"])

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings
    )

    print("向量库构建完成")
    print(f"保存位置：{VECTOR_DIR}")
    print(f"collection：{COLLECTION_NAME}")


if __name__ == "__main__":
    main()
