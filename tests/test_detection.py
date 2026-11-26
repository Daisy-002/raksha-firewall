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


if __name__ == "__main__":
    unittest.main()