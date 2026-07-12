import unittest

from lce_validation.harness.accept_c import make_accept_row
from lce_validation.harness.reducers import reduce_acceptance
from lce_validation.harness.verifier_rows import sufficiency_result, verifier_result


class AcceptCReducerTests(unittest.TestCase):
    def test_unknown_blocks_accept_verified(self):
        row = make_accept_row("RT-001", "CAND-C08", "FX-DATA-F-F-001", ["CLAIM"], ["M5"])
        reduced = reduce_acceptance(
            row,
            [verifier_result("V_resource", "RT-001", "unknown", "dry run")],
            [sufficiency_result("SUFF_TRACE_FAITHFUL", "RT-001", "unknown", "no replay proof")],
            [],
        )
        self.assertEqual(reduced["verdict"], "UNKNOWN_MODEL_GAP")
        self.assertTrue(reduced["blocking_reasons"])

    def test_replacement_wording_is_rejected(self):
        row = make_accept_row("RT-002", "CAND-C11", "FX-DATA-F-A-001", ["CLAIM"], ["P5/P6-VAL-011"])
        reduced = reduce_acceptance(row, [], [], [], attempted_claim_text="attention replaced")
        self.assertEqual(reduced["verdict"], "REJECT_UNSUPPORTED")
