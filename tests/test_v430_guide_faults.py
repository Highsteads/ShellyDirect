#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v430_guide_faults.py
# Description: Tests for the v4.3.0 fixes to the faults found while writing
#              the plain-English guide: sensor types given the native state
#              they report through (Supports* props), battery carried in the
#              sensor webhooks, Accept Replaced Shellys, and the High Power
#              Alert skipping a reading with no power figure.
# Author:      CliveS & Claude Opus 5.5
# Date:        27-09-2026
# Version:     1.0

from __future__ import annotations

import threading
import types
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SERVER_DIR = (Path(__file__).resolve().parent.parent
              / "ShellyDirect.indigoPlugin" / "Contents" / "Server Plugin")


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", ip="192.168.1.5",
                 props=None, states=None):
        self.id, self.name, self.deviceTypeId = dev_id, name, type_id
        self.enabled = self.configured = True
        self.pluginProps = {"ip_address": ip, "channel_id": "0"}
        self.pluginProps.update(props or {})
        self.states = dict(states or {})
        self.prop_writes = 0
        self.refreshed = 0

    def updateStatesOnServer(self, kv):
        for item in kv:
            self.states[item["key"]] = item["value"]

    def updateStateOnServer(self, key, value, **_k):
        self.states[key] = value

    def replacePluginPropsOnServer(self, props):
        self.pluginProps = dict(props)
        self.prop_writes += 1

    def stateListOrDisplayStateIdChanged(self):
        self.refreshed += 1


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._p, self.status_code = payload or {}, status

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


@pytest.fixture
def devices(plugin_mod, monkeypatch):
    """indigo.devices[id] answers from this dict."""
    table = {}

    def _get(_self, dev_id):
        return table[dev_id]
    monkeypatch.setattr(type(plugin_mod.indigo.devices), "__getitem__", _get)
    return table


# ── sensors report through a native state that exists ───────────────────────

@pytest.mark.parametrize("type_id, on, value", [
    ("shellyHT", False, True), ("shellyEM", False, True),
    ("shellySmoke", True, False), ("shellyFlood", True, False), ("shellyI4", True, False),
])
def test_each_sensor_type_gets_the_right_supports_props(plugin_mod, devices, type_id, on, value):
    dev = FakeDev(1, "Sensor", type_id=type_id)
    devices[1] = dev
    host = types.SimpleNamespace(_props_lock=threading.RLock(), logger=_logger())
    got = plugin_mod.Plugin._sensor_display(host, dev)
    assert got is dev and dev.prop_writes == 1
    assert dev.pluginProps["SupportsOnState"] is on
    assert dev.pluginProps["SupportsSensorValue"] is value
    assert dev.pluginProps["ip_address"] == "192.168.1.5", "the rest of the props survive"


def test_props_already_right_are_not_rewritten(plugin_mod, devices):
    dev = FakeDev(1, "Smoke", type_id="shellySmoke",
                  props={"SupportsOnState": "true", "SupportsSensorValue": "false"})
    host = types.SimpleNamespace(_props_lock=threading.RLock(), logger=_logger())
    plugin_mod.Plugin._sensor_display(host, dev)
    assert dev.prop_writes == 0


def test_other_types_are_left_alone(plugin_mod, devices):
    for type_id in ("shellyRelay", "shellyBluSensor", "shellyBluButton"):
        dev = FakeDev(1, "X", type_id=type_id)
        plugin_mod.Plugin._sensor_display(types.SimpleNamespace(), dev)
        assert dev.prop_writes == 0, type_id


def test_start_refreshes_the_state_list_of_the_refetched_device(plugin_mod, monkeypatch):
    """The Supports* write happens first, and the state-list refresh lands on
    the re-fetched device, which is what brings the native state into being."""
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda target=None, args=(), daemon=None: types.SimpleNamespace(start=lambda: None))
    old = FakeDev(1, "Smoke", type_id="shellySmoke", props={"mac_address": "AABBCC000001"})
    new = FakeDev(1, "Smoke", type_id="shellySmoke", props={"mac_address": "AABBCC000001"})
    host = types.SimpleNamespace(logger=_logger(), last_polled={}, last_seen={},
                                 _sensor_display=lambda d: new,
                                 _keep_churn_out_of_sql_logger=lambda d: None)
    plugin_mod.Plugin.deviceStartComm(host, old)
    assert new.refreshed == 1 and old.refreshed == 0


