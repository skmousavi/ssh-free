#!/usr/bin/env python3
"""V3 feature tests."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SSH_FREE_ROOT"] = ROOT


class TestRules(unittest.TestCase):

    def test_is_ip(self):
        from lib.rules import is_ip, is_cidr

        self.assertTrue(is_ip("1.2.3.4"))
        self.assertFalse(is_ip("not-an-ip"))
        self.assertTrue(is_cidr("10.0.0.0/8"))

    def test_expand_rule_ip(self):
        from lib.rules import expand_rule

        self.assertEqual(expand_rule("1.2.3.4"), ["1.2.3.4"])
        self.assertEqual(expand_rule("10.0.0.0/8"), ["10.0.0.0/8"])

    def test_expand_rules_dedup(self):
        from lib.rules import expand_rules

        targets, _ = expand_rules(["1.2.3.4", "1.2.3.4"])
        self.assertEqual(targets, ["1.2.3.4"])

    def test_load_rules_config(self):
        from lib.config import load_config
        from lib.rules import load_rules_config

        cfg = load_rules_config(load_config())
        self.assertIn("mode", cfg)
        self.assertIn("include", cfg)
        self.assertIn("exclude", cfg)


class TestProfiles(unittest.TestCase):

    def test_list_profiles_empty(self):
        from lib.config import load_config
        from lib.profiles import list_profiles

        profiles = list_profiles(load_config())
        self.assertIsInstance(profiles, list)

    def test_profile_target(self):
        from lib.profiles import profile_target

        t = profile_target({"user": "root", "host": "1.2.3.4", "port": 22})
        self.assertEqual(t, "root@1.2.3.4")

        t2 = profile_target({"user": "admin", "host": "1.2.3.4", "port": 2222})
        self.assertEqual(t2, "admin@1.2.3.4:2222")


class TestTraffic(unittest.TestCase):

    def test_snapshot(self):
        from lib.traffic import TrafficStats

        stats = TrafficStats(tun_name="lo")
        snap = stats.snapshot()
        self.assertIn("tun", snap)
        self.assertIn("rx_bytes", snap["tun"])


class TestRoutingConfig(unittest.TestCase):

    def test_rules_mode_in_config(self):
        from lib.config import load_config

        cfg = load_config()
        self.assertIn(cfg["routing"]["mode"], ("full", "split", "rules"))


if __name__ == "__main__":
    unittest.main()
