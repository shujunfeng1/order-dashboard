"""
Excel 解析模块
从邮件附件 Excel 中提取卡单数据，进行字段映射和数据清洗。
"""

import pandas as pd
import sys
import os
from pathlib import Path


def parse_excel(file_path, config):
    """
    解析 Excel 文件，提取标准化数据。

    Args:
        file_path: Excel 文件路径
        config: 配置字典

    Returns:
        pandas.DataFrame: 清洗后的标准化数据
    """
    excel_config = config["excel"]
    sheet_name = excel_config["sheet_name"]

    # 读取 Excel
    df = pd.read_excel(file_path, sheet_name=sheet_name)

    # 获取字段映射
    field_mapping = excel_config["field_mapping"]

    # 验证所有映射字段都存在
    missing_fields = [f for f in field_mapping.keys() if f not in df.columns]
    if missing_fields:
        print(f"[警告] 以下字段在 Excel 中不存在: {missing_fields}")
        print(f"可用列: {list(df.columns)}")

    # 只保留需要的字段
    needed_fields = list(field_mapping.keys())
    available_fields = [f for f in needed_fields if f in df.columns]
    df = df[available_fields].copy()

    # 空白值替换为 "公海"
    blank_replacement = excel_config.get("blank_replacement", "公海")
    blank_fields = excel_config.get("blank_fields", [])

    for field in blank_fields:
        if field in df.columns:
            df[field] = df[field].fillna(blank_replacement)
            df[field] = df[field].astype(str).str.strip()
            df[field] = df[field].replace("", blank_replacement)
            df[field] = df[field].replace("nan", blank_replacement)
            df[field] = df[field].replace("None", blank_replacement)

    # 数据类型转换
    if "实付GMV" in df.columns:
        df["实付GMV"] = pd.to_numeric(df["实付GMV"], errors="coerce").fillna(0)

    # 订单编号转为字符串（保留前导零）
    if "订单编号" in df.columns:
        df["订单编号"] = df["订单编号"].astype(str).str.strip()

    # 客户ID转为字符串
    if "客户ID" in df.columns:
        df["客户ID"] = df["客户ID"].astype(str).str.strip()

    # 下单BD工号转为字符串
    if "下单BD工号" in df.columns:
        df["下单BD工号"] = df["下单BD工号"].astype(str).str.strip()
        df["下单BD工号"] = df["下单BD工号"].replace("nan", blank_replacement)
        df["下单BD工号"] = df["下单BD工号"].replace("None", blank_replacement)

    print(f"[Excel解析] 成功解析 {len(df)} 条记录")
    print(f"[Excel解析] 字段: {list(df.columns)}")

    return df


if __name__ == "__main__":
    import json

    config_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 测试
    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    if test_file:
        df = parse_excel(test_file, config)
        print(f"\n数据概览:")
        print(df.head(10).to_string())
        print(f"\n总行数: {len(df)}")
    else:
        print("用法: python excel_parser.py <excel_file_path>")
