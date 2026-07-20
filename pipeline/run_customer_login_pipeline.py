"""Run the customer-login email-to-dashboard pipeline."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from customer_login_email import fetch_latest_attachment
from customer_login_processor import build_dashboard_data, save_dashboard_data


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path else PROJECT_ROOT / "config" / "customer_login_settings.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def run_pipeline(
    excel_file: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    require_current_slot: bool = False,
    config: dict | None = None,
) -> Path:
    config = config or load_config()
    output = Path(
        output_path
        or os.environ.get(
            "CUSTOMER_LOGIN_OUTPUT",
            PROJECT_ROOT / "web" / "static" / "customer_login_data.json",
        )
    )

    if excel_file:
        data = build_dashboard_data(
            Path(excel_file),
            expected_sheet_name=config["excel"].get("sheet_name"),
        )
        saved = save_dashboard_data(data, output)
        print_summary(data, saved)
        return saved

    with tempfile.TemporaryDirectory(prefix="customer-login-") as temp_dir:
        metadata = fetch_latest_attachment(
            config,
            temp_dir,
            require_current_slot=require_current_slot,
        )
        data = build_dashboard_data(
            metadata["path"],
            subject=metadata["subject"],
            received_at=metadata["received_at"],
            report_datetime=metadata["report_datetime"],
            expected_sheet_name=config["excel"].get("sheet_name"),
        )
        saved = save_dashboard_data(data, output)
        print_summary(data, saved)
        return saved


def print_summary(data: dict, output_path: Path) -> None:
    summary = data["summary"]
    print(f"Customer-login dashboard data written to: {output_path}")
    print(f"Report time: {data['data_date']} {data['data_time']}")
    print(f"Rows: {data['source_rows']}; unique customers: {data['unique_customers']}")
    print(
        "Visit/cart/order: "
        f"{summary['visit_customers']}/{summary['cart_customers']}/{summary['order_customers']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("excel_file", nargs="?", help="Optional local workbook for testing")
    parser.add_argument("--output", help="Dashboard JSON output path")
    parser.add_argument(
        "--require-current-slot",
        action="store_true",
        help="Fail when the report expected for the current Beijing-time slot is missing",
    )
    args = parser.parse_args()
    run_pipeline(
        args.excel_file,
        output_path=args.output,
        require_current_slot=args.require_current_slot,
    )


if __name__ == "__main__":
    main()
