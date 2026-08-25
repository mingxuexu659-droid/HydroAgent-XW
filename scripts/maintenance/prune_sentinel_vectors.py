"""Remove stale Sentinel-2 embeddings from the local generated vector index.

The vector index is ignored by Git. Back it up before running this maintenance
utility because the removed vectors are regenerated on the next catalog update.
"""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector_db.json"


def main() -> None:
    if not VECTOR_DB_PATH.exists():
        raise SystemExit(f"Vector database not found: {VECTOR_DB_PATH}")

    with VECTOR_DB_PATH.open("r", encoding="utf-8") as file:
        vector_db = json.load(file)

    original_count = len(vector_db.get("vectors", []))
    kept_vectors = []
    removed = 0

    for vector in vector_db.get("vectors", []):
        description = vector.get("description", "").lower()
        if "sentinel" in description:
            removed += 1
            print(f"  Removed: {vector.get('dataset_id', '')[:16]}... ({description[:60]}...)")
        else:
            kept_vectors.append(vector)

    vector_db["vectors"] = kept_vectors
    vector_db.setdefault("metadata", {})["total_vectors"] = len(kept_vectors)

    with VECTOR_DB_PATH.open("w", encoding="utf-8") as file:
        json.dump(vector_db, file, ensure_ascii=False, indent=2)

    print(f"\nRemoved {removed} Sentinel vectors ({original_count} -> {len(kept_vectors)})")
    print("Run the catalog builder to regenerate vectors with corrected descriptions.")


if __name__ == "__main__":
    main()
