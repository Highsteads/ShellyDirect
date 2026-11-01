#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_review_polling_faults.py
# Description: Tests written alongside the 01-11-2026 code review. They pin the
#              behaviour of the relay command path, the slow "detail" sweep and
#              the energy-meter poll. The detail-sweep, EM 0 W and restart
#              tests cover the faults the review found, fixed in v4.3.6.
# Author:      CliveS & Claude Opus 5.5
# Date:        01-11-2026
# Version:     1.1 (v4.3.6 fixes: xfails removed, restart tests added)

from __future__ import annotations

import time
import types

import pytest
import requests


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", props=None, states=None):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = True
        self.configured   = True
        self.pluginProps  = {"ip_address": "10.0.0.5", "channel_id": "0"}
        if props:
            self.pluginProps.update(props)
        self.states = states if states is not None else {}

    def updateStateOnServer(self, key, value, uiValue=None, **_kw):
        self.states[key] = value

    def updateStatesOnServer(self, updates):
        for u in updates:
            self.states[u["key"]] = u["value"]


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload    = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


class _Logger:
    def __init__(self):
        self.lines = []

    def debug(self, msg):
        self.lines.append(("DEBUG", str(msg)))

    info = warning = error = debug


@pytest.fixture
def quiet_log(plugin_mod, monkeypatch):
    lines = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": lines.append((level, str(msg))))
    return lines


# ── relay commands: success is only claimed when the Shelly said yes ─────────

def _switch_host(plugin_mod, resp=None, exc=None):
    sent = []

    def _rcommand(url, params=None):
        sent.append((url, dict(params or {})))
        if exc:
            raise exc
        return resp

    return types.SimpleNamespace(_rcommand=_rcommand), sent


def test_switch_set_reports_success_on_http_200(plugin_mod, quiet_log):
    host, sent = _switch_host(plugin_mod, resp=FakeResp({"was_on": False}))
    assert plugin_mod.Plugin._switch_set(host, "10.0.0.5", 1, True, "Kettle") is True
    url, params = sent[0]
    assert url == "http://10.0.0.5/rpc/Switch.Set"
    assert params["id"] == 1 and params["on"] == "true"
    assert params["tag"] == plugin_mod.COMMAND_TAG     # so "who switched it" says Indigo


@pytest.mark.parametrize("on, expected", [(True, "true"), (False, "false")])
def test_switch_set_sends_the_right_word(plugin_mod, quiet_log, on, expected):
    host, sent = _switch_host(plugin_mod, resp=FakeResp({}))
    plugin_mod.Plugin._switch_set(host, "10.0.0.5", 0, on, "Kettle")
    assert sent[0][1]["on"] == expected


def test_switch_set_reports_failure_on_an_http_error(plugin_mod, quiet_log):
    host, _ = _switch_host(plugin_mod, resp=FakeResp({"code": -103}, status=500))
    assert plugin_mod.Plugin._switch_set(host, "10.0.0.5", 0, True, "Kettle") is False
    assert quiet_log and quiet_log[0][0] == "ERROR"


@pytest.mark.parametrize("exc", [requests.exceptions.ConnectionError("x"),
                                 requests.exceptions.Timeout("x")])
def test_switch_set_reports_failure_when_the_shelly_is_unreachable(plugin_mod, quiet_log, exc):
    host, _ = _switch_host(plugin_mod, exc=exc)
    assert plugin_mod.Plugin._switch_set(host, "10.0.0.5", 0, True, "Kettle") is False


def test_a_failed_turn_on_leaves_the_indigo_state_alone(plugin_mod, quiet_log):
    """If the command did not reach the relay, Indigo must not show it as on."""
    dev  = FakeDev(1, "Kettle", states={"onOffState": False})
    host = types.SimpleNamespace(
        logger=_Logger(), log_activity=False,
        _command_ip=lambda d, what="command": "10.0.0.5",
        _set_output=lambda d, ip, on: False,
        _poll_device=lambda d: None)
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    action = types.SimpleNamespace(deviceAction=plugin_mod.indigo.kDeviceAction.TurnOn)
    plugin_mod.Plugin.actionControlDevice(host, action, dev)
    assert dev.states["onOffState"] is False


