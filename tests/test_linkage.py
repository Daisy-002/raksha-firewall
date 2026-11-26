import unittest

from rakshak.linkage import canonical_patient_key


class LinkageTests(unittest.TestCase):
    def test_same_strong_identifier(self):
        a = {"patient_id": "HOSP-12345", "name": "Person A"}
        b = {"patient_id": "HOSP-12345", "name": "Person B"}
        self.assertEqual(canonical_patient_key(a), canonical_patient_key(b))

    def test_name_only_does_not_link(self):
        a = {"name": "Ramesh Kumar"}
        self.assertIsNone(canonical_patient_key(a))

    def test_phone_only_does_not_link(self):
        a = {"phone": "9876543210"}
        self.assertIsNone(canonical_patient_key(a))

    def test_conflicting_strong_ids_abstain(self):
        a = {
            "patient_id": "HOSP-123",
            "uhid": "HOSP-999",
        }
        self.assertIsNone(canonical_patient_key(a))


if __name__ == "__main__":
    unittest.main()