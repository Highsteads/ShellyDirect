#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v440_discovered_devices.py
# Description: Contract tests for v4.4.0 — the discovered-Shelly list, the
#              "Discovered Shelly" menu in the device dialogs and Plugins ->
#              ShellyDirect -> Create Indigo Devices... The key guard is
#              parity: a device made by the new menu must get the same type,
#              name and props as Discover Shelly Devices would have given it.
# Author:      CliveS & Claude
# Date:        02-11-2026
# Version:     1.0

from __future__ import annotations

import threading

import pytest


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", mac="", ip="", channel="0"):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = True
        self.configured   = True
        self.pluginProps  = {"ip_address": ip, "channel_id": channel}
        if mac:
            self.pluginProps["mac_address"] = mac


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body       = body or {}

    def json(self):
        return self._body


class _Logger:
    def __init__(self):
        self.lines = []

    def debug(self, msg):   self.lines.append(("DEBUG", msg))
    def info(self, msg):    self.lines.append(("INFO", msg))
    def warning(self, msg): self.lines.append(("WARNING", msg))
    def error(self, msg):   self.lines.append(("ERROR", msg))


# A Plus 2PM in relay profile, a Plus 2PM in cover profile, a Plus Plug UK and
# a Pro 3EM, as Shelly.GetDeviceInfo describes them.
SHELLYS = {
    "192.168.1.40": {"app": "PlusPlugUK", "model": "SNPL-00112UK", "gen": 2,
                     "name": "Kettle", "mac": "AABBCC000040"},
    "192.168.1.41": {"app": "Plus2PM", "model": "SNSW-102P16EU", "gen": 2,
                     "name": "", "mac": "AABBCC000041"},
    "192.168.1.42": {"app": "Plus2PM", "model": "SNSW-102P16EU", "gen": 2,
                     "name": "Lounge Blind", "mac": "AABBCC000042"},
    "192.168.1.43": {"app": "Pro3EM", "model": "SPEM-003CEBEU", "gen": 2,
                     "name": "shellypro3em-aabbcc000043", "mac": "AABBCC000043"},
}
COVER_IPS = {"192.168.1.42"}


def fake_rget(url, params=None, timeout=None):
    host = url.split("//", 1)[1].split("/", 1)[0]
    if host not in SHELLYS:
        raise ConnectionError("no route")
    if "Shelly.GetDeviceInfo" in url:
        return FakeResp(200, SHELLYS[host])
    if "Cover.GetStatus" in url:
        return FakeResp(200, {"state": "stopped"}) if host in COVER_IPS else FakeResp(404)
    return FakeResp(404)


@pytest.fixture
def world(plugin_mod, monkeypatch):
    """A Plugin built with object.__new__, a device list, and captured log/creates."""
    devices = []
    logged  = []
    created = []
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter",
                        lambda *a, **k: list(devices), raising=False)
    monkeypatch.setattr(plugin_mod.indigo.devices, "__contains__",
                        lambda self, name: any(d.name == name for d in devices),
                        raising=False)
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": logged.append((level, msg)))

    p = object.__new__(plugin_mod.Plugin)
    p.logger           = _Logger()
    p.subnets          = ["192.168.1"]
    p._stopping        = False
    p._discovered      = {}
    p._discovered_lock = threading.RLock()
    p._probing         = set()
    p._scan_running    = False
    p._create_lock     = threading.Lock()
    p._mdns_map        = {}
    p._mdns_lock       = threading.RLock()
    p._mdns_refreshed  = 0.0
    p._zc              = None
    p._rget            = fake_rget
    p._get_or_create_device_folder = lambda: 7

    def _create(ip, type_id, has_pm, name, folder_id, extra_props=None):
        dev = FakeDev(1000 + len(created), name, type_id=type_id, ip=ip,
                      mac=(extra_props or {}).get("mac_address", ""),
                      channel=(extra_props or {}).get("channel_id", "0"))
        created.append({"ip": ip, "type": type_id, "has_pm": has_pm, "name": name,
                        "extra": dict(extra_props or {})})
        devices.append(dev)
        return dev
    p._create_device = _create
    return p, devices, created, logged


