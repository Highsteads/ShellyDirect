#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v319_webhook_ownership.py
# Description: Regression tests for v3.19.0 — the full review of 26-09-2026.
#              Webhook ownership (a plug carrying another device's hooks, hooks
#              registered twice, hooks pointing at an old server address), the
#              sender check on the listener, the real input event names, the
#              midnight reset's missing guards, the undo of a reset that was a
#              glitch, typed dynamic states, the model table and HTTPS.
# Author:      CliveS & Claude Opus 5.5
# Date:        26-09-2026
# Version:     1.0

from __future__ import annotations

import threading
import types

import pytest


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", ip="", mac="",
                 channel="0", props=None, states=None):
        self.id, self.name, self.deviceTypeId = dev_id, name, type_id
        self.enabled = self.configured = True
        self.pluginId = "com.clives.indigoplugin.shellydirect"
        self.pluginProps = {"ip_address": ip, "mac_address": mac, "channel_id": channel}
        if props:
            self.pluginProps.update(props)
        self.states = dict(states or {})


class FakeResp:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload, self.status_code = payload or {}, status
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


SERVER = "192.168.1.9"
PORT = 8178
CHARGER_IP, WASHER_IP = "192.168.1.119", "192.168.1.118"


def _url(dev_id, tail="type=switch&state=on", host=SERVER, port=PORT, blu=False):
    path = "shellyBluEvent" if blu else "shellyEvent"
    return f"http://{host}:{port}/{path}?devId={dev_id}&{tail}"


def _by_id(*devs):
    return {d.id: (d.deviceTypeId, d.pluginProps["ip_address"]) for d in devs}


# ── stale_hook_reason ────────────────────────────────────────────────────────

CHARGER = FakeDev(1507, "Qashqai Charger Plug", ip=CHARGER_IP)
WASHER  = FakeDev(1220, "Washing Machine Monitor", ip=WASHER_IP)


def test_a_hook_for_a_device_on_another_shelly_is_stale(plugin_mod):
    """THE 26-09-2026 live fault: the charger plug held the washing machine
    monitor's hooks. The washer device exists, so the old rule kept them."""
    why = plugin_mod.stale_hook_reason(_url(1220), CHARGER_IP, _by_id(CHARGER, WASHER),
                                       SERVER, PORT)
    assert "1220" in why and WASHER_IP in why


def test_own_hook_is_not_stale(plugin_mod):
    assert plugin_mod.stale_hook_reason(_url(1507), CHARGER_IP, _by_id(CHARGER, WASHER),
                                        SERVER, PORT) == ""


def test_a_hook_at_an_old_server_address_or_port_is_stale(plugin_mod):
    devs = _by_id(CHARGER)
    assert plugin_mod.stale_hook_reason(_url(1507, host="192.168.1.8"), CHARGER_IP,
                                        devs, SERVER, PORT)
    assert plugin_mod.stale_hook_reason(_url(1507, port=8179), CHARGER_IP,
                                        devs, SERVER, PORT)


def test_a_hook_for_a_deleted_device_is_stale(plugin_mod):
    assert plugin_mod.stale_hook_reason(_url(999), CHARGER_IP, _by_id(CHARGER), SERVER, PORT)


def test_somebody_elses_hook_is_never_touched(plugin_mod):
    assert plugin_mod.stale_hook_reason("http://nas.local/notify?x=1", CHARGER_IP,
                                        _by_id(CHARGER), SERVER, PORT) == ""


def test_blu_hooks_belong_to_blu_devices_on_that_gateway(plugin_mod):
    button = FakeDev(300, "Hall Button", type_id="shellyBluButton", ip=CHARGER_IP)
    devs = _by_id(CHARGER, button)
    assert plugin_mod.stale_hook_reason(_url(300, blu=True), CHARGER_IP, devs, SERVER, PORT) == ""
    assert plugin_mod.stale_hook_reason(_url(300, blu=True), WASHER_IP, devs, SERVER, PORT)
    # A relay's id inside a BLU URL is wrong either way.
    assert plugin_mod.stale_hook_reason(_url(1507, blu=True), CHARGER_IP, devs, SERVER, PORT)


