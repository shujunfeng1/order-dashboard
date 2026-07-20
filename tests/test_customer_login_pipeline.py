import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from customer_login_email import expected_report_datetime, parse_report_datetime
from customer_login_processor import process_dataframe


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


if __name__ == "__main__":
    unittest.main()