def _receiver(plugin_mod):
    r = types.SimpleNamespace(last_polled={}, logger=_logger(), log_activity=False,
                              _switch_changed={},
                              _fire_trigger=lambda *a, **k: None,
                              _mirror_states=lambda *a, **k: None,
                              _qp=plugin_mod.Plugin._qp,
                              _qp_int=plugin_mod.Plugin._qp_int,
                              _qp_float=plugin_mod.Plugin._qp_float)
    r._log_activity = plugin_mod.Plugin._log_activity.__get__(r)
    return r


def _query(url):
    return parse_qs(urlparse(url).query, keep_blank_values=True)


def test_a_flood_alarm_lands_on_onoffstate(plugin_mod):
    dev = FakeDev(2, "Utility Flood", type_id="shellyFlood")
    plugin_mod.Plugin._apply_webhook_event(
        _receiver(plugin_mod), dev, _query("/shellyEvent?devId=2&type=flood&flood=true&battery=87"))
    assert dev.states == {"onOffState": True, "batteryPct": 87}


def test_the_i4_poll_writes_input_1_to_onoffstate(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    answers = {0: True, 1: False, 2: True, 3: False}
    host = types.SimpleNamespace(
        last_polled={}, _target_ip=lambda d: "192.168.1.9",
        _rget=lambda url, params=None, timeout=None: FakeResp({"state": answers[int(url[-1])]}),
        _mirror_states=lambda *a, **k: None, _mark_online=lambda d: None,
        _poll_failed=lambda d, r="": (_ for _ in ()).throw(AssertionError(r)))
    dev = FakeDev(3, "Hall i4", type_id="shellyI4")
    plugin_mod.Plugin._poll_i4(host, dev)
    assert dev.states == {"onOffState": True, "input1": False, "input2": True, "input3": False}


def test_devices_xml_matches_the_native_kinds(plugin_mod):
    root = ET.parse(SERVER_DIR / "Devices.xml").getroot()
    for dev in root.iter("Device"):
        type_id = dev.get("id")
        states = {s.get("id") for s in dev.iter("State")}
        if dev.get("type") == "sensor":
            assert not states & {"sensorValue", "onOffState"}, type_id
        wanted = plugin_mod.sensor_supports_props(type_id)
        if wanted is None:
            continue
        fields = {f.get("id"): f for f in dev.iter("Field")}
        for key, val in wanted.items():
            assert fields[key].get("hidden") == "true", (type_id, key)
            assert fields[key].get("defaultValue") == ("true" if val else "false"), (type_id, key)
    flood = next(d for d in root.iter("Device") if d.get("id") == "shellyFlood")
    assert "temperature" not in {s.get("id") for s in flood.iter("State")}


# ── battery in the sensor webhooks ──────────────────────────────────────────

@pytest.mark.parametrize("type_id", ["shellyHT", "shellySmoke", "shellyFlood"])
def test_every_sensor_hook_carries_the_battery(plugin_mod, type_id):
    hooks = plugin_mod.sensor_hook_urls(type_id, "http://192.168.1.2:8178/shellyEvent?devId=7")
    assert len(hooks) == 2
    for _event, url in hooks:
        assert url.endswith('&battery=${status["devicepower:0"].battery.percent}')


def test_flood_hooks_ask_for_no_temperature(plugin_mod):
    for _event, url in plugin_mod.sensor_hook_urls("shellyFlood", "http://h/x?devId=7"):
        assert "tC=" not in url


def test_other_types_have_no_sensor_hooks(plugin_mod):
    assert plugin_mod.sensor_hook_urls("shellyRelay", "http://h/x?devId=7") == []


@pytest.mark.parametrize("type_id, extra", [
    ("shellyHT",    {"temperature": 21.5, "sensorValue": 21.5}),
    ("shellySmoke", {"onOffState": True}),
    ("shellyFlood", {"onOffState": True}),
])
def test_the_battery_the_device_fills_in_reaches_the_state(plugin_mod, type_id, extra):
    """What the Shelly sends once it has evaluated the tokens."""
    _event, url = plugin_mod.sensor_hook_urls(type_id, "http://h/shellyEvent?devId=7")[0]
    sent = url.replace("${ev.tC}", "21.5").replace(plugin_mod.BATTERY_TOKEN, "64")
    dev = FakeDev(7, "Sensor", type_id=type_id)
    plugin_mod.Plugin._apply_webhook_event(_receiver(plugin_mod), dev, _query(sent))
    assert dev.states["batteryPct"] == 64
    for key, val in extra.items():
        assert dev.states[key] == val


def test_a_token_the_device_could_not_evaluate_is_ignored(plugin_mod):
    _event, url = plugin_mod.sensor_hook_urls("shellySmoke", "http://h/shellyEvent?devId=7")[0]
    dev = FakeDev(7, "Smoke", type_id="shellySmoke")
    plugin_mod.Plugin._apply_webhook_event(_receiver(plugin_mod), dev, _query(url))
    assert dev.states == {"onOffState": True}


def _hook_host(monkeypatch, plugin_mod, hooks):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    calls = []

    def _rget(url, params=None, timeout=None):
        calls.append((url.rsplit("/", 1)[-1], params))
        if url.endswith("Webhook.List"):
            return FakeResp({"hooks": hooks})
        return FakeResp({})
    return types.SimpleNamespace(_rget=_rget, logger=_logger()), calls


def test_an_older_sensor_hook_is_brought_up_to_date(plugin_mod, monkeypatch):
    base = "http://192.168.1.2:8178/shellyEvent?devId=30"
    event, url = plugin_mod.sensor_hook_urls("shellySmoke", base)[0]
    host, calls = _hook_host(monkeypatch, plugin_mod,
                             [{"id": 4, "event": event, "urls": [f"{base}&type=smoke&alarm=true"]}])
    dev = FakeDev(30, "Smoke", type_id="shellySmoke")
    plugin_mod.Plugin._setup_sensor_webhook(host, "192.168.1.60", dev, url, event)
    assert [c[0] for c in calls] == ["Webhook.List", "Webhook.Update"]
    assert calls[1][1] == {"id": 4, "urls": plugin_mod.qjson([url])}


def test_a_current_sensor_hook_is_left_alone(plugin_mod, monkeypatch):
    base = "http://192.168.1.2:8178/shellyEvent?devId=30"
    event, url = plugin_mod.sensor_hook_urls("shellySmoke", base)[0]
    host, calls = _hook_host(monkeypatch, plugin_mod, [{"id": 4, "event": event, "urls": [url]}])
    plugin_mod.Plugin._setup_sensor_webhook(host, "192.168.1.60",
                                            FakeDev(30, "Smoke", type_id="shellySmoke"), url, event)
    assert [c[0] for c in calls] == ["Webhook.List"]


# ── Accept Replaced Shellys ─────────────────────────────────────────────────

def _accept_host(plugin_mod, monkeypatch, answering, advertised=None):
    logged = _Log()
    monkeypatch.setattr(plugin_mod, "log", logged)
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda target=None, args=(), daemon=None: types.SimpleNamespace(start=lambda: None))
    host = types.SimpleNamespace(
        _identity_bad={}, _identity_bad_ip={}, _identity_warned=set(), _mac_verified={}, last_polled={},
        _props_lock=threading.RLock(),
        _read_device_mac=lambda ip: answering,
        _mdns_lookup=lambda mac: (advertised or {}).get(mac),
        _configure_webhooks=lambda d: None)
    host._identity_cleared = plugin_mod.Plugin._identity_cleared.__get__(host)
    return host, logged


