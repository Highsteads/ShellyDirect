#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v320_features.py
# Description: Tests for the v3.20.0 features: the electricity price on the
#              plug LED rings, switch settings held on the device, firmware
#              updates from Indigo, grouped offline reporting, who switched a
#              relay, one retry for a lost command, and BLU sensors read
#              through a gateway's BTHome component.
# Author:      CliveS & Claude Opus 5.5
# Date:        26-09-2026
# Version:     1.0

from __future__ import annotations

import json
import threading
import types
from datetime import datetime, timezone

import pytest


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", ip="192.168.1.5",
                 props=None, states=None, enabled=True):
        self.id, self.name, self.deviceTypeId = dev_id, name, type_id
        self.enabled = enabled
        self.configured = True
        self.pluginProps = {"ip_address": ip, "channel_id": "0"}
        self.pluginProps.update(props or {})
        self.states = dict(states or {})
        self.written = []

    def updateStatesOnServer(self, kv):
        for item in kv:
            self.states[item["key"]] = item["value"]
        self.written += kv

    def updateStateOnServer(self, key, value, **_k):
        self.states[key] = value
        self.written.append({"key": key, "value": value})

    def replacePluginPropsOnServer(self, props):
        self.pluginProps = dict(props)


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._p, self.status_code, self.headers = payload or {}, status, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._p


class _Log:
    def __init__(self):
        self.lines = []

    def __call__(self, msg, level="INFO"):
        self.lines.append((level, str(msg)))


def _logger():
    return types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None,
                                 warning=lambda *a, **k: None, error=lambda *a, **k: None)


def _plain_english(text):
    assert text.isascii(), text
    assert "|" not in text and "=" not in text, text


# ── words ────────────────────────────────────────────────────────────────────

def test_counts_and_lists_read_as_english(plugin_mod):
    assert plugin_mod.count_words(1, "device") == "one device"
    assert plugin_mod.count_words(4, "device") == "four devices"
    assert plugin_mod.count_words(23, "device") == "23 devices"
    assert plugin_mod.join_names(["a"]) == "a"
    assert plugin_mod.join_names(["a", "b"]) == "a and b"
    assert plugin_mod.join_names(["a", "b", "c"]) == "a, b and c"


# ── who switched it ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("source,tag,expect", [
    ("HTTP_in", "indigo", "Indigo"),
    ("HTTP_in", None, "another app on the network"),
    ("button", None, "the button on the device"),
    ("SHC", None, "the Shelly app"),
    ("init", None, "the device starting up"),
    ("brand_new_source", None, '"brand_new_source"'),
    ("", None, ""),
])
def test_switch_source_in_words(plugin_mod, source, tag, expect):
    assert plugin_mod.switch_source_label(source, tag) == expect


def _relay_host(plugin_mod, payload):
    host = types.SimpleNamespace(
        logger=_logger(), log_activity=False, _switch_changed={}, fired=[],
        last_polled={}, fail_count={},
        _target_ip=lambda dev: dev.pluginProps["ip_address"],
        _pref_int=plugin_mod.Plugin._pref_int,
        _rget=lambda url, params=None, timeout=None: FakeResp(payload),
        _get_total_wh=plugin_mod.Plugin._get_total_wh,
        _calc_energy=lambda dev_id, wh: (0.0, 0.0),
        _check_power_alert=lambda dev, w: None,
        _mirror_states=lambda dev, m: None,
        _capture_unhandled_fields=lambda dev, data, extra_handled=None: None,
        _mark_online=lambda dev: None,
    )
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    host._fire_trigger = lambda t, d, p=None: host.fired.append((t, d, p))
    host._apply_relay_status = plugin_mod.Plugin._apply_relay_status.__get__(host)
    host._poll_failed = lambda d, r="": (_ for _ in ()).throw(AssertionError(r))
    return host


