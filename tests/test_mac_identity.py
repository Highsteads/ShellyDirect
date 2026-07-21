#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_mac_identity.py
# Description: Contract tests for v3.16.0 — identity is the MAC address, not the
#              IP. Covers the poll gate (match / mismatch / no stored MAC),
#              mDNS parsing for BOTH Shelly service types, re-resolution moving
#              a device to a new address, the quiet handling of devices that are
#              simply switched off at the wall, the duplicate-address guard and
#              the energy-history prune.
# Author:      CliveS & Claude Opus 4.8
# Date:        21-07-2026
# Version:     1.0

from __future__ import annotations

import threading
import time

import pytest


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeDev:
    def __init__(self, dev_id=1, name="Test Plug", type_id="shellyRelay",
                 mac="", ip="", channel="0", props=None, states=None):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = True
        self.configured   = True
        self.pluginProps  = {"ip_address": ip, "channel_id": channel}
        if mac:
            self.pluginProps["mac_address"] = mac
        if props:
            self.pluginProps.update(props)
        self.states       = states if states is not None else {}
        self.state_writes = []
        self.prop_writes  = []

    def updateStateOnServer(self, key, value, uiValue=None, **_kw):
        self.states[key] = value
        self.state_writes.append((key, value))

    def replacePluginPropsOnServer(self, new_props):
        self.pluginProps = dict(new_props)
        self.prop_writes.append(dict(new_props))


class _Logger:
    def __init__(self):
        self.lines = []

    def debug(self, msg):   self.lines.append(("DEBUG", msg))
    def info(self, msg):    self.lines.append(("INFO", msg))
    def warning(self, msg): self.lines.append(("WARNING", msg))
    def error(self, msg):   self.lines.append(("ERROR", msg))


@pytest.fixture
def logged(plugin_mod, monkeypatch):
    """Capture module-level log() calls as (level, message)."""
    lines = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": lines.append((level, msg)))
    return lines


def make_plugin(plugin_mod, macs_at=None, verify_secs=3600):
    """A Plugin instance with only the attributes the identity code touches.

    Built with object.__new__ so the real methods are bound and tested — no
    re-implementation of the logic under test.
    """
    p = object.__new__(plugin_mod.Plugin)
    p.logger            = _Logger()
    p.fail_count        = {}
    p.last_polled       = {}
    p.last_seen         = {}
    p.webhook_repair_fails = {}
    p.mac_verify_secs   = verify_secs
    p._mdns_map         = {}
    p._mdns_lock        = threading.RLock()
    p._mdns_refreshed   = time.time()      # suppress re-browse during tests
    p._zc               = None
    p._zc_browser       = None
    p._mac_verified     = {}
    p._identity_bad     = {}
    p._identity_warned  = set()
    p._relocate_attempt = {}
    p._confirm_attempt  = {}
    p._props_lock       = threading.RLock()
    p._energy_lock      = threading.RLock()
    p.energy_data       = {}
    # The network is replaced by a MAC-per-address table.
    p._reads            = []

    def _read(ip):
        p._reads.append(ip)
        return (macs_at or {}).get(ip, "")

    p._read_device_mac = _read
    return p


# ── MAC normalising ──────────────────────────────────────────────────────────

def test_normalise_mac_forms_compare_equal(plugin_mod):
    n = plugin_mod.normalise_mac
    assert n("3C8A1FECFC84") == "3C8A1FECFC84"
    assert n("3c8a1fecfc84") == "3C8A1FECFC84"
    assert n("3c:8a:1f:ec:fc:84") == "3C8A1FECFC84"
    assert n("3c-8a-1f-ec-fc-84") == "3C8A1FECFC84"


def test_normalise_mac_rejects_rubbish(plugin_mod):
    n = plugin_mod.normalise_mac
    assert n("") == ""
    assert n(None) == ""
    assert n("not a mac") == ""
    assert n("3C8A1FECFC") == ""        # too short