def test_a_replaced_shelly_is_accepted(plugin_mod, monkeypatch, devices):
    dev = FakeDev(1, "Garage Plug", props={"mac_address": "AABBCC000001"})
    devices[1] = dev
    host, logged = _accept_host(plugin_mod, monkeypatch, "aa:bb:cc:00:00:09")
    host._identity_bad[1] = "AABBCC000009"
    host._identity_warned.add((1, "192.168.1.5", "AABBCC000009"))
    plugin_mod.Plugin._menu_accept_replaced_body(host)
    assert dev.pluginProps["mac_address"] == "AABBCC000009"
    assert host._identity_bad == {} and host._identity_warned == set()
    assert host.last_polled == {1: 0}
    assert logged.lines == [("INFO", "Accepted the replaced Shelly for Garage Plug (now AABBCC000009).")]


def test_a_moved_shelly_is_not_accepted(plugin_mod, monkeypatch, devices):
    dev = FakeDev(1, "Garage Plug", props={"mac_address": "AABBCC000001"})
    devices[1] = dev
    host, logged = _accept_host(plugin_mod, monkeypatch, "AABBCC000009",
                                advertised={"AABBCC000001": "192.168.1.44"})
    host._identity_bad[1] = "AABBCC000009"
    plugin_mod.Plugin._menu_accept_replaced_body(host)
    assert dev.pluginProps["mac_address"] == "AABBCC000001"
    assert logged.lines[0][0] == "WARNING" and "has moved" in logged.lines[0][1]