def _probe_all(p):
    for ip in SHELLYS:
        assert p._probe_shelly(ip) is not None, ip


# ── channel_specs: the pure mapping ──────────────────────────────────────────

def test_single_channel_relay(plugin_mod):
    specs = plugin_mod.channel_specs("Plus Plug UK", True, "shellyRelay", 1)
    assert [(s["type_id"], s["channel"], s["suffix"]) for s in specs] == [("shellyRelay", 0, "")]
    assert specs[0]["has_pm"] is True


def test_two_channel_relay_is_two_devices(plugin_mod):
    specs = plugin_mod.channel_specs("Plus 2PM", True, "shellyRelay", 2, cover_mode=False)
    assert [(s["channel"], s["suffix"], s["extra"]["channel_id"]) for s in specs] == \
        [(0, " Ch1", "0"), (1, " Ch2", "1")]


def test_two_channel_relay_in_cover_profile_is_one_cover(plugin_mod):
    specs = plugin_mod.channel_specs("Plus 2PM", True, "shellyRelay", 2, cover_mode=True)
    assert len(specs) == 1
    assert specs[0]["type_id"] == "shellyCover"
    assert specs[0]["label"] == "Plus 2PM Cover"
    assert specs[0]["extra"] == {"poll_interval": "10"}


def test_inconclusive_cover_probe_offers_nothing(plugin_mod):
    """Guessing relay vs blind would create the wrong type for good."""
    assert plugin_mod.channel_specs("Plus 2PM", True, "shellyRelay", 2, cover_mode=None) == []


def test_three_phase_meter_is_one_device(plugin_mod):
    specs = plugin_mod.channel_specs("Pro 3EM", True, "shellyEM", 3)
    assert len(specs) == 1 and specs[0]["extra"]["is_3phase"] is True


def test_multi_em1_is_one_device_per_channel_and_not_3phase(plugin_mod):
    specs = plugin_mod.channel_specs("Pro EM", True, "shellyEM", 2)
    assert [s["extra"]["is_3phase"] for s in specs] == [False, False]


def test_cover_type_polls_every_10s(plugin_mod):
    specs = plugin_mod.channel_specs("Plus Cover", True, "shellyCover", 1)
    assert specs[0]["extra"]["poll_interval"] == "10"


def test_pick_key_round_trip(plugin_mod):
    key = plugin_mod.pick_key("aa:bb:cc:00:00:41", "shellyRelay", 1)
    assert key == "AABBCC000041|shellyRelay|1"
    assert plugin_mod.parse_pick_key(key) == ("AABBCC000041", "shellyRelay", 1)
    for junk in ("", None, "_none_", "a|b", "AABBCC000041|shellyRelay|x"):
        assert plugin_mod.parse_pick_key(junk) is None


def test_display_name_ignores_the_mac_based_default(plugin_mod):
    """Same rule as _build_device_name: 'xxx-' plus 6 hex digits is a default."""
    assert plugin_mod.shelly_display_name({"name": "Kettle", "label": "Plus Plug UK"}) == "Kettle"
    assert plugin_mod.shelly_display_name(
        {"name": "shellypro3em-c0ffee", "label": "Pro 3EM"}) == "Pro 3EM"
    assert plugin_mod.shelly_display_name({"name": "", "label": "Pro 3EM"}) == "Pro 3EM"


def test_channel_owner_ip_only_record(plugin_mod):
    entry = {"mac": "AABBCC000040", "ip": "192.168.1.40"}
    spec  = {"channel": 0}
    assert plugin_mod.channel_owner(entry, spec, {("192.168.1.40", "0"): (5, "Old")}) == (5, "Old")
    assert plugin_mod.channel_owner(entry, spec, {("AABBCC000040", "0"): (6, "New")}) == (6, "New")
    assert plugin_mod.channel_owner(entry, {"channel": 1}, {("AABBCC000040", "0"): (6, "N")}) is None


# ── Parity with Discover Shelly Devices ──────────────────────────────────────

