from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_EXCEL_DIR = BASE_DIR / "data_raw" / "xinwu" / "excel"
OUTPUT_DIR = BASE_DIR / "data_processed"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    excel_files = list(RAW_EXCEL_DIR.glob("*.xlsx"))
    if not excel_files:
        print("没有找到 xlsx 文件")
        return

    for excel_file in excel_files:
        sheets = pd.read_excel(excel_file, sheet_name=None)

        for sheet_name, df in sheets.items():
            output_name = f"{excel_file.stem}_{sheet_name}.csv"
            output_file = OUTPUT_DIR / output_name

            df.to_csv(output_file, index=False, encoding="utf-8-sig")

            print(f"已解析：{excel_file.name} / {sheet_name}")
            print(f"行数：{len(df)}，列数：{len(df.columns)}")
            print(f"输出：{output_file}")
            print("字段：", list(df.columns))


if __name__ == "__main__":
    main()