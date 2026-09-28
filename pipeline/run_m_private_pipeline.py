"""Publish only approved M-level personnel aggregates from fresh Redash query results."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import argparse

ROLES = ["电销部负责人", "BDM", "战区负责人", "省区负责人"]
FIELDS = ["大区", "省区", "团队", "花名", "岗位名称", "在职状态", "oa_id", "普药私海客户数"]

def transform(result, now=None):
    now = now or datetime.now(timezone.utc)
    stamp = datetime.fromisoformat(result["retrieved_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Cache timestamp must include timezone")
    age = (now - stamp).total_seconds()
    if age > 48 * 3600 or age < -300:
        raise ValueError("Cache timestamp outside allowed freshness window")
    source = result["data"]["rows"]
    if not source:
        raise ValueError("Empty query result")
    rows, seen = [], set()
    for item in source:
        if any(k not in item for k in FIELDS):
            raise ValueError("Required query columns missing")
        if item["在职状态"] != "在职" or item["岗位名称"] not in ROLES:
            continue
        uid = item["oa_id"]
        if uid is None or uid in seen:
            raise ValueError("Missing or duplicate personnel identity")
        seen.add(uid)
        count = item["普药私海客户数"]
        if isinstance(count, bool) or not isinstance(count, (int, float)) or count < 0 or int(count) != count:
            raise ValueError("Invalid customer count")
        row = {out: str(item[key] or "").strip() or fallback for out, key, fallback in [
            ("region", "大区", "未分配"), ("province", "省区", "未分配"),
            ("team", "团队", "未分配"), ("name", "花名", "未填写"),
            ("role", "岗位名称", "未填写")]}
        row["customers"] = int(count)
        rows.append(row)
    if not rows:
        raise ValueError("No active target-role personnel")
    rows.sort(key=lambda r: (ROLES.index(r["role"]), r["region"], r["province"], r["team"], r["name"]))
    return {"schema_version": 1, "data_time": stamp.isoformat(), "roles": ROLES,
            "summary": {"people": len(rows), "customers": sum(r["customers"] for r in rows),
                        "zero_people": sum(r["customers"] == 0 for r in rows)},
            "rows": rows}

def fetch_fresh():
    from redash_api_query import execute_query
    key = os.environ.get("REDASH_API_KEY")
    if not key:
        raise ValueError("REDASH_API_KEY required")
    started = datetime.now(timezone.utc)
    result = execute_query(base_url="https://redash.ybm100.com", query_id=12127,
        api_key=key, auth_mode="header", parameters={}, max_age=0,
        retry_max_age=300, timeout=300, poll_interval=5)
    stamp = datetime.fromisoformat(result["retrieved_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None or (stamp - started).total_seconds() < -10:
        raise ValueError("Fresh query returned stale or invalid timestamp")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/m_private_data.json")
    args = parser.parse_args()
    payload = transform(fetch_fresh())
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    print(json.dumps({"data_time": payload["data_time"], **payload["summary"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
