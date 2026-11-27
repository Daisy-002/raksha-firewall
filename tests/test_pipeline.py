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
                    "subject": {
                        "display": "Kamala Nishad",
                        "reference": "Patient/JJH-0077305",
                    },
                    "text": {
                        "status": "generated",
                        "div": (
                            '<div xmlns="http://www.w3.org/1999/xhtml">'
                            "Kamala Nishad, 27 yrs, female, JJH-0077305</div>"
                        ),
                    },
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
            self.assertIn('"reference": "PSN-', result)

    def test_fhir_address_components_are_sanitized_in_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()
            payload = {
                "resourceType": "Patient",
                "address": [{
                    "use": "home",
                    "line": ["22 Main Road"],
                    "city": "Hardoi",
                    "state": "Uttar Pradesh",
                    "postalCode": "225127",
                }],
                "observation": {"line": "left arm"},
            }
            (source / "patient.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            run_pipeline(source, output)

            result = (output / "sanitized" / "patient.json").read_text(
                encoding="utf-8"
            )
            for value in ("22 Main Road", "Hardoi", "Uttar Pradesh", "225127"):
                self.assertNotIn(value, result)
            self.assertIn('"use": "home"', result)
            self.assertIn('"line": "left arm"', result)

    def test_patient_names_in_csv_headers_are_renamed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()
            (source / "wide.csv").write_text(
                "time,Blood Pressure,JJH-0077112 Zainab Siddiqui,"
                "Jaspreet Singh\n"
                "14:00,120,128,110\n",
                encoding="utf-8",
            )

            run_pipeline(source, output)

            result = (output / "sanitized" / "wide.csv").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("JJH-0077112", result)
            self.assertNotIn("Zainab Siddiqui", result)
            self.assertNotIn("Jaspreet Singh", result)
            self.assertIn("time,Blood Pressure,column_3,column_4", result)
            self.assertIn("14:00,120,128,110", result)

    def test_native_hindi_fields_and_date_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()
            (source / "records.csv").write_text(
                "रोगी आईडी,नाम,जन्म तिथि,पता,बीमा संख्या\n"
                "JJH-0077305,कमला निषाद,15-01-1980,"
                "मकान 32 बाराबंकी,POLICY-784512\n",
                encoding="utf-8",
            )

            run_pipeline(source, output)

            result = (output / "sanitized" / "records.csv").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("JJH-0077305", result)
            self.assertNotIn("कमला निषाद", result)
            self.assertNotIn("15-01-1980", result)
            self.assertNotIn("मकान 32", result)
            self.assertNotIn("POLICY-784512", result)
            self.assertIn("PSN-", result)

    def test_person_name_filenames_are_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()
            (source / "Jane_Doe.txt").write_text(
                "Dengue treatment protocol", encoding="utf-8"
            )
            (source / "Dengue_Management_Protocol.txt").write_text(
                "Dengue treatment protocol", encoding="utf-8"
            )

            run_pipeline(source, output)

            output_files = {
                path.name for path in (output / "sanitized").iterdir()
            }
            self.assertIn("Dengue_Management_Protocol.txt", output_files)
            self.assertNotIn("Jane_Doe.txt", output_files)
            self.assertTrue(any(name.startswith("file_") for name in output_files))

    def test_contextual_filename_pii_is_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input"
            output = root / "output"
            source.mkdir()

            private_names = (
                "patient_ramesh_kumar.txt",
                "patient_name_raMeSh_KuMaR.txt",
                "mrn_84572319.csv",
                "landmark_bus_stand.txt",
                "locality_Amarganj.txt",
            )
            for name in private_names:
                (source / name).write_text(
                    "Routine clinical summary", encoding="utf-8"
                )
            (source / "patient_summary_report.txt").write_text(
                "Routine clinical summary with medication details",
                encoding="utf-8",
            )
            for name in (
                "patient_test_record.txt",
                "housekeeping_guide.txt",
                "house_keeping_guide.txt",
            ):
                (source / name).write_text(
                    "General reference material", encoding="utf-8"
                )

            run_pipeline(source, output)

            output_names = {
                path.name for path in (output / "sanitized").iterdir()
            }
            for name in private_names:
                with self.subTest(name=name):
                    self.assertNotIn(name, output_names)
            self.assertIn("patient_summary_report.txt", output_names)
            self.assertIn("patient_test_record.txt", output_names)
            self.assertIn("housekeeping_guide.txt", output_names)
            self.assertIn("house_keeping_guide.txt", output_names)


if __name__ == "__main__":
    unittest.main()