def test_the_devid_match_respects_boundaries(plugin_mod):
    assert plugin_mod.hook_dev_id(_url(10)) == 10
    assert plugin_mod.hook_dev_id("http://x/shellyEvent?devId=101") == 101
    assert plugin_mod.hook_dev_id("http://x/shellyEvent?xdevId=5") is None


# ── classify_hooks ───────────────────────────────────────────────────────────

def _hook(hook_id, *urls, event="switch.on", cid=0):
    return {"id": hook_id, "event": event, "cid": cid, "urls": list(urls)}


def test_the_charger_plug_loses_the_washers_hooks_and_keeps_its_own(plugin_mod):
    own_on, own_off = _url(1507), _url(1507, "type=switch&state=off")
    hooks = [_hook(1, _url(1220)), _hook(2, _url(1220, "type=switch&state=off"), event="switch.off"),
             _hook(3, own_on), _hook(4, own_off, event="switch.off")]
    delete, have = plugin_mod.classify_hooks(hooks, CHARGER_IP, {own_on, own_off},
                                             _by_id(CHARGER, WASHER), SERVER, PORT)
    assert sorted(h for h, _ in delete) == [1, 2]
    assert have == {own_on, own_off}


def test_an_exact_duplicate_is_removed_once(plugin_mod):
    """The Mac Mini and Fire plugs carried every hook twice."""
    on = _url(1507)
    hooks = [_hook(1, on), _hook(2, on), _hook(3, on, event="switch.off")]
    delete, have = plugin_mod.classify_hooks(hooks, CHARGER_IP, {on},
                                             _by_id(CHARGER), SERVER, PORT)
    assert [h for h, _ in delete] == [2], "same event+cid+urls twice: drop the copy"
    assert have == {on}


def test_a_sibling_channel_on_the_same_shelly_survives(plugin_mod):
    ch1 = FakeDev(101, "Ch1", ip="192.168.1.50", channel="0")
    ch2 = FakeDev(102, "Ch2", ip="192.168.1.50", channel="1")
    hooks = [_hook(7, _url(102))]
    delete, _have = plugin_mod.classify_hooks(hooks, "192.168.1.50", {_url(101)},
                                              _by_id(ch1, ch2), SERVER, PORT)
    assert delete == []


def test_a_hook_that_also_carries_a_users_own_url_survives(plugin_mod):
    hooks = [_hook(7, _url(999), "http://nas.local/notify")]
    delete, _have = plugin_mod.classify_hooks(hooks, CHARGER_IP, set(),
                                              _by_id(CHARGER), SERVER, PORT)
    assert delete == []


# ── the listener's sender check ──────────────────────────────────────────────

def _sender_host(check=True, mdns=None):
    host = types.SimpleNamespace(webhook_source_check=check,
                                 _mdns_lock=threading.RLock(),
                                 _mdns_map=dict(mdns or {}))
    return host


def test_a_webhook_from_the_devices_own_address_is_accepted(plugin_mod):
    ok = plugin_mod.Plugin._webhook_source_ok(_sender_host(), WASHER, WASHER_IP)
    assert ok is True


def test_a_webhook_from_another_shelly_is_refused(plugin_mod):
    ok = plugin_mod.Plugin._webhook_source_ok(_sender_host(), WASHER, CHARGER_IP)
    assert ok is False


def test_a_device_that_has_just_moved_is_accepted_via_mdns(plugin_mod):
    dev = FakeDev(5, "Moved", ip="192.168.1.20", mac="AABBCC000001")
    host = _sender_host(mdns={"AABBCC000001": ("192.168.1.21", 0, 0)})
    assert plugin_mod.Plugin._webhook_source_ok(host, dev, "192.168.1.21") is True


def test_the_check_can_be_switched_off_for_nat(plugin_mod):
    assert plugin_mod.Plugin._webhook_source_ok(_sender_host(check=False),
                                                WASHER, CHARGER_IP) is True