def test_a_refused_command_ip_sends_nothing(plugin_mod, quiet_log):
    """_command_ip returns None when a different Shelly is at the address."""
    dev   = FakeDev(1, "Kettle", states={"onOffState": False})
    calls = []
    host  = types.SimpleNamespace(
        logger=_Logger(), log_activity=False,
        _command_ip=lambda d, what="command": None,
        _set_output=lambda d, ip, on: calls.append(on) or True,
        _poll_device=lambda d: None)
    action = types.SimpleNamespace(deviceAction=plugin_mod.indigo.kDeviceAction.TurnOn)
    plugin_mod.Plugin.actionControlDevice(host, action, dev)
    assert calls == [] and dev.states["onOffState"] is False


# ── the slow detail sweep must not retry a dead device every tick ────────────

def _detail_host(plugin_mod, rget):
    host = types.SimpleNamespace(
        logger=_Logger(), last_detail={},
        _target_ip=lambda d: d.pluginProps["ip_address"],
        _rget=rget,
        _capture_unhandled_fields=lambda d, f, extra_handled=None: None)
    host._DETAIL_WIFI = plugin_mod.Plugin._DETAIL_WIFI
    host._DETAIL_SYS  = plugin_mod.Plugin._DETAIL_SYS
    host._DETAIL_LINK = plugin_mod.Plugin._DETAIL_LINK
    return host


def test_a_successful_detail_sweep_is_stamped(plugin_mod):
    host = _detail_host(plugin_mod, lambda url, timeout=None: FakeResp(
        {"wifi": {"rssi": -60}, "sys": {"uptime": 100}}))
    dev  = FakeDev(1, "Kettle")
    before = time.time()
    plugin_mod.Plugin._poll_detail(host, dev)
    assert host.last_detail[1] >= before


def test_a_failed_detail_sweep_waits_for_its_interval(plugin_mod):
    def _timeout(url, timeout=None):
        raise requests.exceptions.Timeout("slow")
    host = _detail_host(plugin_mod, _timeout)
    dev  = FakeDev(1, "Kettle")
    plugin_mod.Plugin._poll_detail(host, dev)
    assert 1 in host.last_detail, "a failed sweep must still wait detail_interval"


# ── energy meter: a missing reading must not become 0 W ──────────────────────

def _em_host(plugin_mod, responses):
    calls = []

    def _rget(url, params=None, timeout=None):
        calls.append(url)
        for frag, resp in responses.items():
            if frag in url:
                return resp
        return FakeResp({}, status=404)

    host = types.SimpleNamespace(
        logger=_Logger(), last_polled={},
        _target_ip=lambda d: d.pluginProps["ip_address"],
        _rget=_rget,
        _calc_energy=lambda dev_id, wh: (1.0, 2.0),
        _mirror_states=lambda *a, **k: None,
        _capture_unhandled_fields=lambda *a, **k: None,
        _mark_online=lambda d: None,
        _poll_failed=lambda d, r="": None,
        _pref_int=plugin_mod.Plugin._pref_int,
        _get_total_wh=plugin_mod.Plugin._get_total_wh,
        _em_total_wh=plugin_mod.Plugin._em_total_wh)
    return host, calls


def test_em1_poll_writes_the_real_power_and_energy(plugin_mod, quiet_log):
    host, _ = _em_host(plugin_mod, {
        "EM1.GetStatus":     FakeResp({"voltage": 240.0, "current": 2.0, "act_power": 480.0}),
        "EM1Data.GetStatus": FakeResp({"total_act_energy": 12345.0}),
    })
    dev = FakeDev(3, "Grid Clamp", type_id="shellyEM", states={"sensorValue": 99.0})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["sensorValue"] == 480.0
    assert dev.states["energyKwhToday"] == 1.0
    assert dev.states["energyKwhMonth"] == 2.0


