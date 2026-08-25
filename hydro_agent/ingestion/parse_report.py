import json
from pathlib import Path

from docx import Document


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_REPORT_DIR = BASE_DIR / "data_raw" / "xinwu" / "reports"
OUTPUT_FILE = BASE_DIR / "data_processed" / "reports.jsonl"


def parse_docx(file_path: Path):
    document = Document(file_path)
    records = []

    for index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue

        records.append({
            "doc_id": file_path.stem,
            "source": file_path.name,
            "paragraph_index": index,
            "text": text,
            "metadata": {
                "district": "新吴区",
                "domain": "water_environment",
                "data_type": "report"
            }
        })

    return records


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_records = []
    for file_path in RAW_REPORT_DIR.glob("*.docx"):
        all_records.extend(parse_docx(file_path))

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"解析完成，共 {len(all_records)} 个段落")
    print(f"输出文件：{OUTPUT_FILE}")


if __name__ == "__main__":
    main()