# ── mDNS name parsing — BOTH service types ───────────────────────────────────

def test_gen2_shelly_tcp_instance_parses(plugin_mod):
    # _shelly._tcp, lower-case MAC embedded in the instance name
    assert plugin_mod.mac_from_mdns(
        "shellypluspluguk-3c8a1fed1000._shelly._tcp.local."
    ) == "3C8A1FED1000"


def test_gen1_http_tcp_instances_parse(plugin_mod):
    # _http._tcp, upper-case MAC — half the fleet only advertises here
    assert plugin_mod.mac_from_mdns(
        "shelly1-8CAAB5056390._http._tcp.local."
    ) == "8CAAB5056390"
    assert plugin_mod.mac_from_mdns(
        "shellyuni-483FDA829C98._http._tcp.local."
    ) == "483FDA829C98"


def test_non_shelly_http_advertisement_ignored(plugin_mod):
    assert plugin_mod.mac_from_mdns("Brother HL-L2350DW._http._tcp.local.") == ""
    assert plugin_mod.mac_from_mdns("someserver._http._tcp.local.") == ""


def test_txt_id_wins_over_name(plugin_mod):
    # Gen1 publishes TXT id; a renamed Gen1 is still identifiable from it.
    props = {b"id": b"shelly1-8CAAB5056390", b"app": b"switch1"}
    assert plugin_mod.mac_from_mdns("Twigs Plug._http._tcp.local.",
                                    props) == "8CAAB5056390"


def test_gen2_txt_has_no_mac_so_the_name_carries_it(plugin_mod):
    # Live shape of a Gen2+ record: gen/app/ver only.
    props = {b"gen": b"2", b"app": b"PlusPlugUK", b"ver": b"1.7.5"}
    assert plugin_mod.mac_from_mdns(
        "shellypluspluguk-3c8a1fed1000._shelly._tcp.local.", props
    ) == "3C8A1FED1000"


def test_renamed_gen2_record_yields_nothing_and_that_is_fine(plugin_mod):
    # Every Gen2+ device advertises twice — once under the user's name with no
    # MAC anywhere, once under its default name. The second one carries it.
    props = {b"gen": b"2", b"app": b"PlusPlugUK", b"ver": b"1.7.5"}
    assert plugin_mod.mac_from_mdns("Sonos Woofer Plug._shelly._tcp.local.",
                                    props) == ""


def test_camera_txt_mac_is_not_mistaken_for_a_shelly(plugin_mod):
    # Cameras on _http._tcp publish a TXT 'mac' of their own.
    assert plugin_mod.mac_from_mdns("DriveCamera._http._tcp.local.",
                                    {b"mac": b"B44C3BCDBE73"}) == ""


# ── mDNS bookkeeping ─────────────────────────────────────────────────────────

def test_mdns_note_and_lookup(plugin_mod):
    p = make_plugin(plugin_mod)
    p._mdns_note("3c8a1fecfc84", "192.168.1.119")
    assert p._mdns_lookup("3C:8A:1F:EC:FC:84") == "192.168.1.119"
    assert p._mdns_lookup("A085E3BD3928") is None


def test_mdns_note_ignores_junk(plugin_mod):
    p = make_plugin(plugin_mod)
    p._mdns_note("", "192.168.1.5")
    p._mdns_note("3C8A1FECFC84", "")
    assert p._mdns_map == {}


# ── The poll gate ────────────────────────────────────────────────────────────

def test_matching_mac_allows_the_poll(plugin_mod, logged):
    p   = make_plugin(plugin_mod, macs_at={"192.168.1.118": "3C8A1FECFC84"})
    dev = FakeDev(mac="3C8A1FECFC84", ip="192.168.1.118")
    assert p._target_ip(dev) == "192.168.1.118"
    assert logged == []                       # a healthy device says nothing


