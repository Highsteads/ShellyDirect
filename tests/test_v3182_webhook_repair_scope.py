#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v3182_webhook_repair_scope.py
# Description: Regression test for v3.18.2 — the stale-webhook repair lookup
#              matched on ip_address ALONE, while the other two selections on
#              ip_address in the same file split on BLU_TYPES. A BLU device
#              stores its GATEWAY's address, so a gateway and everything it
#              relays share one IP and the repair could reconfigure a BLU
#              child's webhooks as though it were the gateway.
# Author:      CliveS & Claude Opus 5
# Date:        20-09-2026
# Version:     1.0

from __future__ import annotations

import types


class FakeDev:
    def __init__(self, dev_id, name, type_id, ip):
        self.id, self.name, self.deviceTypeId = dev_id, name, type_id
        self.enabled = self.configured = True
        self.pluginProps = {"ip_address": ip}


GATEWAY_IP = "192.168.1.60"


def _devices(order):
    """The estate's shape: one mains gateway and the BLU devices it relays,
    all carrying the SAME ip_address. `order` decides which the iterator hands
    back first — the whole point, since the lookup takes the first match."""
    gw  = FakeDev(1, "Hall Gateway", "shellyRelay", GATEWAY_IP)
    blu = FakeDev(2, "Hall Button",  "shellyBluButton", GATEWAY_IP)
    rc4 = FakeDev(3, "Hall Remote",  "shellyBluRC4", GATEWAY_IP)
    return {"gateway-first": [gw, blu, rc4],
            "blu-first":     [blu, rc4, gw]}[order]


def _run_repair(plugin_mod, monkeypatch, devices):
    """Drive _repair_stale_webhook with a stubbed device list, capturing which
    device it decided to reconfigure instead of starting a real thread."""
    plugin = plugin_mod.Plugin.__new__(plugin_mod.Plugin)
    plugin._webhook_repairs = {}
    plugin.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None,
        error=lambda *a, **k: None, debug=lambda *a, **k: None)

    chosen = []
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter",
                        lambda *_a, **_k: list(devices), raising=False)
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda target=None, args=(), daemon=None:
                            types.SimpleNamespace(
                                start=lambda: chosen.append(args[0])))
    plugin._repair_stale_webhook(GATEWAY_IP, stale_dev_id=999)
    return chosen


def test_the_gateway_is_chosen_when_it_comes_first(plugin_mod, monkeypatch):
    chosen = _run_repair(plugin_mod, monkeypatch, _devices("gateway-first"))
    assert [d.name for d in chosen] == ["Hall Gateway"]


def test_a_blu_child_is_never_chosen_even_when_it_comes_first(plugin_mod, monkeypatch):
    """The bug. Device order is Indigo's to decide, so "it worked when I tried
    it" is not a property of the code — matching must exclude BLU types."""
    chosen = _run_repair(plugin_mod, monkeypatch, _devices("blu-first"))
    assert [d.name for d in chosen] == ["Hall Gateway"]
    assert all(d.deviceTypeId not in plugin_mod.BLU_TYPES for d in chosen)


def test_nothing_is_reconfigured_when_only_blu_devices_match(plugin_mod, monkeypatch):
    """A BLU-only match is not a gateway we can repair. Doing nothing and
    warning beats reconfiguring the wrong device."""
    blu = [d for d in _devices("blu-first") if d.deviceTypeId in plugin_mod.BLU_TYPES]
    assert _run_repair(plugin_mod, monkeypatch, blu) == []


def test_the_sixty_second_rate_limit_still_holds(plugin_mod, monkeypatch):
    """v3.13's guard against one repair thread per request. The scope fix must
    not have moved the early return that enforces it."""
    devices = _devices("gateway-first")
    plugin = plugin_mod.Plugin.__new__(plugin_mod.Plugin)
    plugin._webhook_repairs = {}
    plugin.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None,
        error=lambda *a, **k: None, debug=lambda *a, **k: None)
    chosen = []
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter",
                        lambda *_a, **_k: list(devices), raising=False)
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda target=None, args=(), daemon=None:
                            types.SimpleNamespace(
                                start=lambda: chosen.append(args[0])))
    plugin._repair_stale_webhook(GATEWAY_IP, 999)
    plugin._repair_stale_webhook(GATEWAY_IP, 999)
    assert len(chosen) == 1
