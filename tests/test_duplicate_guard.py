#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_duplicate_guard.py
# Description: Contract tests for the v3.11 webhook-churn fix — the duplicate
#              device-record detector that stops two Indigo records bound to one
#              physical Shelly from ping-ponging each other's webhooks.
# Author:      CliveS & Claude Opus 4.8
# Date:        19-06-2026

from __future__ import annotations


class FakeDev:
    """Minimal stand-in for an indigo device record."""
    def __init__(self, dev_id, name, type_id="shellyRelay",
                 mac="", ip="", channel="0", enabled=True, configured=True):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = enabled
        self.configured   = configured
        self.pluginProps  = {
            "mac_address": mac,
            "ip_address":  ip,
            "channel_id":  channel,
        }


def _detect(plugin_mod, devices):
    """Point the device iterator at `devices` and run the detector.

    Target the plugin module's OWN `indigo` reference (not sys.modules["indigo"],
    which test_plugin.py may have swapped for its own stub) so the iterator we set
    is the one the method actually reads.
    """
    plugin_mod.indigo.devices.iter = lambda *a, **k: list(devices)
    # _duplicate_device_ids does not touch self, so any receiver works.
    return plugin_mod.Plugin._duplicate_device_ids(object())


def test_same_mac_same_channel_flags_higher_id(plugin_mod):
    """The exact bug: two records, identical MAC + channel -> one is a duplicate."""
    keeper = FakeDev(100, "Dehumidifier Plug", mac="3C8A1FED0728", ip="192.168.4.106")
    dupe   = FakeDev(200, "Dream Router Plug", mac="3C8A1FED0728", ip="192.168.4.106")
    dup_ids, collisions = _detect(plugin_mod, [dupe, keeper])  # unsorted input
    assert dup_ids == {200}                       # higher id is the loser
    assert len(collisions) == 1
    ident, kept, losers = collisions[0]
    assert ident == "3C8A1FED0728"
    assert kept.id == 100                          # lowest id kept
    assert [d.id for d in losers] == [200]


def test_multi_channel_same_mac_not_flagged(plugin_mod):
    """A 2-channel relay shares a MAC across channels — legitimate, not a duplicate."""
    ch0 = FakeDev(100, "Relay Ch1", mac="AABBCCDDEEFF", channel="0")
    ch1 = FakeDev(101, "Relay Ch2", mac="AABBCCDDEEFF", channel="1")
    dup_ids, collisions = _detect(plugin_mod, [ch0, ch1])
    assert dup_ids == set()
    assert collisions == []


def test_blu_devices_sharing_gateway_ip_not_flagged(plugin_mod):
    """BLU devices legitimately share the BLE gateway IP — excluded from detection."""
    a = FakeDev(100, "BLU Button A", type_id="shellyBluButton", ip="192.168.1.50")
    b = FakeDev(101, "BLU Button B", type_id="shellyBluRC4",    ip="192.168.1.50")
    dup_ids, collisions = _detect(plugin_mod, [a, b])
    assert dup_ids == set()
    assert collisions == []


def test_distinct_devices_none_flagged(plugin_mod):
    a = FakeDev(100, "Plug A", mac="AAAAAAAAAAAA", ip="192.168.1.10")
    b = FakeDev(101, "Plug B", mac="BBBBBBBBBBBB", ip="192.168.1.11")
    dup_ids, collisions = _detect(plugin_mod, [a, b])
    assert dup_ids == set()
    assert collisions == []


def test_macless_records_collide_on_ip(plugin_mod):
    """When no MAC is stored, IP + channel is the fallback identity."""
    a = FakeDev(100, "Plug A", mac="", ip="192.168.1.20")
    b = FakeDev(200, "Plug B", mac="", ip="192.168.1.20")
    dup_ids, collisions = _detect(plugin_mod, [a, b])
    assert dup_ids == {200}
    assert collisions[0][0] == "192.168.1.20"


def test_disabled_or_unconfigured_ignored(plugin_mod):
    """Disabled / unconfigured records don't count as live duplicates."""
    keeper = FakeDev(100, "Live",      mac="3C8A1FED0728")
    off    = FakeDev(200, "Disabled",  mac="3C8A1FED0728", enabled=False)
    unconf = FakeDev(300, "Unconf",    mac="3C8A1FED0728", configured=False)
    dup_ids, collisions = _detect(plugin_mod, [keeper, off, unconf])
    assert dup_ids == set()
    assert collisions == []