def test_em_poll_keeps_energy_when_the_energy_read_fails(plugin_mod, quiet_log):
    host, _ = _em_host(plugin_mod, {
        "EM1.GetStatus":     FakeResp({"voltage": 240.0, "current": 2.0, "act_power": 480.0}),
        "EM1Data.GetStatus": FakeResp({}, status=500),
    })
    dev = FakeDev(3, "Grid Clamp", type_id="shellyEM", states={"energyKwhToday": 5.5})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["energyKwhToday"] == 5.5


def test_em_poll_does_not_invent_zero_watts(plugin_mod, quiet_log):
    host, _ = _em_host(plugin_mod, {
        "EM1.GetStatus":     FakeResp({"voltage": 240.0}),        # no act_power
        "EM1Data.GetStatus": FakeResp({"total_act_energy": 12345.0}),
    })
    dev = FakeDev(3, "Grid Clamp", type_id="shellyEM", states={"sensorValue": 480.0})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["sensorValue"] == 480.0, "a missing reading was written as 0 W"


# ── relay status: offline / partial readings ─────────────────────────────────

def _relay_host(plugin_mod):
    host = types.SimpleNamespace(
        logger=_Logger(), log_activity=False, _switch_changed={},
        power_alert_active={},
        _get_total_wh=plugin_mod.Plugin._get_total_wh,
        _calc_energy=lambda dev_id, wh: (0.25, 3.0),
        _mirror_states=lambda *a, **k: None,
        _capture_unhandled_fields=lambda *a, **k: None,
        _mark_online=lambda d: None,
        _fire_trigger=lambda *a, **k: None,
        _check_power_alert=lambda d, w: None)
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    return host


def test_relay_status_writes_watts_and_energy_with_units(plugin_mod):
    host = _relay_host(plugin_mod)
    dev  = FakeDev(1, "Washer", props={"has_pm": True})
    plugin_mod.Plugin._apply_relay_status(host, dev, {
        "output": True, "apower": 1834.2, "voltage": 241.0, "current": 7.6,
        "aenergy": {"total": 98765.4}})
    assert dev.states["powerWatts"] == pytest.approx(1834.2)     # watts, not kW
    assert dev.states["energyKwhToday"] == 0.25                  # kWh from _calc_energy
    assert dev.states["energyKwhMonth"] == 3.0
    assert dev.states["onOffState"] is True


def test_relay_status_without_aenergy_does_not_touch_energy(plugin_mod):
    host = _relay_host(plugin_mod)
    dev  = FakeDev(1, "Washer", props={"has_pm": True},
                   states={"energyKwhToday": 1.234, "onOffState": True})
    plugin_mod.Plugin._apply_relay_status(host, dev, {"output": True, "apower": 5.0})
    assert dev.states["energyKwhToday"] == 1.234


def test_marking_a_device_offline_flips_deviceOnline(plugin_mod):
    """ApplianceMonitor relies on deviceOnline (not powerWatts) to tell that a
    reading is no longer live, so this flip is the contract it depends on."""
    fired = []
    host  = types.SimpleNamespace(_offline_batch=[],
                                  _fire_trigger=lambda *a, **k: fired.append(a))
    dev   = FakeDev(1, "Washer", states={"deviceOnline": True, "powerWatts": 1834.2})
    plugin_mod.Plugin._mark_offline(host, dev, "timed out")
    assert dev.states["deviceOnline"] is False
    assert fired and fired[0][0] == "deviceWentOffline"


def test_em_poll_keeps_the_last_reading_when_power_is_missing_but_writes_the_rest(plugin_mod, quiet_log):
    host, _ = _em_host(plugin_mod, {
        "EM1.GetStatus":     FakeResp({"voltage": 241.5}),        # no act_power
        "EM1Data.GetStatus": FakeResp({"total_act_energy": 12345.0}),
    })
    dev = FakeDev(3, "Grid Clamp", type_id="shellyEM",
                  states={"sensorValue": 480.0, "powerA": 480.0, "currentA": 2.0})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["voltageA"] == 241.5                         # sent, so written
    assert dev.states["powerA"] == 480.0 and dev.states["currentA"] == 2.0   # not sent, kept