def test_a_new_shelly_that_does_not_answer_is_not_accepted(plugin_mod, monkeypatch, devices):
    dev = FakeDev(1, "Garage Plug", props={"mac_address": "AABBCC000001"})
    devices[1] = dev
    host, logged = _accept_host(plugin_mod, monkeypatch, "")
    host._identity_bad[1] = "AABBCC000009"
    plugin_mod.Plugin._menu_accept_replaced_body(host)
    assert dev.pluginProps["mac_address"] == "AABBCC000001"
    assert "did not answer" in logged.lines[0][1]


def test_nothing_waiting_says_so(plugin_mod, monkeypatch):
    host, logged = _accept_host(plugin_mod, monkeypatch, "")
    plugin_mod.Plugin._menu_accept_replaced_body(host)
    assert logged.lines == [("INFO", "No device is waiting for a replaced Shelly to be accepted.")]


def test_the_messages_point_at_the_menu_that_exists(plugin_mod):
    src = (SERVER_DIR / "plugin.py").read_text(encoding="utf-8")
    assert "clear its MAC" not in src
    assert src.count("Accept Replaced Shellys") >= 2
    menu = ET.parse(SERVER_DIR / "MenuItems.xml").getroot()
    items = {m.findtext("Name"): m.findtext("CallbackMethod") for m in menu.iter("MenuItem")}
    assert hasattr(plugin_mod.Plugin, items["Accept Replaced Shellys"])


# ── High Power Alert with no power figure ───────────────────────────────────

def test_a_reading_without_power_leaves_the_alert_alone(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    host = types.SimpleNamespace(power_alert_active={1: True}, fired=[])
    host._fire_trigger = lambda *a, **k: host.fired.append(a)
    dev = FakeDev(1, "Kettle", props={"power_alert_enabled": True, "power_alert_watts": "2000"})
    plugin_mod.Plugin._check_power_alert(host, dev, None)
    assert host.power_alert_active == {1: True} and host.fired == []


def test_a_status_without_apower_is_not_a_poll_error(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "log", _Log())
    host = types.SimpleNamespace(
        logger=_logger(), log_activity=False, _switch_changed={}, power_alert_active={},
        _get_total_wh=plugin_mod.Plugin._get_total_wh,
        _calc_energy=lambda dev_id, wh: (0.0, 0.0),
        _mirror_states=lambda *a, **k: None,
        _capture_unhandled_fields=lambda *a, **k: None,
        _mark_online=lambda d: None, _fire_trigger=lambda *a, **k: None)
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    host._check_power_alert = plugin_mod.Plugin._check_power_alert.__get__(host)
    dev = FakeDev(1, "Kettle", props={"has_pm": True, "power_alert_enabled": True,
                                      "power_alert_watts": "2000"})
    plugin_mod.Plugin._apply_relay_status(host, dev, {"output": True, "voltage": 240.1})
    assert dev.states["onOffState"] is True and dev.states["voltage"] == 240.1


# ── BLU buttons: no dead sensorValue on a press ─────────────────────────────

@pytest.mark.parametrize("type_id", ["shellyBluButton", "shellyBluRC4"])
def test_a_blu_press_writes_only_states_the_button_has(plugin_mod, type_id):
    """The button sets no Supports* prop, so it has no sensorValue. The press
    lives in lastAction / pressCount and the bluButtonPress trigger."""
    fired = []
    host = types.SimpleNamespace(last_seen={}, log_activity=False, logger=_logger(),
                                 _note_back_online=lambda *a, **k: None,
                                 _fire_trigger=lambda *a, **k: fired.append(a))
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    dev = FakeDev(8, "Hall Button", type_id=type_id, states={"deviceOnline": True, "pressCount": 2})
    plugin_mod.Plugin._process_blu_event(host, dev, {"event": "single_push", "idx": 1, "batteryPct": 90})
    assert "sensorValue" not in dev.states
    assert dev.states["lastAction"] == "single_push" and dev.states["pressCount"] == 3
    assert dev.states["batteryPct"] == 90 and fired[0][0] == "bluButtonPress"
