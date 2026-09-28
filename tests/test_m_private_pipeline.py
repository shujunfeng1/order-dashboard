import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from run_m_private_pipeline import transform

class MPrivateTests(unittest.TestCase):
    def result(self):
        base = {"大区": "测试大区", "省区": "测试省区", "团队": "测试团队",
                "花名": "测试", "岗位名称": "BDM", "在职状态": "在职",
                "oa_id": 1, "普药私海客户数": 0, "私海客户数": 999}
        return {"retrieved_at": "2026-09-28T15:00:00+08:00", "data": {"rows": [
            base, dict(base, oa_id=2, 在职状态="离职"),
            dict(base, oa_id=3, 岗位名称="BD"),
            dict(base, oa_id=4, 岗位名称="省区负责人", 普药私海客户数=12)]}}
    def convert(self, result):
        return transform(result, datetime(2026,9,28,8,tzinfo=timezone.utc))
    def test_scope_metric_and_privacy(self):
        data = self.convert(self.result())
        self.assertEqual(data["summary"], {"people":2,"customers":12,"zero_people":1})
        self.assertEqual(set(data["rows"][0]), {"region","province","team","name","role","customers"})
    def test_duplicate_and_invalid_counts(self):
        for value in [-1, None, 2.5, True]:
            r=self.result()
            r["data"]["rows"][0]["普药私海客户数"]=value
            with self.assertRaises(ValueError): self.convert(r)
        r=self.result()
        r["data"]["rows"][3]["oa_id"]=1
        with self.assertRaises(ValueError): self.convert(r)
    def test_stale_cache_rejected(self):
        r=self.result()
        r["retrieved_at"]="2026-09-25T15:00:00+08:00"
        with self.assertRaises(ValueError): self.convert(r)
