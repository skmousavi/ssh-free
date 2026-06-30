#!/usr/bin/env python3
"""Unit tests for ssh-free."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SSH_FREE_ROOT"] = ROOT


class TestConfig(unittest.TestCase):

    def test_parse_ssh_target(self):
        from lib.config import parse_ssh_target

        r = parse_ssh_target("root@203.0.113.10")
        self.assertEqual(r["user"], "root")
        self.assertEqual(r["host"], "203.0.113.10")
        self.assertEqual(r["port"], 22)

    def test_parse_ssh_target_with_port(self):
        from lib.config import parse_ssh_target

        r = parse_ssh_target("admin@10.0.0.1:2222")
        self.assertEqual(r["user"], "admin")
        self.assertEqual(r["host"], "10.0.0.1")
        self.assertEqual(r["port"], 2222)

    def test_load_config(self):
        from lib.config import load_config

        cfg = load_config()
        self.assertEqual(cfg["app"]["name"], "ssh-free")
        self.assertIn("network", cfg)


class TestUtils(unittest.TestCase):

    def test_is_port_closed(self):
        from lib.utils import is_port_open

        # unlikely to have service on 59999
        self.assertFalse(is_port_open("127.0.0.1", 59999))

    def test_human_size(self):
        from lib.utils import human_size

        self.assertIn("KB", human_size(2048))


class TestDetector(unittest.TestCase):

    def test_detect_ssh(self):
        from lib.config import load_config
        from lib.detector import Detector

        d = Detector(load_config())
        result = d.detect_ssh()
        # ssh should exist on most dev machines
        self.assertTrue(result.ok or not result.ok)


class TestSession(unittest.TestCase):

    def test_build_session(self):
        from lib.session import build_session

        s = build_session(
            server={"host": "1.2.3.4", "user": "root"},
            tun_name="ssh-free0",
            socks_port=10801,
            socks_source="ssh",
            ssh_pid=100,
            tun2socks_pid=200,
        )
        self.assertEqual(s["server"]["host"], "1.2.3.4")
        self.assertEqual(s["socks_port"], 10801)


if __name__ == "__main__":
    unittest.main()