def test_a_button_press_fires_switched_outside_indigo(plugin_mod):
    dev = FakeDev(1, "Lamp", props={"has_pm": False}, states={"onOffState": False})
    host = _relay_host(plugin_mod, {"output": True, "source": "button"})
    plugin_mod.Plugin._poll_relay(host, dev)
    assert dev.states["lastChangedBy"] == "the button on the device"
    assert host.fired == [("switchedOutsideIndigo", 1, {"who": "the button on the device"})]


def test_indigos_own_command_fires_nothing(plugin_mod):
    dev = FakeDev(1, "Lamp", props={"has_pm": False}, states={"onOffState": False})
    host = _relay_host(plugin_mod, {"output": True, "source": "HTTP_in", "tag": "indigo"})
    plugin_mod.Plugin._poll_relay(host, dev)
    assert dev.states["lastChangedBy"] == "Indigo"
    assert host.fired == []


def test_a_webhook_already_updated_state_still_counts_as_a_move(plugin_mod):
    """The webhook writes onOffState first, so the poll sees no difference;
    the flag the webhook leaves is what says the switch moved."""
    dev = FakeDev(1, "Lamp", props={"has_pm": False}, states={"onOffState": True})
    host = _relay_host(plugin_mod, {"output": True, "source": "SHC"})
    host._switch_changed[1] = True
    plugin_mod.Plugin._poll_relay(host, dev)
    assert host.fired and host.fired[0][2]["who"] == "the Shelly app"


def test_who_is_written_only_when_it_changes(plugin_mod):
    dev = FakeDev(1, "Lamp", props={"has_pm": False},
                  states={"onOffState": True, "lastChangedBy": "Indigo"})
    host = _relay_host(plugin_mod, {"output": True, "source": "HTTP_in", "tag": "indigo"})
    plugin_mod.Plugin._poll_relay(host, dev)
    assert not any(k["key"] == "lastChangedBy" for k in dev.written)


# ── one retry for a lost command ─────────────────────────────────────────────

