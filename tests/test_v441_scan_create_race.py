#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v441_scan_create_race.py
# Description: A Scan must not create a second device for a Shelly that
#              Create Indigo Devices made while the scan was running.
# Author:      CliveS & Claude Sonnet 5.5
# Date:        06-11-2026
# Version:     1.0

from __future__ import annotations

import threading

from test_v440_discovered_devices import FakeDev, _Logger, fake_rget, world  # noqa: F401


def test_scan_does_not_duplicate_a_device_made_during_the_scan(world):  # noqa: F811
    p, devices, created, _ = world
    p._remember_shelly = lambda *a, **k: None
    # The scan's start-of-run snapshots are empty. Meanwhile "Create Indigo
    # Devices" makes the Plug UK at .40, as it did live at 12:22:21.
    p._existing_device_ips = lambda: {d.pluginProps["ip_address"] for d in devices}
    p._existing_device_macs = lambda: {d.pluginProps["mac_address"].upper(): d
                                       for d in devices if d.pluginProps.get("mac_address")}
    orig_probe = p._classify_shelly
    state = {"made": False}

    def classify(ip, data, say=None):
        if ip == "192.168.1.40" and not state["made"]:
            state["made"] = True
            devices.append(FakeDev(900, "Kettle", mac="AABBCC000040", ip=ip))
        return orig_probe(ip, data, say)

    # Make the snapshot stale: the first call (scan start) sees nothing.
    calls = {"n": 0}
    real_ips, real_macs = p._existing_device_ips, p._existing_device_macs

    def stale_ips():
        calls["n"] += 1
        return set() if calls["n"] == 1 else real_ips()

    def stale_macs():
        return {} if calls["n"] <= 1 else real_macs()

    p._existing_device_ips = stale_ips
    p._existing_device_macs = stale_macs
    p._classify_shelly = classify
    p._discover_thread("192.168.1")
    assert not any(c["ip"] == "192.168.1.40" for c in created), created


def test_scan_releases_the_create_lock(world):  # noqa: F811
    p, devices, created, _ = world
    p._remember_shelly = lambda *a, **k: None
    p._existing_device_ips = lambda: set()
    p._existing_device_macs = lambda: {}
    p._discover_thread("192.168.1")
    assert not p._create_lock.locked()
