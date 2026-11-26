import os
import unittest

from rakshak.dates import shift_date_string


class DateTests(unittest.TestCase):
    def test_same_secret_same_shift(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"

        first = shift_date_string("2024-01-15", "patient:1")
        second = shift_date_string("2024-01-15", "patient:1")

        self.assertEqual(first, second)
        self.assertNotEqual(first, "2024-01-15")

    def test_different_secret_changes_shift(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        first = shift_date_string("2024-01-15", "patient:1")

        os.environ["RAKSHA_SECRET"] = "test-secret-two"
        second = shift_date_string("2024-01-15", "patient:1")

        self.assertNotEqual(first, second)

    def test_invalid_date_preserved(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        self.assertEqual(
            shift_date_string("2024-99-99", "patient:1"),
            "2024-99-99"
        )

    def test_indian_date_formats_are_shifted_and_preserved(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        samples = (
            ("15-01-2024", r"\d{2}-\d{2}-\d{4}"),
            ("15/01/2024", r"\d{2}/\d{2}/\d{4}"),
            ("2024-01-15T10:30:00Z", r"\d{4}-\d{2}-\d{2}T10:30:00Z"),
        )
        for value, expected_format in samples:
            with self.subTest(value=value):
                shifted = shift_date_string(value, "patient:1")
                self.assertNotEqual(shifted, value)
                self.assertRegex(shifted, f"^{expected_format}$")

    def test_devanagari_date_digits_are_shifted(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        original = "१५-०१-२०२४"
        shifted = shift_date_string(original, "patient:1")
        self.assertNotEqual(shifted, original)
        self.assertRegex(shifted, r"^[०-९]{2}-[०-९]{2}-[०-९]{4}$")


if __name__ == "__main__":
    unittest.main()