def test_3phase_total_falls_back_to_the_sum_only_when_every_phase_is_there(plugin_mod, quiet_log):
    full = {"a_act_power": 100.0, "b_act_power": 200.0, "c_act_power": 300.0,
            "a_voltage": 240.0, "b_voltage": 240.0, "c_voltage": 240.0}
    host, _ = _em_host(plugin_mod, {"EM.GetStatus": FakeResp(full),
                                    "EMData.GetStatus": FakeResp({"total_act": 1.0})})
    dev = FakeDev(4, "House", type_id="shellyEM", props={"is_3phase": True})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["sensorValue"] == 600.0

    partial = {"a_act_power": 100.0, "b_act_power": 200.0}         # phase C missing
    host, _ = _em_host(plugin_mod, {"EM.GetStatus": FakeResp(partial),
                                    "EMData.GetStatus": FakeResp({"total_act": 1.0})})
    dev = FakeDev(4, "House", type_id="shellyEM", props={"is_3phase": True},
                  states={"sensorValue": 650.0, "powerC": 350.0})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["sensorValue"] == 650.0, "a partial sum must not replace the total"
    assert dev.states["powerC"] == 350.0
    assert dev.states["powerA"] == 100.0


def test_em_poll_with_a_real_zero_writes_zero(plugin_mod, quiet_log):
    host, _ = _em_host(plugin_mod, {
        "EM1.GetStatus":     FakeResp({"voltage": 240.0, "current": 0.0, "act_power": 0.0}),
        "EM1Data.GetStatus": FakeResp({"total_act_energy": 1.0}),
    })
    dev = FakeDev(3, "Grid Clamp", type_id="shellyEM", states={"sensorValue": 480.0})
    plugin_mod.Plugin._poll_em(host, dev)
    assert dev.states["sensorValue"] == 0.0


# ── v4.3.6: a reading from before a restart must not look live ───────────────

def _fail_host(unconfirmed):
    offline = []
    host = types.SimpleNamespace(
        fail_count={}, last_polled={}, _unconfirmed=set(unconfirmed),
        _mark_offline=lambda d, r="": offline.append((d.id, r)),
        _try_relocate=lambda d: offline.append((d.id, "relocate")))
    return host, offline


def test_first_failure_after_a_start_marks_the_device_offline_at_once(plugin_mod):
    host, offline = _fail_host({1})
    dev = FakeDev(1, "Washer")
    plugin_mod.Plugin._poll_failed(host, dev, "timed out")
    assert offline == [(1, "timed out")]
    assert host.fail_count[1] == 1, "the back-off count itself is unchanged"


def test_a_device_that_has_answered_still_gets_three_strikes(plugin_mod):
    """Mid-cycle Wi-Fi blips must not flip deviceOnline on one lost poll."""
    host, offline = _fail_host(set())
    dev = FakeDev(1, "Washer")
    plugin_mod.Plugin._poll_failed(host, dev, "timed out")
    plugin_mod.Plugin._poll_failed(host, dev, "timed out")
    assert offline == []
    plugin_mod.Plugin._poll_failed(host, dev, "timed out")
    assert offline == [(1, "timed out"), (1, "relocate")]


def test_a_successful_read_confirms_the_device(plugin_mod):
    host = types.SimpleNamespace(
        last_seen={}, fail_count={}, _mac_verified={}, webhook_repair_fails={},
        _unconfirmed={1}, _note_back_online=lambda *a, **k: None)
    dev = FakeDev(1, "Washer", states={"deviceOnline": True})
    plugin_mod.Plugin._mark_online(host, dev)
    assert host._unconfirmed == set()


def test_going_offline_does_not_zero_power(plugin_mod):
    """ApplianceMonitor keeps using the last watts while a cycle is running and
    the meter is offline; a 0 here would end a wash on a Wi-Fi blip."""
    host = types.SimpleNamespace(_offline_batch=[], _fire_trigger=lambda *a, **k: None)
    dev  = FakeDev(1, "Washer", states={"deviceOnline": True, "powerWatts": 1834.2})
    plugin_mod.Plugin._mark_offline(host, dev, "timed out")
    assert dev.states["powerWatts"] == 1834.2
