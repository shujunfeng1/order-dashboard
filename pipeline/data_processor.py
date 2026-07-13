"""
数据处理模块
对解析后的卡单数据进行聚合计算，生成看板所需的 JSON 数据。
"""

import pandas as pd
import json
from datetime import datetime
from pathlib import Path


def process_data(df, config):
    """
    处理数据，生成看板 JSON。

    Args:
        df: 解析后的 DataFrame
        config: 配置字典

    Returns:
        dict: 看板数据 JSON
    """
    dashboard_config = config["dashboard"]
    metrics = dashboard_config["metrics"]
    filter_fields = dashboard_config["filter_fields"]

    # ========== 1. KPI 卡片 ==========
    kpi = {}
    for metric_name, metric_config in metrics.items():
        col = metric_config["column"]
        agg = metric_config["agg"]
        if col not in df.columns:
            kpi[metric_name] = 0
            continue
        if agg == "nunique":
            kpi[metric_name] = int(df[col].nunique())
        elif agg == "count":
            kpi[metric_name] = int(len(df))
        elif agg == "sum":
            kpi[metric_name] = float(df[col].sum())
    # GMV 保留两位小数
    if "涉及实付GMV" in kpi:
        kpi["涉及实付GMV"] = round(kpi["涉及实付GMV"], 2)

    # ========== 2. 筛选器选项 ==========
    filters = {}
    for field in filter_fields:
        if field in df.columns:
            values = df[field].dropna().unique().tolist()
            filters[field] = sorted([str(v) for v in values])
        else:
            filters[field] = []

    # ========== 3. 图表数据 ==========
    charts = {}

    # 大区卡单分布（柱状图）
    if "大区" in df.columns:
        region_agg = df.groupby("大区").agg(
            卡单订单数=("订单编号", "count"),
            涉及实付GMV=("实付GMV", "sum") if "实付GMV" in df.columns else ("大区", "count"),
        ).reset_index()
        charts["region"] = {
            "categories": region_agg["大区"].tolist(),
            "values": region_agg["卡单订单数"].tolist(),
        }

    # 异常原因分类（横向柱状图，同时含订单数和GMV两个维度）
    if "异常原因分类" in df.columns:
        reason_agg = df.groupby("异常原因分类").agg(
            order_count=("订单编号", "count"),
            gmv=("实付GMV", "sum") if "实付GMV" in df.columns else ("订单编号", "count"),
        ).reset_index().sort_values("order_count", ascending=False)
        charts["reason"] = [
            {
                "name": str(row["异常原因分类"]),
                "order_count": int(row["order_count"]),
                "gmv": round(float(row["gmv"]), 2),
            }
            for _, row in reason_agg.iterrows()
        ]

    # 业绩归属分布（饼图）
    if "业绩归属" in df.columns:
        ownership_counts = df["业绩归属"].value_counts()
        charts["ownership"] = [
            {"name": str(name), "value": int(count)}
            for name, count in ownership_counts.items()
        ]

    # ========== 4. 聚合表（大区+省区+组别） ==========
    grouping_fields = dashboard_config["grouping_fields"]
    available_group_fields = [f for f in grouping_fields if f in df.columns]

    agg_dict = {}
    for metric_name, metric_config in metrics.items():
        col = metric_config["column"]
        agg = metric_config["agg"]
        if col in df.columns:
            if agg == "nunique":
                agg_dict[metric_name] = (col, "nunique")
            elif agg == "count":
                agg_dict[metric_name] = (col, "count")
            elif agg == "sum":
                agg_dict[metric_name] = (col, "sum")

    if available_group_fields and agg_dict:
        grouped = df.groupby(available_group_fields, dropna=False).agg(**agg_dict).reset_index()
        # GMV 保留两位小数
        if "涉及实付GMV" in grouped.columns:
            grouped["涉及实付GMV"] = grouped["涉及实付GMV"].round(2)
        # 排序：按卡单订单数降序
        if "卡单订单数" in grouped.columns:
            grouped = grouped.sort_values("卡单订单数", ascending=False)
        # 转为列表
        table_data = grouped.to_dict("records")
        # 确保所有值为可序列化类型
        for row in table_data:
            for key, val in row.items():
                if pd.isna(val):
                    row[key] = ""
                elif isinstance(val, (int, float)):
                    row[key] = float(val) if isinstance(val, float) else int(val)
                else:
                    row[key] = str(val)
    else:
        table_data = []

    # ========== 5. 明细数据 ==========
    detail_data = df.to_dict("records")
    for row in detail_data:
        for key, val in row.items():
            if pd.isna(val):
                row[key] = ""
            elif isinstance(val, (int, float)):
                if isinstance(val, float):
                    row[key] = round(val, 2)
                else:
                    row[key] = int(val)
            else:
                row[key] = str(val)

    # ========== 6. 组装最终 JSON ==========
    result = {
        "meta": {
            "data_date": datetime.now().strftime("%Y-%m-%d"),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_records": len(df),
        },
        "kpi": kpi,
        "filters": filters,
        "charts": charts,
        "table": table_data,
        "detail": detail_data,
    }

    print(f"[数据处理] KPI: {kpi}")
    print(f"[数据处理] 筛选器: { {k: len(v) for k, v in filters.items()} }")
    print(f"[数据处理] 聚合表: {len(table_data)} 行")
    print(f"[数据处理] 明细: {len(detail_data)} 行")

    return result


def save_json(data, output_path):
    """保存 JSON 数据到文件。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[数据处理] JSON 已保存到: {output_path}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from excel_parser import parse_excel

    config_path = Path(__file__).parent.parent / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    test_file = sys.argv[1] if len(sys.argv) > 1 else None
    if test_file:
        df = parse_excel(test_file, config)
        result = process_data(df, config)
        output = Path(__file__).parent.parent / "web" / "static" / "data" / "dashboard_data.json"
        save_json(result, output)
    else:
        print("用法: python data_processor.py <excel_file_path>")