def test_verification_is_throttled(plugin_mod):
    p   = make_plugin(plugin_mod, macs_at={"192.168.1.118": "3C8A1FECFC84"})
    dev = FakeDev(mac="3C8A1FECFC84", ip="192.168.1.118")
    for _ in range(5):
        assert p._target_ip(dev) == "192.168.1.118"
    assert len(p._reads) == 1                 # one identity check per interval


def test_mismatched_mac_refuses_the_poll(plugin_mod, logged):
    # The 21-Jul incident: another plug now answers on this address.
    p   = make_plugin(plugin_mod, macs_at={"192.168.4.118": "3C8A1FECFC84"})
    dev = FakeDev(name="Washing Machine Monitor",
                  mac="A085E3BD3928", ip="192.168.4.118")
    assert p._target_ip(dev) is None          # nothing may be written
    assert dev.state_writes == []
    warnings = [m for lvl, m in logged if lvl == "WARNING"]
    assert len(warnings) == 1
    assert "A085E3BD3928" in warnings[0]      # both MACs named
    assert "3C8A1FECFC84" in warnings[0]
    assert "192.168.4.118" in warnings[0]     # and the address


def test_mismatch_warns_once_not_every_poll(plugin_mod, logged):
    p   = make_plugin(plugin_mod, macs_at={"192.168.4.118": "3C8A1FECFC84"},
                      verify_secs=0)
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    for _ in range(10):
        assert p._target_ip(dev) is None
    assert len([m for lvl, m in logged if lvl == "WARNING"]) == 1


def test_mismatch_then_found_elsewhere_self_heals(plugin_mod, logged):
    p = make_plugin(plugin_mod, macs_at={"192.168.4.118": "3C8A1FECFC84",
                                         "192.168.4.119": "A085E3BD3928"})
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    p._mdns_note("A085E3BD3928", "192.168.4.119")
    assert p._target_ip(dev) == "192.168.4.119"
    assert dev.pluginProps["ip_address"] == "192.168.4.119"     # stored props updated
    infos = [m for lvl, m in logged if lvl == "INFO"]
    assert any("192.168.4.119" in m and "address updated" in m for m in infos)
    # And it is trusted again straight away
    assert p._identity_bad == {}


def test_relocation_confirms_before_rewriting_props(plugin_mod, logged):
    # mDNS says the MAC is at .120 but something else answers there — refuse.
    p = make_plugin(plugin_mod, macs_at={"192.168.4.120": "AAAAAAAAAAAA"})
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    p._mdns_note("A085E3BD3928", "192.168.4.120")
    p._identity_bad[dev.id] = "3C8A1FECFC84"
    assert p._target_ip(dev) is None
    assert dev.pluginProps["ip_address"] == "192.168.4.118"     # untouched
    assert dev.prop_writes == []


def test_device_with_no_stored_mac_keeps_working_and_learns(plugin_mod, logged):
    p   = make_plugin(plugin_mod, macs_at={"192.168.1.50": "8CAAB5056390"})
    dev = FakeDev(ip="192.168.1.50")
    assert dev.pluginProps.get("mac_address") is None
    assert p._target_ip(dev) == "192.168.1.50"                  # still polled
    assert dev.pluginProps["mac_address"] == "8CAAB5056390"     # learned
    assert any("8CAAB5056390" in m for _lvl, m in logged)


def test_unreadable_mac_does_not_block_the_poll(plugin_mod, logged):
    # Device switched off at the wall: GetDeviceInfo fails, the poll proceeds
    # and fails in the normal way, and nothing is said.
    p   = make_plugin(plugin_mod, macs_at={})
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    assert p._target_ip(dev) == "192.168.4.118"
    assert logged == []


def test_failing_device_skips_the_extra_request(plugin_mod):
    p   = make_plugin(plugin_mod, macs_at={"192.168.4.118": "A085E3BD3928"})
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    p.fail_count[dev.id] = 7
    assert p._target_ip(dev) == "192.168.4.118"
    assert p._reads == []          # no second timeout per tick for an absent plug


