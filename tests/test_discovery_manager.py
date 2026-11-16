#!/usr/bin/env python3
"""Tests for src/discovery_manager.py — hybrid direct/discovery reconnection."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import CameraConfig
from src.discovery_manager import CameraIPState, DiscoveryManager


class ConnectError(Exception):
    pass


def failing_connect(camera_config):
    raise ConnectError("no route to host")


def make_camera(mac="F4:5C:89:A2:3B:1C"):
    return CameraConfig(
        id="cam-1",
        name="Imou Bullet 2e",
        host="192.168.1.100",
        mac_address=mac,
        username="admin",
        password="admin",
    )


class TestCameraIPState(unittest.TestCase):
    def test_defaults(self):
        state = CameraIPState()
        self.assertEqual(state.last_known_ip, "")
        self.assertIsNone(state.discovery_timestamp)
        self.assertTrue(state.ip_stable)
        self.assertEqual(state.retry_count, 0)


class TestDiscoveryManager(unittest.TestCase):
    def test_direct_connection_skips_discovery(self):
        scans = []

        def scanner(network_prefix):
            scans.append(network_prefix)
            return []

        manager = DiscoveryManager(scanner=scanner)
        camera = make_camera()
        client, discovered = manager.check_and_reconnect(camera, lambda cfg: "client-direct")
        self.assertEqual(client, "client-direct")
        self.assertFalse(discovered)
        self.assertEqual(scans, [])
        self.assertEqual(manager.state_for(camera.id).last_known_ip, "192.168.1.100")
        self.assertEqual(manager.state_for(camera.id).retry_count, 0)

    def test_discovery_matches_by_mac_and_updates_host(self):
        manager = DiscoveryManager(
            scanner=lambda prefix: [
                {"ip": "192.168.1.177", "mac": "aa:bb:cc:dd:ee:ff", "model": "Imou Camera"},
                {"ip": "192.168.1.140", "mac": "f4:5c:89:a2:3b:1c", "model": "Imou Cruise"},
            ]
        )
        camera = make_camera()
        client, discovered = manager.check_and_reconnect(
            camera, lambda cfg: "client-rediscovered" if cfg.host == "192.168.1.140" else failing_connect(cfg)
        )
        self.assertEqual(client, "client-rediscovered")
        self.assertTrue(discovered)
        self.assertEqual(camera.host, "192.168.1.140")
        self.assertTrue(camera.discovered)
        state = manager.state_for(camera.id)
        self.assertIsNotNone(state.discovery_timestamp)

    def test_never_steals_unrelated_discovered_camera(self):
        manager = DiscoveryManager(
            scanner=lambda prefix: [
                {"ip": "192.168.1.177", "mac": "aa:bb:cc:dd:ee:ff", "model": "Imou Camera"},
            ]
        )
        camera = make_camera()
        client, discovered = manager.check_and_reconnect(camera, failing_connect)
        self.assertIsNone(client)
        self.assertEqual(camera.host, "192.168.1.100")
        self.assertEqual(manager.state_for(camera.id).retry_count, 1)

    def test_camera_without_mac_is_not_matched(self):
        manager = DiscoveryManager(
            scanner=lambda prefix: [
                {"ip": "192.168.1.140", "mac": "f4:5c:89:a2:3b:1c", "model": "Imou Camera"},
            ]
        )
        camera = make_camera(mac=None)
        client, discovered = manager.check_and_reconnect(camera, failing_connect)
        self.assertIsNone(client)
        self.assertEqual(camera.host, "192.168.1.100")

    def test_discovered_host_that_still_fails_returns_none(self):
        manager = DiscoveryManager(
            scanner=lambda prefix: [
                {"ip": "192.168.1.140", "mac": "f4:5c:89:a2:3b:1c", "model": "Imou Camera"},
            ]
        )
        camera = make_camera()
        client, discovered = manager.check_and_reconnect(camera, failing_connect)
        self.assertIsNone(client)
        self.assertEqual(manager.state_for(camera.id).retry_count, 1)

    def test_scan_failure_is_contained(self):
        def broken_scanner(prefix):
            raise RuntimeError("network down")

        manager = DiscoveryManager(scanner=broken_scanner)
        camera = make_camera()
        client, discovered = manager.check_and_reconnect(camera, failing_connect)
        self.assertIsNone(client)
        self.assertEqual(camera.host, "192.168.1.100")


if __name__ == "__main__":
    unittest.main()
