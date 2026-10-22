import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "proba_codex"))
from aduna import aduna  # noqa: E402


class TestProbaCodex(unittest.TestCase):
    def test_aduna(self):
        self.assertEqual(aduna(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