def test_a_lost_command_is_sent_once_more(plugin_mod):
    calls = []

    def _rget(url, params=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise plugin_mod.requests.exceptions.ConnectionError("no route")
        return FakeResp({"was_on": False})

    host = types.SimpleNamespace(_rget=_rget, logger=_logger(), COMMAND_RETRY_DELAY=0)
    resp = plugin_mod.Plugin._rcommand(host, "http://192.168.1.5/rpc/Switch.Set", {"id": 0})
    assert resp.json() == {"was_on": False} and len(calls) == 2


def test_a_command_that_fails_twice_still_fails(plugin_mod):
    def _rget(url, params=None, timeout=None):
        raise plugin_mod.requests.exceptions.ConnectionError("no route")
    host = types.SimpleNamespace(_rget=_rget, logger=_logger(), COMMAND_RETRY_DELAY=0)
    with pytest.raises(plugin_mod.requests.exceptions.ConnectionError):
        plugin_mod.Plugin._rcommand(host, "http://x/rpc/Switch.Set")


# ── grouped offline reporting ────────────────────────────────────────────────

def _presence_host(plugin_mod, monkeypatch):
    logged = _Log()
    monkeypatch.setattr(plugin_mod, "log", logged)
    host = types.SimpleNamespace(_offline_batch=[], _online_batch=[], fired=[],
                                 OUTAGE_WINDOW=180, OUTAGE_MIN=3, logger=_logger(),
                                 log_activity=False)
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    host._fire_trigger = lambda t, d, p=None: host.fired.append(t)
    host._note_back_online = plugin_mod.Plugin._note_back_online.__get__(host)
    return host, logged


def test_several_devices_dropping_together_make_one_line(plugin_mod, monkeypatch):
    host, logged = _presence_host(plugin_mod, monkeypatch)
    host._offline_batch = [(1000, n, "no route") for n in ("Sonos Left", "Sonos Right", "Twigs", "HomePod")]
    plugin_mod.Plugin._flush_presence(host, 1000 + 181)
    warnings = [m for lv, m in logged.lines if lv == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].startswith("Four Shelly devices stopped answering")
    assert "Sonos Left, Sonos Right, Twigs and HomePod" in warnings[0]
    _plain_english(warnings[0])
    assert host.fired == ["manyDevicesOffline"]


def test_one_or_two_devices_are_reported_one_by_one(plugin_mod, monkeypatch):
    host, logged = _presence_host(plugin_mod, monkeypatch)
    host._offline_batch = [(1000, "Twigs", "no route to 192.168.1.5")]
    plugin_mod.Plugin._flush_presence(host, 1000 + 60)
    assert logged.lines == [], "held back until the window has passed"
    plugin_mod.Plugin._flush_presence(host, 1000 + 181)
    assert logged.lines == [("WARNING", "[Twigs] offline - no route to 192.168.1.5")]


def test_a_short_drop_is_one_quiet_line_not_two(plugin_mod, monkeypatch):
    host, logged = _presence_host(plugin_mod, monkeypatch)
    host._offline_batch = [(1000, "Twigs", "no route")]
    host._note_back_online("Twigs")
    plugin_mod.Plugin._flush_presence(host, 5000)
    assert logged.lines == [] and host._online_batch == []


# ── switch settings held on the device ───────────────────────────────────────

def test_only_what_indigo_sets_is_managed(plugin_mod):
    assert plugin_mod.wanted_switch_config({"manage_switch_settings": False,
                                            "auto_off_minutes": "90"}) == {}
    want = plugin_mod.wanted_switch_config({"manage_switch_settings": True,
                                            "auto_off_minutes": "90",
                                            "power_limit_w": "2500",
                                            "current_limit_a": "",
                                            "initial_state": "off"})
    assert want == {"auto_off": True, "auto_off_delay": 5400.0,
                    "power_limit": 2500, "initial_state": "off"}


def test_only_differences_are_sent(plugin_mod):
    current = {"auto_off": True, "auto_off_delay": 5400.0, "power_limit": 3000,
               "initial_state": "off"}
    want = {"auto_off": True, "auto_off_delay": 5400.0, "power_limit": 2500,
            "initial_state": "off"}
    assert plugin_mod.switch_config_changes(current, want) == {"power_limit": 2500}


def test_settings_are_described_in_words(plugin_mod):
    text = plugin_mod.describe_switch_config({"auto_off": True, "auto_off_delay": 5400.0,
                                              "power_limit": 2500, "initial_state": "off"})
    assert text == ("turn itself off 90 minutes after being turned on, cut the power "
                    "above 2500 W and stay off after a power cut")
    _plain_english(text)


def test_apply_sends_one_setconfig_with_the_changes(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    sent = []

    def _rget(url, params=None, timeout=None):
        if "GetConfig" in url:
            return FakeResp({"auto_off": False, "auto_off_delay": 60.0, "power_limit": 3000})
        sent.append(json.loads(params["config"]))
        return FakeResp({"restart_required": False})

    dev = FakeDev(1, "Fire", props={"manage_switch_settings": True, "auto_off_minutes": "120"})
    host = types.SimpleNamespace(_rget=_rget, _target_ip=lambda d: "192.168.1.5",
                                 _pref_int=plugin_mod.Plugin._pref_int)
    changes = plugin_mod.Plugin._apply_switch_settings(host, dev)
    assert sent == [{"auto_off": True, "auto_off_delay": 7200.0}] and changes == sent[0]


# ── electricity price on the LED ring ────────────────────────────────────────

OCTOPUS_RATES = json.dumps([
    {"value_inc_vat": 24.35433, "valid_from": "2026-09-25T18:00:00Z", "valid_to": "2026-09-26T01:00:00Z"},
    {"value_inc_vat": 14.618415, "valid_from": "2026-09-26T01:00:00Z", "valid_to": "2026-09-26T04:00:00Z"},
    {"value_inc_vat": 34.099905, "valid_from": "2026-09-26T15:00:00Z", "valid_to": "2026-09-26T18:00:00Z"},
])


@pytest.mark.parametrize("when,band", [
    ("2026-09-26T02:30:00+00:00", "cheap"),
    ("2026-09-25T20:00:00+00:00", "standard"),
    ("2026-09-26T15:00:00+00:00", "peak"),     # on the minute the peak starts
])
def test_the_band_follows_the_rate_list(plugin_mod, when, band):
    spans = plugin_mod.parse_rate_spans(OCTOPUS_RATES)
    pence = plugin_mod.price_now(spans, datetime.fromisoformat(when))
    assert plugin_mod.price_band(pence, 20, 30) == band


def test_a_time_outside_the_list_has_no_price(plugin_mod):
    spans = plugin_mod.parse_rate_spans(OCTOPUS_RATES)
    assert plugin_mod.price_now(spans, datetime(2026, 9, 26, 10, tzinfo=timezone.utc)) is None
    assert plugin_mod.price_band(None, 20, 30) is None
    assert plugin_mod.parse_rate_spans("not json") == []


def _price_host(plugin_mod, devs, band_pence):
    host = types.SimpleNamespace(price_light_enabled=True, _price_band=None, _price_pence=None,
                                 _led_applied={}, logger=_logger(), log_activity=False,
                                 price_cheap_below=20.0, price_peak_above=30.0,
                                 shown=[], restored=[])
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    host._current_price = lambda: (band_pence, "the rate list")
    host._show_price_band = lambda dev, band: host.shown.append((dev.name, band))
    host._restore_led = lambda dev: host.restored.append(dev.name)
    return host


def test_opted_in_plugs_show_the_band_and_opted_out_ones_are_restored(plugin_mod, monkeypatch):
    lamp = FakeDev(1, "Lamp", props={"price_light": True}, states={"deviceOnline": True})
    tv = FakeDev(2, "TV", props={"price_light": False, "led_original": "{}x"})
    plain = FakeDev(3, "Plain", props={})
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [lamp, tv, plain],
                        raising=False)
    host = _price_host(plugin_mod, [lamp, tv, plain], 14.6)
    plugin_mod.Plugin._update_price_light(host)
    assert host.shown == [("Lamp", "cheap")] and host.restored == ["TV"]


def test_the_ring_is_saved_then_coloured(plugin_mod):
    sent, saved = [], {}
    dev = FakeDev(1, "Lamp", props={"price_light": True})

    def _rget(url, params=None, timeout=None):
        if url.endswith("GetConfig"):
            return FakeResp({"leds": {"mode": "switch", "colors": {"switch:0": {
                "on": {"rgb": [0, 100, 0], "brightness": 50}}}}})
        return FakeResp({"restart_required": False})

    host = types.SimpleNamespace(_rget=_rget, _target_ip=lambda d: "192.168.1.5",
                                 _led_component=lambda d: "pluguk_ui", _led_applied={},
                                 _props_lock=threading.RLock(), logger=_logger())
    host._led_set = lambda ip, comp, leds: sent.append((comp, leds)) or FakeResp({})
    plugin_mod.Plugin._show_price_band(host, dev, "peak")
    saved = json.loads(dev.pluginProps["led_original"])
    assert saved["colors"]["switch:0"]["on"]["rgb"] == [0, 100, 0]
    comp, leds = sent[0]
    assert comp == "pluguk_ui"
    assert leds["colors"]["switch:0"]["on"]["rgb"] == plugin_mod.PRICE_COLOURS["peak"]
    assert leds["colors"]["switch:0"]["off"]["brightness"] < leds["colors"]["switch:0"]["on"]["brightness"]
    assert host._led_applied[1] == "peak"


# ── firmware ─────────────────────────────────────────────────────────────────

def test_a_held_device_is_never_updated(plugin_mod):
    host = types.SimpleNamespace(_target_ip=lambda d: (_ for _ in ()).throw(AssertionError))
    dev = FakeDev(1, "Indigo Mac Mini Plug", props={"hold_firmware": True})
    assert plugin_mod.Plugin._update_firmware(host, dev) == "Indigo Mac Mini Plug is held, so it was left alone"


def test_an_update_waits_for_the_new_version_and_puts_the_relay_back(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(plugin_mod, "log", _Log())
    state = {"ver": "2.0.0", "output": True, "updated": False, "set": []}

    def _rget(url, params=None, timeout=None):
        if "CheckForUpdate" in url:
            return FakeResp({"stable": {"version": "2.0.1"}})
        if "Shelly.Update" in url:
            state["updated"] = True
            state["output"] = False                    # the restart turned it off
            return FakeResp({})
        if "GetDeviceInfo" in url:
            return FakeResp({"ver": "2.0.1" if state["updated"] else "2.0.0"})
        if "Shelly.GetStatus" in url:
            return FakeResp({"switch:0": {"output": state["output"]}})
        return FakeResp({})

    host = types.SimpleNamespace(_rget=_rget, _target_ip=lambda d: "192.168.1.5",
                                 FIRMWARE_WAIT=60)
    host._switch_outputs = plugin_mod.Plugin._switch_outputs.__get__(host)
    host._switch_set = lambda ip, sid, on, name="": state["set"].append((sid, on)) or True
    msg = plugin_mod.Plugin._update_firmware(host, FakeDev(1, "NAS Plug"))
    assert msg == "NAS Plug is now on 2.0.1"
    assert state["set"] == [(0, True)], "switched back on after the restart"


def test_firmware_is_offered_once_per_physical_shelly(plugin_mod, monkeypatch):
    ch1 = FakeDev(1, "2PM Ch1", ip="192.168.1.50")
    ch2 = FakeDev(2, "2PM Ch2", ip="192.168.1.50", props={"channel_id": "1"})
    blu = FakeDev(3, "Hall Button", type_id="shellyBluButton", ip="192.168.1.50")
    sensor = FakeDev(4, "Porch", type_id="shellyBluSensor", ip="192.168.1.50")
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [ch1, ch2, blu, sensor],
                        raising=False)
    names = [d.name for d in plugin_mod.Plugin._firmware_candidates(types.SimpleNamespace())]
    assert names == ["2PM Ch1"]


# ── BLU sensors through BTHome ───────────────────────────────────────────────

GATEWAY_COMPONENTS = [
    {"key": "bthomedevice:200", "status": {"id": 200, "rssi": -71, "battery": 98,
                                           "last_updated_ts": 1790460000},
     "config": {"id": 200, "addr": "7c:c6:b6:00:00:01", "name": "Porch H&T"}},
    {"key": "bthomesensor:201", "status": {"id": 201, "value": 98},
     "config": {"id": 201, "addr": "7c:c6:b6:00:00:01", "obj_id": 1, "idx": 0}},
    {"key": "bthomesensor:202", "status": {"id": 202, "value": 12.4},
     "config": {"id": 202, "addr": "7c:c6:b6:00:00:01", "obj_id": 69, "idx": 0}},
    {"key": "bthomesensor:203", "status": {"id": 203, "value": 81},
     "config": {"id": 203, "addr": "7c:c6:b6:00:00:01", "obj_id": 46, "idx": 0}},
    {"key": "bthomedevice:210", "status": {"id": 210}, "config": {"id": 210, "addr": "aa:bb:cc:00:00:02"}},
    {"key": "bthomesensor:211", "status": {"id": 211, "value": True},
     "config": {"id": 211, "addr": "aa:bb:cc:00:00:02", "obj_id": 45, "idx": 0}},
]
OBJ_NAMES = {1: "battery", 69: "temperature", 46: "humidity", 45: "window"}


def test_readings_are_matched_to_their_device_by_address(plugin_mod):
    host = types.SimpleNamespace()
    status, readings = plugin_mod.Plugin._blu_sensor_readings(host, GATEWAY_COMPONENTS, 200)
    assert status["rssi"] == -71
    assert sorted(o for o, _v, _c in readings) == [1, 46, 69]
    status, readings = plugin_mod.Plugin._blu_sensor_readings(host, GATEWAY_COMPONENTS, 999)
    assert status is None and readings == []


def _sensor_host(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    host = types.SimpleNamespace(last_polled={}, pluginPrefs={}, marked=[],
                                 BLU_STALE_HOURS_DEFAULT=12,
                                 _pref_int=plugin_mod.Plugin._pref_int,
                                 _gateway_components=lambda ip: GATEWAY_COMPONENTS,
                                 _obj_name_map=lambda ip, ids: OBJ_NAMES,
                                 _capture_unhandled_fields=lambda *a, **k: None)
    host._blu_sensor_readings = plugin_mod.Plugin._blu_sensor_readings.__get__(host)
    host._mark_online = lambda d: host.marked.append("online")
    host._mark_offline = lambda d, r="": host.marked.append("offline")
    host._poll_failed = lambda d, r="": host.marked.append(("failed", r))
    return host


def test_an_h_and_t_sensor_reads_as_a_temperature(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod.time, "time", lambda: 1790460000 + 60)
    host = _sensor_host(plugin_mod, monkeypatch)
    dev = FakeDev(9, "Porch H&T", type_id="shellyBluSensor",
                  props={"bthome_id": "200", "display_kind": "value"})
    plugin_mod.Plugin._poll_blu_sensor(host, dev)
    assert dev.states["temperature"] == 12.4 and dev.states["sensorValue"] == 12.4
    assert dev.states["humidity"] == 81.0 and dev.states["battery"] == 98
    assert dev.states["rssi"] == -71
    assert "onOffState" not in dev.states
    assert host.marked == ["online"]


def test_a_door_sensor_reads_as_open_or_closed(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod.time, "time", lambda: 1790460000)
    host = _sensor_host(plugin_mod, monkeypatch)
    dev = FakeDev(10, "Shed Door", type_id="shellyBluSensor",
                  props={"bthome_id": "210", "display_kind": "onoff"})
    plugin_mod.Plugin._poll_blu_sensor(host, dev)
    assert dev.states["onOffState"] is True
    assert "sensorValue" not in dev.states


def test_a_silent_sensor_goes_offline(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod.time, "time", lambda: 1790460000 + 13 * 3600)
    host = _sensor_host(plugin_mod, monkeypatch)
    dev = FakeDev(9, "Porch H&T", type_id="shellyBluSensor", props={"bthome_id": "200"})
    plugin_mod.Plugin._poll_blu_sensor(host, dev)
    assert host.marked == ["offline"]


def test_an_unpaired_id_says_how_to_find_the_right_one(plugin_mod, monkeypatch):
    logged = _Log()
    host = _sensor_host(plugin_mod, monkeypatch)
    monkeypatch.setattr(plugin_mod, "log", logged)
    dev = FakeDev(9, "Porch", type_id="shellyBluSensor", props={"bthome_id": "999"})
    plugin_mod.Plugin._poll_blu_sensor(host, dev)
    assert "Show BLU Devices on Gateways" in logged.lines[0][1]


# ── a gateway child never claims its gateway's address ───────────────────────

def test_a_blu_sensor_does_not_clash_with_its_gateway(plugin_mod, monkeypatch):
    gw = FakeDev(1, "Garage Mini", ip="192.168.1.26", props={"mac_address": "AABBCC000001"})
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [gw], raising=False)
    clash = plugin_mod.Plugin._address_clash(types.SimpleNamespace(), "192.168.1.26",
                                             {"channel_id": "0"}, "shellyBluSensor", 99)
    assert clash == ""


def test_a_blu_sensor_is_never_a_duplicate_of_its_gateway(plugin_mod, monkeypatch):
    gw = FakeDev(1, "Garage Mini", ip="192.168.1.26", props={"mac_address": "AABBCC000001"})
    sensor = FakeDev(2, "Porch", type_id="shellyBluSensor", ip="192.168.1.26")
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [gw, sensor],
                        raising=False)
    dup_ids, _c = plugin_mod.Plugin._duplicate_device_ids(types.SimpleNamespace())
    assert dup_ids == set()


