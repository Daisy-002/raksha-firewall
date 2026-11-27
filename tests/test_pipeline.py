import json
import os
import tempfile
import unittest
from pathlib import Path

from rakshak.engine import run_pipeline


class PipelineTests(unittest.TestCase):
    def test_end_to_end(self):
        os.environ["RAKSHA_SECRET"] = "pipeline-secret"
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary, "in"), Path(temporary, "out")
            source.mkdir()
            (source / "list.csv").write_text(
                "UHID,Patient Name,Mobile,Age,Diagnosis\n"
                "KGH/24/883421,Harpreet Gill,9812345670,67,Dengue fever\n", encoding="utf-8")
            (source / "note_KGH-24-883421.txt").write_text(
                "Patient: Harpreet Gill\nUHID: KGH/24/883421\nBP 120/80\n", encoding="utf-8")
            (source / "scan.pdf").write_bytes(b"%PDF Harpreet Gill")
            (source / "bad.json").write_text('{"name": "Harpreet', encoding="utf-8")
            run_pipeline(source, output)

            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["counts"]["files_total"], 4)
            self.assertEqual(report["counts"]["files_quarantined"], 2)
            released = [p for p in output.rglob("*") if p.is_file()]
            text = "".join(p.name + p.read_text(encoding="utf-8") for p in released)
            for secret in ("Harpreet", "9812345670", "883421", "pipeline-secret"):
                self.assertNotIn(secret, text)
            self.assertIn("Dengue fever", text)
            records = [json.loads(line) for line in
                       (output / "records.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len({r["patient"] for r in records}), 1)
            self.assertIsNotNone(records[0]["patient"])


if __name__ == "__main__":
    unittest.main()
