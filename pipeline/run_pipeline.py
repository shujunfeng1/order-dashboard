"""
管道主入口（GitHub Actions 版）
串联：邮件读取 → Excel 解析 → 数据处理 → 输出到 docs/
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from excel_parser import parse_excel
from data_processor import process_data, save_json


def run_pipeline(excel_file=None, config=None):
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config_path = project_root / "config" / "settings.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 步骤 1: 获取 Excel
    if excel_file is None:
        print("=" * 50)
        print("步骤 1: 从邮件获取附件")
        print("=" * 50)
        from email_reader import fetch_and_download
        attachments_dir = project_root / "attachments"
        files = fetch_and_download(config, attachments_dir)
        if not files:
            print("[管道] 未获取到附件，流程终止")
            return None
        excel_file = files[0]
        if len(files) > 1:
            excel_file = max(files, key=lambda f: Path(f).stat().st_mtime)
    else:
        print(f"步骤 1: 使用本地文件: {excel_file}")

    # 步骤 2: 解析 Excel
    print("\n" + "=" * 50)
    print("步骤 2: 解析 Excel")
    print("=" * 50)
    df = parse_excel(excel_file, config)

    # 步骤 3: 数据处理
    print("\n" + "=" * 50)
    print("步骤 3: 数据处理")
    print("=" * 50)
    result = process_data(df, config)

    # 步骤 4: 输出到 docs/
    print("\n" + "=" * 50)
    print("步骤 4: 保存到 docs/")
    print("=" * 50)
    json_path = docs_dir / "dashboard_data.json"
    save_json(result, json_path)

    # 删除旧 Excel，保存新的
    for old in docs_dir.glob("*.xlsx"):
        old.unlink()
    detail_excel_name = f"卡单明细_{result['meta']['data_date']}.xlsx"
    detail_excel_path = docs_dir / detail_excel_name
    df.to_excel(detail_excel_path, index=False, sheet_name="卡单明细")
    print(f"[管道] Excel: {detail_excel_path}")

    result["meta"]["detail_excel"] = detail_excel_name
    save_json(result, json_path)

    print("\n管道执行完成!")
    print(f"  JSON: {json_path}")
    print(f"  Excel: {detail_excel_path}")
    return str(json_path)


if __name__ == "__main__":
    excel_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(excel_file)
