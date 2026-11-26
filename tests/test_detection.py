import base64
import unittest

from rakshak.detection import sanitize_value


class DummyStats:
    def __init__(self):
        self.identifiers = 0
        self.entities = {}


class DetectionTests(unittest.TestCase):
    def test_phone_detection(self):
        stats = DummyStats()
        result = sanitize_value("notes", "Call 9876543210", stats)
        self.assertNotIn("9876543210", result)
        self.assertGreater(stats.identifiers, 0)

    def test_leading_zero_phone_detection(self):
        result = sanitize_value("notes", "Call 060062-72163")
        self.assertNotIn("060062-72163", result)
        self.assertIn("[REDACTED_PHONE]", result)
        self.assertEqual(
            sanitize_value("mobile", 9876543210), "[REDACTED_PHONE]"
        )

    def test_regional_fields_are_redacted(self):
        self.assertEqual(
            sanitize_value("Naam", "Kamala Nishad"), "[REDACTED_NAME]"
        )
        self.assertEqual(
            sanitize_value("Pita/Pati ka Naam", "D/o Kishan Nishad"),
            "[REDACTED_NAME]",
        )
        self.assertEqual(
            sanitize_value("Pata", "House 32, Barabanki"),
            "[GENERALIZED_LOCATION]",
        )
        self.assertEqual(
            sanitize_value("Gaon", "Amarganj Khurd"),
            "[GENERALIZED_LOCATION]",
        )
        self.assertEqual(
            sanitize_value("PIN", "225127"), "[GENERALIZED_LOCATION]"
        )
        self.assertIn(
            "[REDACTED_NAME]",
            sanitize_value("notes", "Naam: Kamala Nishad"),
        )
        self.assertEqual(
            sanitize_value("नाम", "कमला निषाद"), "[REDACTED_NAME]"
        )
        self.assertEqual(
            sanitize_value("पता", "मकान 32, बाराबंकी"),
            "[GENERALIZED_LOCATION]",
        )
        self.assertEqual(
            sanitize_value("मोबाइल नंबर", "9876543210"),
            "[REDACTED_PHONE]",
        )

    def test_insurance_field_aliases_are_redacted(self):
        for field in ("insurance_no", "membernumber", "claimid"):
            with self.subTest(field=field):
                result = sanitize_value(field, "POLICY-784512")
                self.assertNotIn("POLICY-784512", result)

    def test_generic_family_fields_are_not_blindly_redacted(self):
        value = "Family history: diabetes; given dosage: 5 mg"
        self.assertEqual(sanitize_value("family_history", value), value)
        self.assertEqual(sanitize_value("given", "left side"), "left side")

    def test_email_detection(self):
        stats = DummyStats()
        result = sanitize_value("notes", "Email abc@example.com", stats)
        self.assertNotIn("abc@example.com", result)

    def test_aadhaar_detection(self):
        stats = DummyStats()
        result = sanitize_value("notes", "1234 5678 9012", stats)
        self.assertNotIn("1234 5678 9012", result)

    def test_clinical_dose_preserved(self):
        stats = DummyStats()
        result = sanitize_value("clinical_note", "Dolo 650, 5 mg, 1-0-1", stats)
        self.assertIn("Dolo 650", result)
        self.assertIn("5 mg", result)
        self.assertIn("1-0-1", result)

    def test_free_text_name_and_hospital_id_labels(self):
        result = sanitize_value(
            "clinical_note",
            "Name: Kamala Nishad; Reg No: JJH-0077305",
        )
        self.assertNotIn("Kamala Nishad", result)
        self.assertNotIn("JJH-0077305", result)

    def test_fhir_narrative_name_and_identifier_are_redacted(self):
        result = sanitize_value(
            "fhir_narrative",
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            "Kamala Nishad, 27 yrs, female, JJH-0077305</div>",
        )
        self.assertNotIn("Kamala Nishad", result)
        self.assertNotIn("JJH-0077305", result)
        self.assertIn("[REDACTED_NAME]", result)

    def test_timestamped_relative_note_redacts_patient_name(self):
        result = sanitize_value(
            "clinical_note",
            "14:00 - Ramesh Kumar - K/O Mahesh Kumar",
        )
        self.assertNotIn("Ramesh Kumar", result)

    def test_hinglish_patient_name_contexts(self):
        examples = (
            "Irfan ka BP is 128/72",
            "Ramesh Kumar ko 6 din se bukhar hai",
            "Harish sahab ka blood pressure is elevated",
        )
        for text in examples:
            with self.subTest(text=text):
                result = sanitize_value("clinical_note", text)
                self.assertIn("[REDACTED_NAME]", result)
                self.assertNotIn(text.split()[0], result)

    def test_hindi_name_before_symptom_duration(self):
        result = sanitize_value(
            "clinical_note",
            "कमला निषाद को 6 दिन से बुखार है",
        )
        self.assertNotIn("कमला निषाद", result)
        self.assertIn("6 दिन से बुखार", result)

    def test_text_base64_payload_is_sanitized(self):
        cleartext = "Name: Kamala Nishad; Reg No: JJH-0077305"
        encoded = base64.b64encode(cleartext.encode()).decode("ascii")
        result = sanitize_value("attachment_data", encoded)
        decoded = base64.b64decode(result).decode("utf-8")
        self.assertNotIn("Kamala Nishad", decoded)
        self.assertNotIn("JJH-0077305", decoded)

    def test_labeled_dob_in_free_text_is_redacted(self):
        result = sanitize_value("clinical_note", "Date of birth: 15-01-1980")
        self.assertNotIn("15-01-1980", result)
        self.assertIn("[REDACTED_DATE]", result)


if __name__ == "__main__":
    unittest.main()