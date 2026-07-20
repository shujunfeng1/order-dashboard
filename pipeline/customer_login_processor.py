"""Transform the customer-login workbook into privacy-safe dashboard data."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REQUIRED_COLUMNS = [
    "大区", "省份", "客户ID", "客户类型", "登录日期", "是否加购", "是否下单",
    "是否拜访", "是否上门拜访", "是否电话拜访",
]
FILENAME_TIME_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d{2})-(\d{2})")


def clean_text(value, fallback: str = "") -> str:
    """Normalize spreadsheet text and replace blank-like values."""
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return fallback
    return text


def parse_file_datetime(path: str | Path) -> datetime:
    """Read a report timestamp from the standard attachment filename."""
    match = FILENAME_TIME_PATTERN.search(Path(path).stem)
    if not match:
        raise ValueError(f"Unable to parse report time from {Path(path).name}")
    date_part, hour, minute = match.groups()
    parsed = datetime.strptime(f"{date_part} {hour}:{minute}", "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=BEIJING_TZ)


def _as_yes(series: pd.Series) -> pd.Series:
    return series.map(lambda value: clean_text(value) == "是")


def process_dataframe(df: pd.DataFrame) -> tuple[list[dict], dict]:
    """Deduplicate customers, calculate flags, and aggregate safe dimensions."""
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    source_rows = len(df)
    normalized = pd.DataFrame(index=df.index)
    normalized["customer_id"] = df["客户ID"].map(clean_text)
    blank_ids = normalized["customer_id"].eq("")
    normalized.loc[blank_ids, "customer_id"] = [
        f"__row_{index}" for index in normalized.index[blank_ids]
    ]
    normalized["region"] = df["大区"].map(lambda value: clean_text(value, "公海"))
    normalized["province"] = df["省份"].map(lambda value: clean_text(value, "公海"))
    normalized["industry"] = df["客户类型"].map(
        lambda value: "连锁" if clean_text(value) in {"连锁", "批发"} else "单体"
    )
    normalized["cart"] = _as_yes(df["是否加购"])
    normalized["order"] = _as_yes(df["是否下单"])
    normalized["visit"] = (
        _as_yes(df["是否拜访"])
        | _as_yes(df["是否上门拜访"])
        | _as_yes(df["是否电话拜访"])
    )

    customers = normalized.groupby("customer_id", sort=False, as_index=False).agg(
        region=("region", "last"),
        province=("province", "last"),
        industry=("industry", "last"),
        cart=("cart", "max"),
        order=("order", "max"),
        visit=("visit", "max"),
    )
    customers["visit_order"] = customers["visit"] & customers["order"]
    customers["nonvisit_order"] = ~customers["visit"] & customers["order"]
    customers["nonvisit_base"] = ~customers["visit"]

    grouped = customers.groupby(
        ["region", "province", "industry"], sort=True, as_index=False
    ).agg(
        login=("customer_id", "size"),
        visit=("visit", "sum"),
        cart=("cart", "sum"),
        order=("order", "sum"),
        visit_order=("visit_order", "sum"),
        nonvisit_order=("nonvisit_order", "sum"),
        nonvisit_base=("nonvisit_base", "sum"),
    )
    metric_columns = [
        "login", "visit", "cart", "order", "visit_order", "nonvisit_order", "nonvisit_base"
    ]
    grouped[metric_columns] = grouped[metric_columns].astype(int)

    rows = grouped.to_dict(orient="records")
    summary = {
        "source_rows": int(source_rows),
        "unique_customers": int(len(customers)),
        "duplicate_rows": int(source_rows - len(customers)),
        "login_customers": int(len(customers)),
        "visit_customers": int(customers["visit"].sum()),
        "cart_customers": int(customers["cart"].sum()),
        "order_customers": int(customers["order"].sum()),
        "order_without_cart_customers": int((customers["order"] & ~customers["cart"]).sum()),
    }
    return rows, summary


def build_dashboard_data(
    excel_path: str | Path,
    *,
    subject: str | None = None,
    received_at: str | None = None,
    report_datetime: str | None = None,
    expected_sheet_name: str | None = None,
) -> dict:
    """Load a workbook and build the JSON structure consumed by the page."""
    excel_path = Path(excel_path)
    with pd.ExcelFile(excel_path, engine="openpyxl") as workbook:
        if len(workbook.sheet_names) != 1:
            raise ValueError(f"Expected one worksheet, found {len(workbook.sheet_names)}")
        sheet_name = workbook.sheet_names[0]
        if expected_sheet_name and sheet_name != expected_sheet_name:
            raise ValueError(f"Unexpected worksheet: {sheet_name}")
        df = pd.read_excel(workbook, sheet_name=sheet_name)
    df.columns = [clean_text(column) for column in df.columns]
    rows, summary = process_dataframe(df)
    report_dt = (
        datetime.fromisoformat(report_datetime).astimezone(BEIJING_TZ)
        if report_datetime
        else parse_file_datetime(excel_path)
    )
    stable_received_at = received_at or report_dt.isoformat()
    return {
        "source_file": excel_path.name,
        "email_subject": subject or "",
        "data_date": report_dt.strftime("%Y-%m-%d"),
        "data_time": report_dt.strftime("%H:%M"),
        "received_at": stable_received_at,
        "updated_at": stable_received_at,
        "source_rows": summary["source_rows"],
        "unique_customers": summary["unique_customers"],
        "duplicate_rows": summary["duplicate_rows"],
        "visit_field_definition": "door_or_phone",
        "order_without_cart_rows": summary["order_without_cart_customers"],
        "summary": summary,
        "rows": rows,
    }


def save_dashboard_data(data: dict, output_path: str | Path) -> Path:
    """Write dashboard JSON atomically."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(output_path)
    return output_path