def test_a_refusal_is_reported_once_and_cleans_the_sender(plugin_mod, monkeypatch):
    started, logged = [], []
    monkeypatch.setattr(plugin_mod, "log", lambda m, level="INFO": logged.append((level, m)))
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda target=None, args=(), daemon=None:
                            types.SimpleNamespace(start=lambda: started.append(args)))
    host = types.SimpleNamespace(_foreign_warned=set(), _webhook_repairs={},
                                 _remove_hooks_for=lambda *a: None)
    for _ in range(3):
        plugin_mod.Plugin._refuse_foreign_webhook(host, WASHER, CHARGER_IP)
    assert len([m for lv, m in logged if lv == "WARNING"]) == 1
    assert started == [(CHARGER_IP, WASHER.id)], "one clean-up, rate limited"


# ── input event names ────────────────────────────────────────────────────────

REAL_INPUT_EVENTS = {"input.button_push", "input.button_doublepush",
                     "input.button_longpush", "input.button_triplepush",
                     "input.toggle_on", "input.toggle_off"}


def _wanted_host(plugin_mod, comps):
    host = types.SimpleNamespace(server_ip=SERVER, webhook_port=PORT,
                                 _device_components=lambda ip: comps)
    host._hook_base = plugin_mod.Plugin._hook_base.__get__(host)
    host._pref_int = plugin_mod.Plugin._pref_int
    return host


@pytest.mark.parametrize("type_id", ["shellyRelay", "shellyUni", "shellyI4"])
def test_every_input_event_name_is_one_shelly_accepts(plugin_mod, type_id):
    """The plugin asked for input.single_push / on / off, which do not exist,
    so no input ever pushed an event. Checked live with Webhook.ListAllSupported
    on a Mini Gen 4."""
    comps = {f"input:{i}" for i in range(4)} | {"switch:0"}
    wanted, verified = plugin_mod.Plugin._wanted_webhooks(
        _wanted_host(plugin_mod, comps), FakeDev(1, "d", type_id=type_id), "192.168.1.5")
    events = {e for e, _u, _c in wanted if e.startswith("input.")}
    assert events and events <= REAL_INPUT_EVENTS
    assert verified is True


def test_a_plug_without_inputs_is_not_asked_for_input_hooks(plugin_mod):
    comps = {"switch:0", "pluguk_ui", "sys"}
    wanted, _v = plugin_mod.Plugin._wanted_webhooks(
        _wanted_host(plugin_mod, comps), FakeDev(1, "Plug"), "192.168.1.5")
    assert [e for e, _u, _c in wanted] == ["switch.on", "switch.off"]


def test_the_i4_stays_within_the_20_hook_limit(plugin_mod):
    comps = {f"input:{i}" for i in range(4)}
    wanted, _v = plugin_mod.Plugin._wanted_webhooks(
        _wanted_host(plugin_mod, comps), FakeDev(1, "i4", type_id="shellyI4"), "192.168.1.5")
    assert len(wanted) <= 20


def test_unknown_components_keep_the_input_hooks(plugin_mod):
    wanted, verified = plugin_mod.Plugin._wanted_webhooks(
        _wanted_host(plugin_mod, None), FakeDev(1, "Relay"), "192.168.1.5")
    assert any(e.startswith("input.") for e, _u, _c in wanted)
    assert verified is False


# ── restarts only on address changes ─────────────────────────────────────────

def test_only_an_address_change_restarts_the_device(plugin_mod):
    host = types.SimpleNamespace(RESTART_PROPS=plugin_mod.Plugin.RESTART_PROPS)
    a = FakeDev(1, "d", ip="192.168.1.5")
    b = FakeDev(1, "d", ip="192.168.1.5", props={"seenDynamicKeys": "wifiRssi:n",
                                                  "mac_address": "AABBCC000001"})
    c = FakeDev(1, "d", ip="192.168.1.6")
    change = plugin_mod.Plugin.didDeviceCommPropertyChange
    assert change(host, a, b) is False, "a learned MAC or field must not restart it"
    assert change(host, a, c) is True


# ── midnight reset ───────────────────────────────────────────────────────────

