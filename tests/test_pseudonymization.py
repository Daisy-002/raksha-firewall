import os
import unittest

from rakshak.pseudonymization import pseudonym


class PseudonymTests(unittest.TestCase):
    def test_deterministic(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        first = pseudonym("patient_id:123")
        second = pseudonym("patient_id:123")
        self.assertEqual(first, second)

    def test_different_secret_changes_pseudonym(self):
        os.environ["RAKSHA_SECRET"] = "test-secret-one"
        first = pseudonym("patient_id:123")

        os.environ["RAKSHA_SECRET"] = "test-secret-two"
        second = pseudonym("patient_id:123")

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()