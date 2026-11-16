#!/usr/bin/env python3
"""Tests for src/switch_controller.py — SmartSwitch HTTP commands and SwitchController logic."""

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.switch_controller import (
    SmartSwitch,
    SwitchController,
    SwitchError,
    SEVERITY_ORDER,
)


class FakeTransport:
    """Transport that records requests and returns scripted responses."""

    def __init__(self, responses=None, error=None):
        self.requests = []
        self.responses = responses or []
        self.error = error

    def request(self, method, url, body=None, headers=None, timeout=5.0):
        self.requests.append({
            "method": method,
            "url": url,
            "body": body,
            "headers": headers or {},
            "timeout": timeout,
        })
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return 200, ""


class FakeSwitch:
    def __init__(self):
        self.on_calls = 0
        self.off_calls = 0

    def turn_on(self):
        self.on_calls += 1
        return True

    def turn_off(self):
        self.off_calls += 1
        return True


class TestSmartSwitch(unittest.TestCase):
    def make_switch(self, **kwargs):
        transport = kwargs.pop("transport", None) or FakeTransport()
        return SmartSwitch(
            host="192.168.1.200",
            token="tok123",
            switch_id="1",
            retry_delay=0,
            transport=transport,
            **kwargs,
        ), transport

    def test_turn_on_posts_control_action(self):
        switch, transport = self.make_switch()
        self.assertTrue(switch.turn_on())
        self.assertEqual(len(transport.requests), 1)
        req = transport.requests[0]
        self.assertEqual(req["method"], "POST")
        self.assertTrue(req["url"].endswith("/control"))
        self.assertEqual(req["body"], {"action": "on", "switch": "1"})
        self.assertEqual(req["headers"].get("Authorization"), "Bearer tok123")

    def test_turn_off_posts_control_action(self):
        switch, transport = self.make_switch()
        self.assertTrue(switch.turn_off())
        self.assertEqual(transport.requests[0]["body"], {"action": "off", "switch": "1"})

    def test_retries_then_returns_false(self):
        transport = FakeTransport(error=OSError("connection refused"))
        switch, _ = self.make_switch(transport=transport, retries=2)
        self.assertFalse(switch.turn_on())
        self.assertEqual(len(transport.requests), 3)

    def test_non_200_returns_false(self):
        transport = FakeTransport(responses=[(500, "boom")])
        switch, _ = self.make_switch(transport=transport, retries=0)
        self.assertFalse(switch.turn_on())

    def test_get_status_parses_json(self):
        transport = FakeTransport(responses=[(200, '{"switch": "1", "state": "on"}')])
        switch, _ = self.make_switch(transport=transport)
        self.assertEqual(switch.get_status(), {"switch": "1", "state": "on"})
        self.assertTrue(transport.requests[0]["url"].endswith("/status"))
        self.assertEqual(transport.requests[0]["method"], "GET")

    def test_get_status_raises_after_retries(self):
        transport = FakeTransport(error=OSError("down"))
        switch, _ = self.make_switch(transport=transport, retries=1)
        with self.assertRaises(SwitchError):
            switch.get_status()
        self.assertEqual(len(transport.requests), 2)

    def test_set_switch_id_changes_payload(self):
        switch, transport = self.make_switch()
        switch.set_switch_id("3")
        switch.turn_on()
        self.assertEqual(transport.requests[0]["body"]["switch"], "3")


class TestSwitchController(unittest.TestCase):
    def test_severity_order(self):
        self.assertEqual(SEVERITY_ORDER, ("low", "medium", "high", "critical"))

    def test_should_activate_uses_ordinal_severity(self):
        controller = SwitchController(FakeSwitch(), threshold="high")
        self.assertFalse(controller.should_activate("medium"))
        self.assertTrue(controller.should_activate("high"))
        self.assertTrue(controller.should_activate("critical"))

    def test_low_threshold_activates_medium(self):
        controller = SwitchController(FakeSwitch(), threshold="low")
        self.assertTrue(controller.should_activate("medium"))

    def test_trigger_below_threshold_does_nothing(self):
        fake = FakeSwitch()
        controller = SwitchController(fake, threshold="high")

        async def run():
            return await controller.trigger("medium")

        self.assertFalse(asyncio.run(run()))
        self.assertEqual(fake.on_calls, 0)

    def test_trigger_activates_and_auto_deactivates(self):
        fake = FakeSwitch()
        controller = SwitchController(fake, threshold="medium", min_interval_seconds=0.01)

        async def run():
            activated = await controller.trigger("high")
            await asyncio.sleep(0.1)
            return activated

        self.assertTrue(asyncio.run(run()))
        self.assertEqual(fake.on_calls, 1)
        self.assertEqual(fake.off_calls, 1)

    def test_shutdown_cancels_pending_auto_off(self):
        fake = FakeSwitch()
        controller = SwitchController(fake, threshold="low", min_interval_seconds=5)

        async def run():
            await controller.trigger("high")
            await controller.shutdown()
            await asyncio.sleep(0.05)

        asyncio.run(run())
        self.assertEqual(fake.on_calls, 1)
        self.assertEqual(fake.off_calls, 0)


if __name__ == "__main__":
    unittest.main()