class _MidnightHost:
    def __init__(self, plugin_mod, total_wh, target_ip="192.168.1.5"):
        self.energy_data   = {}
        self._energy_lock  = threading.RLock()
        self.logger        = types.SimpleNamespace(debug=lambda *a, **k: None)
        self.log_activity  = False
        self._log_activity = plugin_mod.Plugin._log_activity.__get__(self)
        self._total, self._target = total_wh, target_ip
        self.saved = 0
        self._midnight_reset = plugin_mod.Plugin._midnight_reset.__get__(self)

    def _target_ip(self, dev):
        return self._target

    def _pref_int(self, props, key, default=0):
        return int(props.get(key, default))

    def _rget(self, url):
        return FakeResp({"aenergy": {"total": self._total}})

    def _get_total_wh(self, blob, key):
        return blob.get(key)

    def _save_energy_data(self):
        self.saved += 1


@pytest.fixture
def one_plug(plugin_mod, monkeypatch):
    dev = FakeDev(7, "Plug", ip="192.168.1.5", props={"has_pm": True},
                  states={"deviceOnline": True})
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [dev], raising=False)
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    return dev


def test_a_zero_reading_at_midnight_is_not_taken_as_the_baseline(plugin_mod, one_plug):
    """The phantom-zero shape skipped the two-strike rule on this path."""
    host = _MidnightHost(plugin_mod, total_wh=0.0)
    host.energy_data["7"] = {"day_baseline_wh": 80000.0, "day_date": "2026-09-25",
                             "month_baseline_wh": 70000.0, "month_date": "2026-09"}
    host._midnight_reset("2026-09-26")
    assert host.energy_data["7"]["day_baseline_wh"] == 80000.0
    assert "history" not in host.energy_data["7"], "nothing banked from a 0"


def test_a_device_that_fails_the_identity_check_is_left_alone(plugin_mod, one_plug):
    host = _MidnightHost(plugin_mod, total_wh=90000.0, target_ip=None)
    host.energy_data["7"] = {"day_baseline_wh": 80000.0, "day_date": "2026-09-25"}
    host._midnight_reset("2026-09-26")
    assert host.energy_data["7"]["day_baseline_wh"] == 80000.0


def test_a_device_already_rolled_over_is_not_banked_twice(plugin_mod, one_plug):
    host = _MidnightHost(plugin_mod, total_wh=80100.0)
    host.energy_data["7"] = {"day_baseline_wh": 80050.0, "day_date": "2026-09-26",
                             "history": [{"date": "2026-09-25", "kwh": 1.0}]}
    host._midnight_reset("2026-09-26")
    assert len(host.energy_data["7"]["history"]) == 1


def test_the_date_is_saved_with_the_baselines(plugin_mod, one_plug):
    host = _MidnightHost(plugin_mod, total_wh=81000.0)
    host.energy_data["7"] = {"day_baseline_wh": 80000.0, "day_date": "2026-09-25"}
    host._midnight_reset("2026-09-26")
    assert host.energy_data["__meta__"]["last_date"] == "2026-09-26"
    assert host.saved == 1


# ── undoing a reset that was a glitch ────────────────────────────────────────

def _calc_host():
    return types.SimpleNamespace(energy_data={}, _energy_lock=threading.RLock())


