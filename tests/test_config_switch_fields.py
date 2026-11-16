#!/usr/bin/env python3
"""Tests for the switch fields in src/config.py AlertConfig."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import AlertConfig, CamAlertConfig

REPO_ROOT = Path(__file__).parent.parent


class TestAlertConfigSwitchFields(unittest.TestCase):
    def test_defaults(self):
        cfg = AlertConfig()
        self.assertFalse(cfg.enable_switch)
        self.assertEqual(cfg.switch_host, "")
        self.assertEqual(cfg.switch_token, "")
        self.assertEqual(cfg.switch_id, "1")
        self.assertEqual(cfg.switch_severity_threshold, "high")

    def test_roundtrip(self):
        original = AlertConfig(
            enable_switch=True,
            switch_host="192.168.1.200",
            switch_token="abc123def456",
            switch_id="2",
            switch_severity_threshold="medium",
        )
        restored = AlertConfig.from_dict(original.to_dict())
        self.assertTrue(restored.enable_switch)
        self.assertEqual(restored.switch_host, "192.168.1.200")
        self.assertEqual(restored.switch_token, "abc123def456")
        self.assertEqual(restored.switch_id, "2")
        self.assertEqual(restored.switch_severity_threshold, "medium")

    def test_config_json_has_switch_fields(self):
        with open(REPO_ROOT / "config" / "camalert.json", encoding="utf-8") as f:
            data = json.load(f)
        alerts = data["alerts"]
        for key in (
            "enable_switch",
            "switch_host",
            "switch_token",
            "switch_id",
            "switch_severity_threshold",
        ):
            self.assertIn(key, alerts)
        self.assertFalse(alerts["enable_switch"])

    def test_file_roundtrip_keeps_switch_fields(self):
        config = CamAlertConfig.load(REPO_ROOT / "config" / "camalert.json")
        data = config.to_dict()
        self.assertIn("switch_host", data["alerts"])


if __name__ == "__main__":
    unittest.main()
