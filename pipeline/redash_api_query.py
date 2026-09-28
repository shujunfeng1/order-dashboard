#!/usr/bin/env python3
"""Execute saved Redash queries through the HTTP API and export results.

Designed for both query API keys and user API keys. Parameterized queries are
always submitted with POST /api/queries/<id>/results; never rely on the
latest-result GET endpoint for them.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


EXIT_INPUT = 2
EXIT_API = 3
EXIT_TIMEOUT = 4
EXIT_EXPORT = 5


class RedashError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute a saved Redash query and export its result safely."
    )
    parser.add_argument("--base-url", required=True, help="Redash base URL, e.g. https://redash.example.com")
    parser.add_argument("--query-id", required=True, type=int, help="Saved Redash query ID")
    parser.add_argument(
        "--api-key-env",
        default="REDASH_API_KEY",
        help="Environment variable containing the API key (default: REDASH_API_KEY)",
    )
    parser.add_argument(
        "--api-key",
        help="API key literal. Avoid this in shared terminals; prefer --api-key-env.",
    )
    parser.add_argument(
        "--auth-mode",
        choices=("query-param", "header"),
        default="query-param",
        help="Use ?api_key=... for query keys, or Authorization: Key ... for user keys.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Redash parameter. Repeat for multiple parameters.",
    )
    parser.add_argument(
        "--params-json",
        help="JSON object or @path/to/params.json. --param values override duplicate keys.",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=0,
        help="Maximum acceptable cached-result age in seconds. 0 forces a fresh run.",
    )
    parser.add_argument(
        "--retry-max-age",
        type=int,
        default=86400,
        help="Cache age used while checking an asynchronous job (default: 86400).",
    )
    parser.add_argument("--timeout", type=float, default=300, help="Overall timeout in seconds")
    parser.add_argument("--poll-interval", type=float, default=3, help="Seconds between checks")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "csv", "xlsx"),
        default="auto",
        help="Output format. auto uses the output file extension; otherwise json.",
    )
    parser.add_argument("--output", help="Output file. Omit to print only a machine-readable summary.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output file")
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=0,
        help="Include this many result rows in the stdout summary (default: 0).",
    )
    return parser.parse_args()


def load_parameters(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.params_json:
        raw = args.params_json
        if raw.startswith("@"):
            raw = Path(raw[1:]).read_text(encoding="utf-8")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("--params-json must decode to a JSON object")
        params.update(decoded)

    for item in args.param:
        if "=" not in item:
            raise ValueError(f"Invalid --param {item!r}; expected NAME=VALUE")
        name, value = item.split("=", 1)
        if not name:
            raise ValueError("Parameter name cannot be empty")
        params[name] = value
    return params


def get_api_key(args: argparse.Namespace) -> str:
    key = args.api_key or os.environ.get(args.api_key_env, "")
    if not key:
        raise ValueError(
            f"No API key found. Set {args.api_key_env} or pass --api-key (not recommended)."
        )
    return key


def safe_error_text(raw: str, api_key: str) -> str:
    return raw.replace(api_key, "***") if api_key else raw


def request_json(
    url: str,
    *,
    api_key: str,
    auth_mode: str,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 120,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if auth_mode == "query-param":
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urllib.parse.urlencode({'api_key': api_key})}"
    else:
        headers["Authorization"] = f"Key {api_key}"

    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(raw).get("message", raw)
        except json.JSONDecodeError:
            message = raw or str(exc)
        raise RedashError(safe_error_text(str(message), api_key), status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise RedashError(safe_error_text(str(exc.reason), api_key)) from exc


def parse_retrieved_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def result_is_fresh(query_result: dict[str, Any], submitted_at: datetime) -> bool:
    retrieved = parse_retrieved_at(query_result.get("retrieved_at"))
    if retrieved is None:
        return True
    return retrieved >= submitted_at - timedelta(seconds=10)


def execute_query(
    *,
    base_url: str,
    query_id: int,
    api_key: str,
    auth_mode: str,
    parameters: dict[str, Any],
    max_age: int,
    retry_max_age: int,
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/api/queries/{query_id}/results"
    started_monotonic = time.monotonic()
    submitted_at = datetime.now(timezone.utc)
    require_fresh = max_age == 0
    next_max_age = max_age

    while True:
        remaining = timeout - (time.monotonic() - started_monotonic)
        if remaining <= 0:
            raise TimeoutError(f"Redash query {query_id} did not finish within {timeout:g} seconds")

        response = request_json(
            endpoint,
            api_key=api_key,
            auth_mode=auth_mode,
            method="POST",
            payload={"parameters": parameters, "max_age": next_max_age},
            timeout=min(remaining, 120),
        )

        query_result = response.get("query_result")
        if isinstance(query_result, dict):
            if not require_fresh or result_is_fresh(query_result, submitted_at):
                return query_result
            # A previous cached result arrived while the fresh job is still running.
            next_max_age = 0
        else:
            job = response.get("job") or {}
            status = job.get("status")
            error = job.get("error")
            if error or status in (4, 5):
                raise RedashError(str(error or f"Redash job ended with status {status}"))
            # Query API keys cannot generally read /api/jobs/<id>. Re-posting this
            # query endpoint works with both query keys and user keys.
            next_max_age = retry_max_age

        sleep_for = min(poll_interval, max(0, timeout - (time.monotonic() - started_monotonic)))
        if sleep_for <= 0:
            raise TimeoutError(f"Redash query {query_id} did not finish within {timeout:g} seconds")
        time.sleep(sleep_for)


def ordered_columns(query_result: dict[str, Any]) -> list[str]:
    data = query_result.get("data") or {}
    columns = data.get("columns") or []
    names = [column.get("name") for column in columns if isinstance(column, dict) and column.get("name")]
    if names:
        return names
    rows = data.get("rows") or []
    return list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []


def cell_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def resolve_format(fmt: str, output: Optional[str]) -> str:
    if fmt != "auto":
        return fmt
    if output:
        suffix = Path(output).suffix.lower().lstrip(".")
        if suffix in {"json", "csv", "xlsx"}:
            return suffix
    return "json"


def prepare_output(path_text: str, overwrite: bool) -> Path:
    path = Path(path_text).expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {path}. Pass --overwrite to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def export_result(query_result: dict[str, Any], output: Path, fmt: str) -> None:
    data = query_result.get("data") or {}
    rows = data.get("rows") or []
    columns = ordered_columns(query_result)

    if fmt == "json":
        output.write_text(json.dumps({"query_result": query_result}, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    if fmt == "csv":
        with output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: cell_value(row.get(name)) for name in columns})
        return

    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font
        except ImportError as exc:
            raise RuntimeError("XLSX export requires openpyxl. Install it or use JSON/CSV.") from exc
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Redash"
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append([cell_value(row.get(name)) for name in columns])
        sheet.freeze_panes = "A2"
        if columns:
            sheet.auto_filter.ref = sheet.dimensions
        workbook.save(output)
        return

    raise ValueError(f"Unsupported format: {fmt}")


def main() -> int:
    args = parse_args()
    try:
        if args.query_id <= 0:
            raise ValueError("--query-id must be positive")
        if args.max_age < 0 or args.retry_max_age < 0:
            raise ValueError("--max-age and --retry-max-age cannot be negative")
        if args.timeout <= 0 or args.poll_interval <= 0:
            raise ValueError("--timeout and --poll-interval must be positive")
        if args.sample_rows < 0:
            raise ValueError("--sample-rows cannot be negative")

        parameters = load_parameters(args)
        api_key = get_api_key(args)
        fmt = resolve_format(args.format, args.output)
        output = prepare_output(args.output, args.overwrite) if args.output else None

        query_result = execute_query(
            base_url=args.base_url,
            query_id=args.query_id,
            api_key=api_key,
            auth_mode=args.auth_mode,
            parameters=parameters,
            max_age=args.max_age,
            retry_max_age=args.retry_max_age,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
        )

        if output:
            export_result(query_result, output, fmt)

        data = query_result.get("data") or {}
        rows = data.get("rows") or []
        columns = ordered_columns(query_result)
        summary: dict[str, Any] = {
            "success": True,
            "query_id": args.query_id,
            "row_count": len(rows),
            "column_count": len(columns),
            "retrieved_at": query_result.get("retrieved_at"),
            "output": str(output) if output else None,
            "format": fmt if output else None,
        }
        if args.sample_rows:
            summary["sample_rows"] = rows[: args.sample_rows]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": str(exc), "category": "input"}, ensure_ascii=False), file=sys.stderr)
        return EXIT_INPUT
    except TimeoutError as exc:
        print(json.dumps({"success": False, "error": str(exc), "category": "timeout"}, ensure_ascii=False), file=sys.stderr)
        return EXIT_TIMEOUT
    except RedashError as exc:
        print(
            json.dumps(
                {"success": False, "error": str(exc), "category": "api", "status": exc.status},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return EXIT_API
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc), "category": "export"}, ensure_ascii=False), file=sys.stderr)
        return EXIT_EXPORT


if __name__ == "__main__":
    raise SystemExit(main())