def test_discovery_never_mistakes_a_sensor_for_its_gateway(plugin_mod, monkeypatch):
    sensor = FakeDev(2, "Porch", type_id="shellyBluSensor", ip="192.168.1.26",
                     props={"mac_address": "AABBCC000001"})
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [sensor],
                        raising=False)
    host = types.SimpleNamespace()
    assert plugin_mod.Plugin._existing_device_macs(host) == {}
    assert plugin_mod.Plugin._existing_device_ips(host) == set()


# ── v4.1.0: price light on every plug at once ────────────────────────────────

def test_the_menu_ticks_every_plug_with_a_ring_and_says_so(plugin_mod, monkeypatch):
    logged = _Log()
    monkeypatch.setattr(plugin_mod, "log", logged)
    lamp = FakeDev(1, "Lamp")
    tv = FakeDev(2, "TV")
    garage = FakeDev(3, "Garage")
    already = FakeDev(4, "Kettle", props={"price_light": True})
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter",
                        lambda *a, **k: [lamp, tv, garage, already], raising=False)
    host = types.SimpleNamespace(price_light_enabled=True, _price_checked=99.0,
                                 _props_lock=threading.RLock(),
                                 _device_components=lambda ip: {"switch:0"} if ip == "192.168.1.26"
                                 else {"switch:0", "pluguk_ui"})
    garage.pluginProps["ip_address"] = "192.168.1.26"
    plugin_mod.Plugin._set_price_light_all(host, True)
    assert lamp.pluginProps["price_light"] is True and tv.pluginProps["price_light"] is True
    assert "price_light" not in garage.pluginProps
    assert logged.lines == [("INFO", "The LED ring now shows the electricity price on two "
                                     "plugs: Lamp and TV. Garage has no LED ring.")]
    _plain_english(logged.lines[0][1])
    assert host._price_checked == 0.0


