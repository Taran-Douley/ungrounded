import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ungrounded.stimuli import DEFAULT_TRIPLES  # noqa: E402

HARNESS = os.path.join(os.path.dirname(__file__), "..", "reference", "exp3_triples.txt")


class TestStimuliMatchPaper(unittest.TestCase):
    """The default set is only a replication if it is byte-identical to the paper."""

    def test_twelve_triples(self):
        self.assertEqual(len(DEFAULT_TRIPLES), 12)

    def test_all_three_conditions_present(self):
        for t in DEFAULT_TRIPLES:
            self.assertTrue(t.ungroundable)
            self.assertTrue(t.groundable_known)
            self.assertTrue(t.groundable_unknown,
                            f"{t.id} is missing the fictional-vendor condition")

    def test_fictional_vendors_are_distinct_from_real_ones(self):
        for t in DEFAULT_TRIPLES:
            self.assertNotEqual(t.groundable_known, t.groundable_unknown)

    @unittest.skipUnless(os.path.exists(HARNESS), "reference copy not vendored")
    def test_matches_harness_verbatim(self):
        raw = open(HARNESS, encoding="utf-8").read()
        got = "\n".join(f"{t.ungroundable}|{t.groundable_known}|{t.groundable_unknown}"
                         for t in DEFAULT_TRIPLES)
        self.assertEqual(got.strip(), raw.strip())


if __name__ == "__main__":
    unittest.main()