def test_returning_device_is_reverified(plugin_mod):
    p   = make_plugin(plugin_mod, macs_at={"192.168.4.118": "A085E3BD3928"})
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    p._mac_verified[dev.id] = time.time()
    p.fail_count[dev.id]    = 4
    dev.states["deviceOnline"] = True
    p._mark_online(dev)
    assert dev.id not in p._mac_verified            # forced re-check next tick
    assert p._target_ip(dev) == "192.168.4.118"
    assert p._reads == ["192.168.4.118"]


# ── Absent devices stay quiet ────────────────────────────────────────────────

def test_relocation_is_throttled_and_silent(plugin_mod, logged):
    p   = make_plugin(plugin_mod)
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118")
    for _ in range(20):
        p._try_relocate(dev)
    assert p._reads == []          # MAC not advertised: a dict lookup, no network
    assert logged == []            # and not one line in the log


def test_poll_failure_does_not_spam(plugin_mod, logged, monkeypatch):
    p   = make_plugin(plugin_mod)
    dev = FakeDev(mac="A085E3BD3928", ip="192.168.4.118",
                  props={"suppress_offline_alerts": True})
    dev.states["deviceOnline"] = True
    monkeypatch.setattr(plugin_mod.Plugin, "_fire_trigger",
                        lambda *a, **k: None, raising=False)
    for _ in range(10):
        p._poll_failed(dev, "timeout")
    assert logged == []
    assert dev.states["deviceOnline"] is False


# ── Duplicate-address guard ──────────────────────────────────────────────────

def _patch_devices(plugin_mod, monkeypatch, devs):
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *_a: list(devs))


def test_address_clash_detected(plugin_mod, monkeypatch):
    p     = make_plugin(plugin_mod)
    other = FakeDev(dev_id=2, name="Garage Outside Mains Plug",
                    mac="3C8A1FECFC84", ip="192.168.4.118")
    _patch_devices(plugin_mod, monkeypatch, [other])
    clash = p._address_clash("192.168.4.118",
                             {"channel_id": "0", "mac_address": "A085E3BD3928"},
                             "shellyRelay", 1)
    assert clash == "Garage Outside Mains Plug"


def test_same_device_different_channel_is_not_a_clash(plugin_mod, monkeypatch):
    p     = make_plugin(plugin_mod)
    other = FakeDev(dev_id=2, name="Plus 2PM ch0", mac="3C8A1FECFC84",
                    ip="192.168.4.118", channel="0")
    _patch_devices(plugin_mod, monkeypatch, [other])
    assert p._address_clash("192.168.4.118",
                            {"channel_id": "1", "mac_address": "3C8A1FECFC84"},
                            "shellyRelay", 3) == ""


def test_same_mac_same_address_is_not_a_clash(plugin_mod, monkeypatch):
    p     = make_plugin(plugin_mod)
    other = FakeDev(dev_id=2, name="Same box", mac="3C8A1FECFC84",
                    ip="192.168.4.118")
    _patch_devices(plugin_mod, monkeypatch, [other])
    assert p._address_clash("192.168.4.118",
                            {"channel_id": "0", "mac_address": "3c8a1fecfc84"},
                            "shellyRelay", 3) == ""


# ── Energy history prune ─────────────────────────────────────────────────────

def test_prune_removes_orphans_only(plugin_mod, monkeypatch, logged):
    p = make_plugin(plugin_mod)
    p.energy_data = {"__meta__": {"last_date": "2026-07-21"},
                     "111": {"day_baseline_wh": 10},
                     "999": {"day_baseline_wh": 20}}
    monkeypatch.setattr(plugin_mod.Plugin, "_save_energy_data",
                        lambda self: None, raising=False)
    _patch_devices(plugin_mod, monkeypatch, [FakeDev(dev_id=111)])
    orphans = p._prune_energy_data()
    assert orphans == ["999"]
    assert set(p.energy_data) == {"__meta__", "111"}