def test_a_reset_is_undone_when_the_counter_comes_back(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    host = _calc_host()
    calc = plugin_mod.Plugin._calc_energy
    calc(host, 7, 80000.0)                       # baseline for today
    calc(host, 7, 80500.0)                       # 0.5 kWh used
    calc(host, 7, 0.0)                           # first strike
    calc(host, 7, 0.0)                           # second strike: committed
    today, _month = calc(host, 7, 80600.0)       # the real counter again
    assert abs(today - 0.6) < 1e-9, "baseline restored, not 80.6 kWh 'today'"


def test_a_genuine_reset_stays_reset(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    host = _calc_host()
    calc = plugin_mod.Plugin._calc_energy
    calc(host, 7, 80000.0)
    calc(host, 7, 0.0)
    calc(host, 7, 5.0)
    today, _month = calc(host, 7, 250.0)
    assert abs(today - 0.245) < 1e-9, "baseline is the confirmed 5 Wh reading"


# ── typed dynamic states ─────────────────────────────────────────────────────

def test_seen_keys_round_trip_with_types(plugin_mod):
    seen = plugin_mod.parse_seen_keys("wifiRssi:n,sysMac:s,cloudConnected:b,oldKey")
    assert seen == {"wifiRssi": "n", "sysMac": "s", "cloudConnected": "b", "oldKey": None}
    assert plugin_mod.parse_seen_keys(plugin_mod.format_seen_keys(seen)) == seen


def test_a_new_field_is_declared_with_the_type_it_arrived_with(plugin_mod):
    """The type came from the CURRENT value, which is None for a new key, so
    every new field became a String and SQL Logger grew a second column."""
    dev = FakeDev(1, "Plug", props={"seenDynamicKeys": "wifiRssi:n,sysRestartRequired:b"})
    made = []
    host = types.SimpleNamespace(
        _is_valid_state_id=lambda k: True,
        getDeviceStateDictForBoolTrueFalseType=lambda k, a, b: made.append((k, "b")) or {"Key": k},
        getDeviceStateDictForNumberType=lambda k, a, b: made.append((k, "n")) or {"Key": k},
        getDeviceStateDictForStringType=lambda k, a, b: made.append((k, "s")) or {"Key": k})
    orig = plugin_mod.indigo.PluginBase
    plugin_mod.indigo.PluginBase = types.SimpleNamespace(getDeviceStateList=lambda self, d: [])
    try:
        plugin_mod.Plugin.getDeviceStateList(host, dev)
    finally:
        plugin_mod.indigo.PluginBase = orig
    assert sorted(made) == [("sysRestartRequired", "b"), ("wifiRssi", "n")]


# ── model table ──────────────────────────────────────────────────────────────

def test_build_suffixes_find_the_base_model(plugin_mod):
    assert plugin_mod.app_info_for("S2PMG4ZB") == plugin_mod.APP_INFO["S2PMG4"]
    assert plugin_mod.app_info_for("Pro1PMProAddon") == plugin_mod.APP_INFO["Pro1PM"]
    assert plugin_mod.app_info_for("NothingLikeIt") is None


def test_the_mini_gen4_in_this_house_is_listed(plugin_mod):
    assert plugin_mod.APP_INFO["Mini1G4"][2] == "shellyRelay"


def test_no_invented_plug_uk_gen4(plugin_mod):
    assert "PlugUK" not in plugin_mod.APP_INFO


# ── HTTPS (enhanced security) ────────────────────────────────────────────────

def test_a_redirect_to_https_is_followed_and_remembered(plugin_mod, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None, auth=None, allow_redirects=True, verify=True):
        calls.append((url, verify))
        if url.startswith("http://"):
            return FakeResp(status=308, headers={"Location": url.replace("http://", "https://")})
        return FakeResp({"ok": True})

    monkeypatch.setattr(plugin_mod.requests, "get", fake_get)
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    host = types.SimpleNamespace(timeout=3, shelly_user="", shelly_pass="", _https_hosts=set())
    r1 = plugin_mod.Plugin._rget(host, "http://192.168.1.5/rpc/Shelly.GetStatus")
    r2 = plugin_mod.Plugin._rget(host, "http://192.168.1.5/rpc/Shelly.GetStatus")
    assert r1.json() == {"ok": True} and r2.json() == {"ok": True}
    assert calls == [("http://192.168.1.5/rpc/Shelly.GetStatus", True),
                     ("https://192.168.1.5/rpc/Shelly.GetStatus", False),
                     ("https://192.168.1.5/rpc/Shelly.GetStatus", False)]


def test_plain_http_devices_are_untouched(plugin_mod, monkeypatch):
    calls = []
    monkeypatch.setattr(plugin_mod.requests, "get",
                        lambda url, **k: calls.append(url) or FakeResp({"ok": 1}))
    host = types.SimpleNamespace(timeout=3, shelly_user="", shelly_pass="", _https_hosts=set())
    plugin_mod.Plugin._rget(host, "http://192.168.1.5/rpc/Switch.GetStatus?id=0")
    assert calls == ["http://192.168.1.5/rpc/Switch.GetStatus?id=0"]
    assert host._https_hosts == set()

