#!/usr/bin/env python3
"""Tests for the switch channel and severity filtering in src/alerts.py."""

import asyncio
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.alerts import Alert, AlertConfig, AlertManager, AlertSeverity, AlertResult
from src.events import BaseEvent, EventType


class StubSwitchController:
    def __init__(self, result=True):
        self.result = result
        self.triggered = []

    def should_activate(self, severity):
        return True

    async def trigger(self, severity):
        self.triggered.append(severity)
        return self.result

    async def shutdown(self):
        return None


def make_alert(severity=AlertSeverity.MEDIUM, alert_id="alert-1"):
    event = BaseEvent(
        event_type=EventType.MOTION,
        camera_id="cam-1",
        camera_name="Cam 1",
        timestamp=datetime.now(),
        confidence=0.9,
    )
    return Alert(
        id=alert_id,
        event=event,
        severity=severity,
        title="Motion detected",
        message="Movement on camera Cam 1",
    )


def make_config(**overrides):
    base = dict(
        enable_console=True,
        enable_email=False,
        enable_telegram=False,
        enable_webhook=False,
        min_interval_seconds=0,
        severity_threshold=AlertSeverity.LOW,
    )
    base.update(overrides)
    return AlertConfig(**base)


class TestSeverityFiltering(unittest.TestCase):
    def test_critical_alert_passes_high_threshold(self):
        manager = AlertManager(make_config(severity_threshold="high"))
        result = asyncio.run(manager.send(make_alert(AlertSeverity.CRITICAL)))
        self.assertTrue(result.success)
        self.assertNotEqual(result.channel, "skipped")

    def test_low_alert_below_medium_threshold_is_skipped(self):
        manager = AlertManager(make_config(severity_threshold="medium"))
        result = asyncio.run(manager.send(make_alert(AlertSeverity.LOW)))
        self.assertFalse(result.success)
        self.assertEqual(result.channel, "skipped")

    def test_failed_channel_reports_error_without_crashing(self):
        manager = AlertManager(
            make_config(enable_console=False, enable_email=True)
        )
        result = asyncio.run(manager.send(make_alert(AlertSeverity.HIGH)))
        self.assertFalse(result.success)
        self.assertIn("email", result.channel)


class TestSwitchChannel(unittest.TestCase):
    def test_high_alert_triggers_switch(self):
        stub = StubSwitchController()
        manager = AlertManager(
            make_config(enable_switch=True, switch_severity_threshold="high", switch_host="192.168.1.200"),
            switch_controller=stub,
        )
        result = asyncio.run(manager.send(make_alert(AlertSeverity.HIGH)))
        self.assertTrue(result.success)
        self.assertEqual(stub.triggered, [AlertSeverity.HIGH])
        self.assertIn("switch", result.channel)

    def test_medium_alert_does_not_trigger_high_threshold_switch(self):
        stub = StubSwitchController()
        manager = AlertManager(
            make_config(enable_switch=True, switch_severity_threshold="high", switch_host="192.168.1.200"),
            switch_controller=stub,
        )
        asyncio.run(manager.send(make_alert(AlertSeverity.MEDIUM)))
        self.assertEqual(stub.triggered, [])

    def test_switch_failure_does_not_fail_alert(self):
        stub = StubSwitchController(result=False)
        manager = AlertManager(
            make_config(enable_switch=True, switch_severity_threshold="low", switch_host="192.168.1.200"),
            switch_controller=stub,
        )
        result = asyncio.run(manager.send(make_alert(AlertSeverity.HIGH)))
        self.assertTrue(result.success)
        self.assertIn("switch", result.channel)

    def test_switch_disabled_never_triggers(self):
        stub = StubSwitchController()
        manager = AlertManager(
            make_config(enable_switch=False, switch_host="192.168.1.200"),
            switch_controller=stub,
        )
        asyncio.run(manager.send(make_alert(AlertSeverity.CRITICAL)))
        self.assertEqual(stub.triggered, [])

    def test_alert_result_has_error_field(self):
        self.assertIsNone(AlertResult(alert_id="a", success=True, channel="console").error)


if __name__ == "__main__":
    unittest.main()
