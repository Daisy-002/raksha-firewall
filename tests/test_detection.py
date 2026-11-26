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