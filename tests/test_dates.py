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


if __name__ == "__main__":
    unittest.main()