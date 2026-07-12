import unittest

from lce_validation.audit.redline_scan import scan_text


class RedlineContextTests(unittest.TestCase):
    def test_guarded_redline_phrase_is_not_violation(self):
        text = "Forbidden final claims without evidence: attention is replaced."
        self.assertEqual(scan_text(text), [])

    def test_quoted_redline_list_item_is_not_violation(self):
        text = '- "benchmark improvement is demonstrated"'
        self.assertEqual(scan_text(text), [])

    def test_unguarded_redline_phrase_is_violation(self):
        text = "The result shows attention is replaced."
        rows = scan_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prohibited_phrase"], "attention is replaced")
