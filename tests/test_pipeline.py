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

    def test_regional_tsv_fields_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()

            (source / "patients.tsv").write_text(
                "Reg No\tNaam\tPita/Pati ka Naam\tPata\tGaon\tMobile No\n"
                "JJH-0077305\tKamala Nishad\tD/o Kishan Nishad\t"
                "House 32, Barabanki\tAmarganj Khurd\t060062-72163\n",
                encoding="utf-8",
            )

            run_pipeline(source, output)

            result = (output / "sanitized" / "patients.tsv").read_text(
                encoding="utf-8"
            )
            for value in (
                "JJH-0077305", "Kamala Nishad", "Kishan Nishad",
                "House 32", "Amarganj Khurd", "060062-72163",
            ):
                self.assertNotIn(value, result)
            self.assertIn("PSN-", result)

    def test_json_metadata_and_patient_reference_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()
            payload = {
                "_export_meta": {
                    "source_path": "D:/HIS/Jane_Doe_0077305/visits.json",
                },
                "patient_index": {
                    "by_name": {"Jane Doe": "JJH-0077305"},
                    "by_uhid": {"JJH-0077305": {"visits": 1}},
                },
                "visits": [{
                    "patient_ref": "JJH-0077305",
                    "visit_id": "OPD/26/05/00112",
                    "patient": {
                        "name": [{
                            "use": "official",
                            "family": "Nishad",
                            "given": ["Kamala"],
                            "text": "Kamala Nishad",
                        }],
                    },
                }],
            }
            (source / "visits.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            run_pipeline(source, output)

            result = (output / "sanitized" / "visits.json").read_text(
                encoding="utf-8"
            )
            for value in (
                "Jane Doe", "JJH-0077305", "D:/HIS/",
                "Kamala Nishad", "Nishad", "Kamala",
                "OPD/26/05/00112",
            ):
                self.assertNotIn(value, result)
            self.assertIn("[REDACTED_METADATA]", result)
            self.assertNotIn("by_name", result)


if __name__ == "__main__":
    unittest.main()