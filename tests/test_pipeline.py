import json
import os
import tempfile
import unittest
from pathlib import Path

from rakshak.engine import run_pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        os.environ["RAKSHA_SECRET"] = "pipeline-test-secret"

    def test_csv_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()

            csv_content = (
                "patient_id,name,phone,age,diagnosis\n"
                "HOSP-12345,Ramesh Kumar,9876543210,47,Diabetes\n"
            )
            (source / "patients.csv").write_text(
                csv_content,
                encoding="utf-8"
            )

            run_pipeline(source, output)

            sanitized = output / "sanitized" / "patients.csv"
            self.assertTrue(sanitized.exists())

            result = sanitized.read_text(encoding="utf-8")
            self.assertNotIn("HOSP-12345", result)
            self.assertNotIn("9876543210", result)
            self.assertIn("PSN-", result)

            report = json.loads(
                (output / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["counts"]["files_total"], 1)
            self.assertEqual(report["counts"]["files_sanitized"], 1)

            records = (output / "records.jsonl").read_text(encoding="utf-8")
            self.assertIn("PSN-", records)

    def test_unsupported_file_quarantined(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()

            (source / "scan.pdf").write_bytes(b"not a supported document")

            run_pipeline(source, output)

            report = json.loads(
                (output / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["counts"]["files_quarantined"], 1)


if __name__ == "__main__":
    unittest.main()