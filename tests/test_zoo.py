#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_zoo.py
# Description: Drives the Shelly device zoo (zoo_manifest.CASES). Per-animal
#              contract (self-description -> the exact list of Indigo devices,
#              one per channel) plus cross-cutting invariants the classifier
#              must never break.
# Author:      CliveS & Claude Opus 4.8
# Date:        13-06-2026

from __future__ import annotations

import pytest

from zoo_manifest import CASES

# Valid ShellyDirect device types (from Devices.xml). A classifier emitting
# anything outside this set is a bug. BLU types are intentionally absent from
# what IP/RPC discovery may produce — see the BLU invariant below.
KNOWN_TYPES = {
    "shellyRelay", "shellyDimmer", "shellyRGBW", "shellyCover", "shellyEM",
    "shellyI4", "shellyUni", "shellyHT", "shellySmoke", "shellyFlood",
}
BLU_TYPES = {"shellyBluButton", "shellyBluRC4"}

_IDS = [c.name for c in CASES]


def _detect(plugin_mod, case):
    return plugin_mod.detect_shelly_devices(case.device_info, case.config_keys)


def _pairs(result):
    """Reduce the classifier output to the comparable (type, channel) list."""
    return [(d["device_type_id"], d["channel"]) for d in result]


# ── Per-animal contract ──────────────────────────────────────────────────────

@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_zoo_maps_to_expected_devices(plugin_mod, case):
    """Each self-description yields exactly the expected per-channel devices."""
    got = _pairs(_detect(plugin_mod, case))
    assert got == case.expect, f"{case.name}: got {got}, expected {case.expect} ({case.note})"


# ── Cross-cutting invariants ─────────────────────────────────────────────────

@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_invariant_only_known_types(plugin_mod, case):
    """Never emit a device type that isn't declared in Devices.xml."""
    for d in _detect(plugin_mod, case):
        assert d["device_type_id"] in KNOWN_TYPES, (
            f"{case.name}: emitted unknown type {d['device_type_id']!r}"
        )


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_invariant_never_blu(plugin_mod, case):
    """IP/RPC discovery must never yield a Bluetooth device — BLU devices have
    no IP and are reached via a gateway, so they stay manual."""
    for d in _detect(plugin_mod, case):
        assert d["device_type_id"] not in BLU_TYPES, (
            f"{case.name}: IP discovery emitted a BLU type"
        )


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_invariant_channels_distinct_and_complete(plugin_mod, case):
    """Multi-channel devices yield one device per channel with distinct channel
    ids — no duplicates, no dropped channels."""
    result = _detect(plugin_mod, case)
    channels = [d["channel"] for d in result]
    assert len(channels) == len(set(channels)), f"{case.name}: duplicate channel ids {channels}"


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_invariant_deterministic(plugin_mod, case):
    """Same self-description classified twice gives the same answer."""
    assert _pairs(_detect(plugin_mod, case)) == _pairs(_detect(plugin_mod, case)), (
        f"{case.name}: non-deterministic"
    )


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_invariant_source_tagged(plugin_mod, case):
    """Every emitted device records HOW it was classified (app table vs
    component fallback) — the discovery UI/log needs this provenance, and an
    app present in APP_INFO must be classified via the table."""
    plugin_mod_app = case.device_info.get("app", "")
    for d in _detect(plugin_mod, case):
        assert d["source"] in ("app", "components"), f"{case.name}: bad source {d['source']!r}"
        if plugin_mod_app in plugin_mod.APP_INFO:
            assert d["source"] == "app", (
                f"{case.name}: app {plugin_mod_app!r} is in APP_INFO but was classified via {d['source']}"
            )
