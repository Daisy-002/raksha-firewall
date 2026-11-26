import unittest

from rakshak.validation import find_residual_identifiers


class PrivacyTests(unittest.TestCase):
    def test_phone_is_detected(self):
        self.assertTrue(find_residual_identifiers("9876543210"))

    def test_email_is_detected(self):
        self.assertTrue(find_residual_identifiers("person@example.com"))

    def test_pan_is_detected(self):
        self.assertTrue(find_residual_identifiers("ABCDE1234F"))

    def test_clean_text_passes(self):
        self.assertEqual(find_residual_identifiers("Patient received treatment."), [])


if __name__ == "__main__":
    unittest.main()