#!/usr/bin/env python3
"""Routing detection tests."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SSH_FREE_ROOT"] = ROOT


class TestRoutingDetect(unittest.TestCase):

    def test_detect_backend(self):
        from lib.routing_detect import detect_routing_backend

        backend = detect_routing_backend()
        self.assertIn("backend", backend)
        self.assertIn("supports_full", backend)

    def test_full_mode_always_ok(self):
        from lib.routing_detect import detect_routing_backend, resolve_effective_mode

        backend = detect_routing_backend()
        mode = resolve_effective_mode("full", backend)
        self.assertEqual(mode, "full")

    def test_split_fallback_without_policy(self):
        from lib.routing_detect import resolve_effective_mode

        backend = {"supports_full": True, "supports_policy": False}
        self.assertEqual(resolve_effective_mode("split", backend), "full")
        self.assertEqual(resolve_effective_mode("rules", backend), "full")


if __name__ == "__main__":
    unittest.main()