def test_create_menu_makes_what_discover_would(world, monkeypatch):
    """Same types, names and props as the auto-creating Discover run."""
    p, devices, created, _ = world

    # 1. The old path. Discover only looks at the four fake addresses.
    p._existing_device_ips  = lambda: {d.pluginProps["ip_address"] for d in devices}
    p._existing_device_macs = lambda: {}
    p._remember_shelly      = lambda *a, **k: None
    p._discover_thread("192.168.1")
    via_discover = sorted((c["ip"], c["type"], c["has_pm"], c["name"],
                           tuple(sorted(c["extra"].items()))) for c in created)
    assert len(via_discover) == 1 + 2 + 1 + 1      # plug, 2 relays, 1 cover, 1 meter

    # 2. The new path, on an empty Indigo.
    devices.clear()
    created.clear()
    del p._remember_shelly
    _probe_all(p)
    p._create_discovered_thread(p._discovered_entries(),
                                {t for fam in __import__("plugin").CREATE_FAMILIES.values()
                                 for t in fam})
    via_menu = sorted((c["ip"], c["type"], c["has_pm"], c["name"],
                       tuple(sorted(c["extra"].items()))) for c in created)
    assert via_menu == via_discover


# ── Device dialog menu ───────────────────────────────────────────────────────

def test_dialog_lists_only_free_channels_of_its_own_type(world):
    p, devices, _, _ = world
    _probe_all(p)
    devices.append(FakeDev(50, "2PM Ch1", mac="AABBCC000041", ip="192.168.1.41", channel="0"))
    rows = p.getDiscoveredChannels(typeId="shellyRelay", targetId=99)
    keys = [k for k, _ in rows]
    assert keys[0] == "_none_"
    assert "AABBCC000041|shellyRelay|0" not in keys          # owned by device 50
    assert "AABBCC000041|shellyRelay|1" in keys
    assert "AABBCC000040|shellyRelay|0" in keys
    assert not any("shellyCover" in k or "shellyEM" in k for k in keys)


def test_device_being_edited_keeps_its_own_channel(world):
    p, devices, _, _ = world
    _probe_all(p)
    devices.append(FakeDev(50, "2PM Ch1", mac="AABBCC000041", ip="192.168.1.41", channel="0"))
    keys = [k for k, _ in p.getDiscoveredChannels(typeId="shellyRelay", targetId=50)]
    assert "AABBCC000041|shellyRelay|0" in keys


def test_empty_list_still_has_a_valid_first_row(world):
    p, _, _, _ = world
    rows = p.getDiscoveredChannels(typeId="shellyRelay", targetId=1)
    assert len(rows) == 1 and rows[0][0] == "_none_"


def test_pick_fills_the_fields(world):
    p, _, _, _ = world
    _probe_all(p)
    vals = p.discoveredChannelPicked({"shelly_pick": "AABBCC000041|shellyRelay|1"},
                                     "shellyRelay", 99)
    assert vals["ip_address"] == "192.168.1.41"
    assert vals["channel_id"] == "1"
    assert vals["has_pm"] is True
    assert "mac_address" not in vals         # only stored on a matching save


def test_save_stores_the_mac_when_the_pick_still_matches(world):
    p, _, _, _ = world
    _probe_all(p)
    vals = {"shelly_pick": "AABBCC000041|shellyRelay|1",
            "ip_address": "192.168.1.41", "channel_id": "1"}
    errors = {}
    p._validate_pick(vals, "shellyRelay", 99, errors)
    assert errors == {}
    assert vals["mac_address"] == "AABBCC000041"


def test_save_drops_a_pick_the_user_typed_over(world):
    p, _, _, _ = world
    _probe_all(p)
    vals = {"shelly_pick": "AABBCC000041|shellyRelay|1",
            "ip_address": "192.168.1.99", "channel_id": "1"}
    errors = {}
    p._validate_pick(vals, "shellyRelay", 99, errors)
    assert errors == {}
    assert vals["shelly_pick"] == "_none_"
    assert "mac_address" not in vals


