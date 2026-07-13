"""
管道主入口
串联：邮件读取 → Excel 解析 → 数据处理 → 生成 JSON
"""

import json
import sys
import os
import shutil
from pathlib import Path

# 加载本地 .env 凭据（parent.parent 指向项目根目录）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # GitHub Actions 环境通过 secrets 注入，无需 python-dotenv

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from excel_parser import parse_excel
from data_processor import process_data, save_json


def run_pipeline(excel_file=None, config=None):
    """
    执行完整数据管道。

    Args:
        excel_file: Excel 文件路径。如果为 None，则从邮件获取。
        config: 配置字典。如果为 None，则从配置文件加载。

    Returns:
        str: 生成的 JSON 文件路径
    """
    # 加载配置
    if config is None:
        config_path = Path(__file__).parent.parent / "config" / "settings.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 项目根目录
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "web" / "static" / "data"
    exports_dir = project_root / "web" / "static" / "exports"
    data_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    # ========== 步骤 1: 获取 Excel 文件 ==========
    if excel_file is None:
        # 从邮件获取
        print("=" * 60)
        print("步骤 1: 从邮件获取附件")
        print("=" * 60)
        from email_reader import fetch_and_download

        attachments_dir = project_root / "attachments"
        files = fetch_and_download(config, attachments_dir)

        if not files:
            print("[管道] 未获取到附件，流程终止")
            return None

        # 取最新的 Excel 文件
        excel_file = files[0]
        if len(files) > 1:
            # 多个附件时，取最新的
            excel_file = max(files, key=lambda f: Path(f).stat().st_mtime)
    else:
        print("=" * 60)
        print(f"步骤 1: 使用本地文件: {excel_file}")
        print("=" * 60)

    # ========== 步骤 2: 解析 Excel ==========
    print("\n" + "=" * 60)
    print("步骤 2: 解析 Excel")
    print("=" * 60)
    df = parse_excel(excel_file, config)

    # ========== 步骤 3: 数据处理 ==========
    print("\n" + "=" * 60)
    print("步骤 3: 数据处理")
    print("=" * 60)
    result = process_data(df, config)

    # ========== 步骤 4: 保存 JSON ==========
    print("\n" + "=" * 60)
    print("步骤 4: 保存数据")
    print("=" * 60)
    json_path = data_dir / "dashboard_data.json"
    save_json(result, json_path)

    # 同时保存一份明细 Excel 供下载
    detail_excel_path = exports_dir / f"卡单明细_{result['meta']['data_date']}.xlsx"
    df.to_excel(detail_excel_path, index=False, sheet_name="卡单明细")
    print(f"[管道] 明细 Excel 已保存: {detail_excel_path}")

    # 保存最新明细路径到 JSON
    result["meta"]["detail_excel"] = detail_excel_path.name
    save_json(result, json_path)

    print("\n" + "=" * 60)
    print("管道执行完成!")
    print(f"  JSON: {json_path}")
    print(f"  Excel: {detail_excel_path}")
    print("=" * 60)

    return str(json_path)


if __name__ == "__main__":
    # 支持命令行传入 Excel 文件路径
    excel_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(excel_file)
