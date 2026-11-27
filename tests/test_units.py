import os
import re
import unittest

from rakshak.dates import find, render
from rakshak.detection import detect
from rakshak.fields import classify
from rakshak.pseudonymization import deterministic_offset, pseudonym
from rakshak.textutil import similar_word


def found(text):
    return {(text[s:e], k) for s, e, k in detect(text)}


class DetectionTests(unittest.TestCase):
    def test_identifiers(self):
        for text, kind in (("Call 098123-45670", "PHONE"), ("९८७६५ ४३२१०", "PHONE"),
                           ("4821 7736 1190", "AADHAAR"), ("XXXX XXXX 5866", "AADHAAR_MASKED"),
                           ("ABCDE1234F", "PAN"), ("KGH/24/883421", "MRN")):
            self.assertIn(kind, {k for _, k in found(text)}, text)

    def test_care_of_versus_complaint(self):
        self.assertIn(("Baldev", "RELATIVE_NAME"), found("C/O Baldev, House 4"))
        self.assertEqual(found("C/O fever for 3 days"), set())
        self.assertEqual(found("H/O TB 9 yrs back"), set())

    def test_medical_text_untouched(self):
        for text in ("Dr. Anil Gupta (MD Medicine)", "Tab Dolo 650 1-0-1 x 5 days",
                     "Platelet Count 150000 /uL", "H/O Parkinson's disease", "Referred by ASHA worker"):
            self.assertEqual(found(text), set(), text)


class SupportTests(unittest.TestCase):
    def setUp(self):
        os.environ["RAKSHA_SECRET"] = "test-secret"

    def test_cross_script_names(self):
        self.assertTrue(similar_word("मोहम्मद", "Mohd"))
        self.assertTrue(similar_word("Reena", "Rina"))
        self.assertFalse(similar_word("Ramesh", "Suresh"))

    def test_unseen_labels(self):
        for label, role in (("Contact#", "phone"), ("Next of Kin", "relative"),
                            ("W/O or S/O", "relative"), ("Gram/Mohalla", "village"),
                            ("Beneficiary Full Name", "name"), ("drug", "text")):
            self.assertEqual(classify(label), role, label)

    def test_shift_keeps_intervals_and_style(self):
        offset = deterministic_offset("patient")
        results = []
        for value in ("01-03-2025", "11-03-2025"):
            ((_, _, date, kind, match),) = find(value)
            shifted = render(value, date, offset, kind, match, "dmy")
            self.assertRegex(shifted, r"^\d{2}-\d{2}-\d{4}$")
            results.append(next(find(shifted))[2])
        self.assertEqual((results[1] - results[0]).days, 10)

    def test_pseudonym_is_keyed(self):
        first = pseudonym("x")
        self.assertRegex(first, r"^PSN-[0-9A-Z]{4}-[0-9A-Z]{4}$")
        os.environ["RAKSHA_SECRET"] = "another"
        self.assertNotEqual(first, pseudonym("x"))


if __name__ == "__main__":
    unittest.main()