def test_save_refuses_a_channel_taken_meanwhile(world):
    p, devices, _, _ = world
    _probe_all(p)
    devices.append(FakeDev(50, "Taken", mac="AABBCC000041", ip="192.168.1.41", channel="1"))
    vals = {"shelly_pick": "AABBCC000041|shellyRelay|1",
            "ip_address": "192.168.1.41", "channel_id": "1"}
    errors = {}
    p._validate_pick(vals, "shellyRelay", 99, errors)
    assert "Taken" in errors["shelly_pick"]


# ── Create Indigo Devices... ─────────────────────────────────────────────────

def test_create_menu_needs_a_kind_ticked(world):
    p, _, _, _ = world
    _probe_all(p)
    vals = {k: False for k in ("inc_relays", "inc_covers", "inc_lights",
                               "inc_meters", "inc_sensors")}
    ok, _, errors = p.menuCreateDiscoveredDevices(vals)
    assert ok is False and "inc_relays" in errors


def test_create_menu_says_when_there_is_nothing_to_create(world):
    p, _, _, _ = world
    ok, _, errors = p.menuCreateDiscoveredDevices({"shelly_choice": "_all_"})
    assert ok is False and "Nothing to create" in errors["shelly_choice"]


def test_create_skips_existing_channels_and_unticked_kinds(world):
    p, devices, created, _ = world
    _probe_all(p)
    devices.append(FakeDev(50, "2PM Ch1", mac="AABBCC000041", ip="192.168.1.41", channel="0"))
    p._create_discovered_thread(p._discovered_entries(), {"shellyRelay"})
    made = sorted((c["ip"], c["extra"].get("channel_id", "0")) for c in created)
    assert made == [("192.168.1.40", "0"), ("192.168.1.41", "1")]


def test_create_for_one_chosen_shelly(world, monkeypatch):
    p, _, created, _ = world
    _probe_all(p)
    started = []
    monkeypatch.setattr(threading, "Thread",
                        lambda target, args=(), daemon=None: started.append((target, args))
                        or type("T", (), {"start": lambda self: None})())
    assert p.menuCreateDiscoveredDevices({"shelly_choice": "AABBCC000040"}) is True
    target, args = started[0]
    target(*args)
    assert [c["ip"] for c in created] == ["192.168.1.40"]


def test_create_refuses_a_shelly_now_answering_as_another_mac(world, monkeypatch):
    p, _, created, logged = world
    _probe_all(p)
    monkeypatch.setitem(SHELLYS, "192.168.1.40", dict(SHELLYS["192.168.1.40"], mac="FFEEDD000001"))
    p._create_discovered_thread([e for e in p._discovered_entries()
                                 if e["mac"] == "AABBCC000040"], {"shellyRelay"})
    assert created == []
    assert any(lvl == "WARNING" and "did not answer" in m for lvl, m in logged)


def test_shelly_menu_rows(world):
    p, devices, _, _ = world
    _probe_all(p)
    devices.append(FakeDev(50, "Kettle", mac="AABBCC000040", ip="192.168.1.40"))
    rows = dict(p.getDiscoveredShellys())
    assert rows["AABBCC000040"].endswith("all in Indigo")
    assert rows["AABBCC000041"].endswith("2 of 2 not in Indigo")
    assert rows["_all_"].startswith("All discovered Shellys (three Shellys")


# ── Background probing ───────────────────────────────────────────────────────

def test_probe_soon_skips_a_fresh_entry(world, monkeypatch):
    p, _, _, _ = world
    assert p._probe_shelly("192.168.1.40") is not None
    assert p._probe_soon("AABBCC000040", "192.168.1.40") is None
    worker = p._probe_soon("AABBCC000040", "192.168.1.77")     # moved: probe again
    assert worker is not None
    worker.join(2)


def test_probe_ignores_a_non_shelly(world):
    p, _, _, _ = world
    assert p._probe_shelly("192.168.1.250") is None
    assert p._discovered == {}


def test_nothing_is_created_by_probing(world):
    p, _, created, _ = world
    _probe_all(p)
    assert created == []
    assert len(p._discovered) == 4