def test_a_plug_that_cannot_be_asked_is_ticked_not_written_off(plugin_mod, monkeypatch):
    logged = _Log()
    monkeypatch.setattr(plugin_mod, "log", logged)
    washer = FakeDev(5, "Washer")
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [washer], raising=False)
    host = types.SimpleNamespace(price_light_enabled=True, _price_checked=99.0,
                                 _props_lock=threading.RLock(), _device_components=lambda ip: None)
    plugin_mod.Plugin._set_price_light_all(host, True)
    assert washer.pluginProps["price_light"] is True
    assert "Washer could not be reached, so it shows the price when back if it has a ring." in logged.lines[0][1]


def test_none_in_the_source_menus_means_no_source(plugin_mod):
    """Indigo drops an empty-valued menu option, so "- none -" is the value
    "none" and must read as no source at all."""
    host = types.SimpleNamespace()
    plugin_mod.Plugin._load_price_prefs(host, {"price_light_enabled": True,
                                               "price_rates_var": "none",
                                               "price_rates_var2": "778257677",
                                               "price_now_var": "none"})
    assert host.price_rates_vars == ["", "778257677"] and host.price_now_var == ""
    menu = plugin_mod.Plugin.getVariableChoices(types.SimpleNamespace())
    assert menu[0] == ("none", "- none -")


def test_query_json_has_no_spaces(plugin_mod):
    """A space reaches Shelly as "+" and the argument is refused."""
    assert plugin_mod.qjson({"leds": {"mode": "switch", "rgb": [100, 55, 0]}}) == \
        '{"leds":{"mode":"switch","rgb":[100,55,0]}}'


def test_no_query_argument_is_built_with_plain_json_dumps():
    """Every json.dumps left in plugin.py must be outside a query string: the
    websocket frame, the saved LED settings and the energy file."""
    import ast
    import io
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "ShellyDirect.indigoPlugin" / "Contents" / "Server Plugin" / "plugin.py"
    tree = ast.parse(io.open(src, encoding="utf-8").read())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for val in node.values:
                if (isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute)
                        and val.func.attr == "dumps"):
                    offenders.append(val.lineno)
    assert offenders == [], f"json.dumps inside a params dict at lines {offenders}"
