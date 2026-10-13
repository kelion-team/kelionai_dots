"""Regression tests for canonical issue URL validation (offline)."""
import unittest
from orchestration.bridge import prepare

class IssueUrlValidationTests(unittest.TestCase):
    def test_accepts_canonical_issue(self):
        result = prepare("task-1234", "chat", "agt_test", "agtch_test", "diagnostics", "https://github.com/kelion-team/kelionai_dots/issues/4")
        self.assertEqual(result["issue_url"], "https://github.com/kelion-team/kelionai_dots/issues/4")

    def test_rejects_untrusted_or_ambiguous_issue_links(self):
        invalid = [
            "https://github.com.evil.test/owner/repo/issues/4",
            "https://github.com@evil.test/owner/repo/issues/4",
            "https://github.com/owner/repo/issues/4?redirect=evil",
            "https://github.com/owner/repo/issues/4#fragment",
            "http://github.com/owner/repo/issues/4",
            "https://github.com/owner/repo/issues/0",
            "https://github.com/owner/repo/issues/4/extra",
            "https://github.com/owner/repo/pull/4",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare("task-1234", "chat", "agt_test", "agtch_test", "diagnostics", url)

if __name__ == "__main__":
    unittest.main()
