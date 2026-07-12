import unittest

from lce_validation.systems.lane_records import lane_row
from lce_validation.systems.pi_service_probe import dry_run_pi_service_probe
from lce_validation.systems.process_identity import current_process_identity
from lce_validation.systems.resource_sampler import sample_resource


class ResourceRowDryRunTests(unittest.TestCase):
    def test_resource_lane_and_pi_probe_are_dry_run(self):
        proc = current_process_identity()
        res = sample_resource("run01")
        lane = lane_row("run01", proc["process_identity_ref"], res["resource_snapshot_ref"])
        pi = dry_run_pi_service_probe()
        self.assertEqual(lane["lane_label"], "WIN_CPU_FIRST")
        self.assertFalse(lane["gpu_assist"])
        self.assertEqual(pi["impact_status"], "dry_run_no_network_or_service_impact")
        self.assertIn(8790, pi["service_ports_checked"])
        self.assertIn(8788, pi["service_ports_checked"])
