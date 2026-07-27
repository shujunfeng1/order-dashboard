import sys
import unittest
from email.header import Header
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from customer_login_email import (
    FreshEmailNotFound,
    expected_report_datetime,
    find_latest_email,
    parse_report_datetime,
)
from customer_login_processor import process_dataframe


class FakeMailbox:
    def __init__(self, messages):
        self.messages = messages
        self.fetched = []

    def select(self, mailbox, readonly=False):
        return "OK", [str(max(self.messages, default=0)).encode("ascii")]

    def fetch(self, message_id, query):
        sequence_number = int(message_id)
        self.fetched.append(sequence_number)
        raw = self.messages[sequence_number]
        return "OK", [(b"header", raw)]

    def search(self, *args, **kwargs):
        raise AssertionError("server-side SEARCH must not be used")


def make_header_message(subject, sender="hm.lu@ybm100.com"):
    encoded_subject = Header(subject, "utf-8").encode()
    return (
        f"Subject: {encoded_subject}\n"
        f"From: Report Sender <{sender}>\n"
        "Date: Mon, 27 Jul 2026 16:41:36 +0800\n"
        "Message-ID: <test@example.com>\n\n"
    ).encode("utf-8")


class CustomerLoginPipelineTests(unittest.TestCase):
    def test_subject_timestamp(self):
        parsed = parse_report_datetime("【今日登录客户明细】2026-07-20-16-40")
        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M"), "2026-07-20 16:40")

    def test_expected_slot(self):
        now = datetime(2026, 7, 20, 13, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
        expected = expected_report_datetime(now, ["10:45", "13:15", "16:40"])
        self.assertEqual(expected.strftime("%H:%M"), "13:15")

    def test_deduplication_and_public_pool(self):
        frame = pd.DataFrame([
            {"大区": None, "省份": "湖北", "客户ID": "C1", "客户类型": "单体", "登录日期": "2026-07-20", "是否加购": "否", "是否下单": "是", "是否拜访": "否", "是否上门拜访": "否", "是否电话拜访": "否"},
            {"大区": None, "省份": "湖北", "客户ID": "C1", "客户类型": "单体", "登录日期": "2026-07-20", "是否加购": "是", "是否下单": "否", "是否拜访": "是", "是否上门拜访": "否", "是否电话拜访": "是"},
        ])
        rows, summary = process_dataframe(frame)
        self.assertEqual(summary["source_rows"], 2)
        self.assertEqual(summary["unique_customers"], 1)
        self.assertEqual(rows[0]["region"], "公海")
        self.assertEqual(rows[0]["industry"], "单体")
        self.assertEqual(rows[0]["visit"], 1)
        self.assertEqual(rows[0]["cart"], 1)
        self.assertEqual(rows[0]["order"], 1)

    def test_recent_header_scan_avoids_slow_server_search(self):
        mailbox = FakeMailbox({
            1: make_header_message("【今日登录客户明细】2026-07-27-13-15"),
            2: make_header_message("【今日登录客户明细】2026-07-27-16-40"),
            3: make_header_message("Unrelated notification", "other@example.com"),
        })
        config = {
            "email": {
                "sender_filter": "hm.lu@ybm100.com",
                "subject_prefix": "【今日登录客户明细】",
                "lookback_days": 2,
                "report_slots": ["10:45", "13:15", "16:40"],
                "scan_recent_messages": 10,
            }
        }
        now = datetime(2026, 7, 27, 17, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        candidate = find_latest_email(
            mailbox, config, now=now, require_current_slot=True
        )
        self.assertEqual(candidate.report_datetime.strftime("%H:%M"), "16:40")
        self.assertEqual(mailbox.fetched, [3, 2])

    def test_recent_header_scan_rejects_stale_slot(self):
        mailbox = FakeMailbox({
            1: make_header_message("【今日登录客户明细】2026-07-27-10-45"),
            2: make_header_message("【今日登录客户明细】2026-07-27-13-15"),
        })
        config = {
            "email": {
                "sender_filter": "hm.lu@ybm100.com",
                "subject_prefix": "【今日登录客户明细】",
                "lookback_days": 2,
                "report_slots": ["10:45", "13:15", "16:40"],
                "scan_recent_messages": 10,
            }
        }
        now = datetime(2026, 7, 27, 17, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with self.assertRaises(FreshEmailNotFound):
            find_latest_email(mailbox, config, now=now, require_current_slot=True)


if __name__ == "__main__":
    unittest.main()
