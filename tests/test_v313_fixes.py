#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v313_fixes.py
# Description: Regression tests for the v3.13 deep-review medium batch (Fable 5
#              review): the extracted webhook event applier (Uni input0 fix,
#              per-field token tolerance), the v3.11 repair back-off state
#              machine (first-ever coverage), poll back-off, battery stale
#              threshold, secrets-precedence on prefs save, sensor-webhook
#              dedup, BLU-gateway discoverability and the duplicate-guard
#              webhook gate.
# Author:      CliveS & Claude Fable 5
# Date:        17-07-2026
# Version:     1.0

from __future__ import annotations

import threading
import time
import types


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay",
                 mac="", ip="", channel="0", enabled=True, props=None,
                 states=None):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = enabled
        self.configured   = True
        self.pluginProps  = {"mac_address": mac, "ip_address": ip,
                             "channel_id": channel}
        if props:
            self.pluginProps.update(props)
        self.states       = states if states is not None else {}
        self.state_writes = []

    def updateStateOnServer(self, key, value, uiValue=None, **_kw):
        self.states[key] = value
        self.state_writes.append((key, value, uiValue))

    def updateStatesOnServer(self, updates):
        for u in updates:
            self.updateStateOnServer(u["key"], u["value"], u.get("uiValue"))

    def replacePluginPropsOnServer(self, new_props):
        self.pluginProps = dict(new_props)


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload    = payload
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Logger:
    def __init__(self):
        self.lines = []
    def debug(self, msg):   self.lines.append(("DEBUG", msg))
    def info(self, msg):    self.lines.append(("INFO", msg))
    def warning(self, msg): self.lines.append(("WARNING", msg))
    def error(self, msg):   self.lines.append(("ERROR", msg))


def _qs(d):
    """dict -> parse_qs-style {key: [value]}"""
    return {k: [str(v)] for k, v in d.items()}


def _apply_receiver(plugin_mod):
    return types.SimpleNamespace(
        last_polled={}, logger=_Logger(),
        _fire_trigger=lambda *a, **k: None,
        _mirror_states=lambda *a, **k: None,
        _qp=plugin_mod.Plugin._qp,
        _qp_int=plugin_mod.Plugin._qp_int,
        _qp_float=plugin_mod.Plugin._qp_float,
    )


# ── _apply_webhook_event (extracted from the closure — first coverage) ────────

def test_webhook_switch_on(plugin_mod):
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(1, "Plug")
    plugin_mod.Plugin._apply_webhook_event(r, dev, _qs({"type": "switch", "state": "on"}))
    assert dev.states["onOffState"] is True
    assert 1 in r.last_polled


def test_webhook_uni_input0_writes_input0_state(plugin_mod):
    """v3.13: the Uni declares input0/input1 — its sensorValue write was dead."""
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(2, "Uni", type_id="shellyUni")
    plugin_mod.Plugin._apply_webhook_event(
        r, dev, _qs({"type": "input", "state": "on", "input": "0"}))
    assert dev.states.get("input0") is True
    assert "sensorValue" not in dev.states


def test_webhook_i4_input0_keeps_sensorvalue(plugin_mod):
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(3, "i4", type_id="shellyI4")
    plugin_mod.Plugin._apply_webhook_event(
        r, dev, _qs({"type": "input", "state": "on", "input": "0"}))
    assert dev.states.get("sensorValue") is True


def test_webhook_ht_bad_field_skips_only_that_field(plugin_mod):
    """One unsubstituted token must not 500 the request or drop the others."""
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(4, "HT", type_id="shellyHT")
    plugin_mod.Plugin._apply_webhook_event(
        r, dev, _qs({"type": "ht", "tC": "{temperature}", "humidity": "55.5",
                     "battery": "90"}))
    assert "sensorValue" not in dev.states          # bad tC skipped
    assert dev.states["humidity"] == 55.5           # good fields land
    assert dev.states["batteryPct"] == 90


def test_webhook_ht_macro_token_skipped(plugin_mod):
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(5, "HT", type_id="shellyHT")
    plugin_mod.Plugin._apply_webhook_event(
        r, dev, _qs({"type": "ht", "tC": "${ev.tC}"}))
    assert dev.states == {}


def test_webhook_smoke_alarm(plugin_mod):
    r = _apply_receiver(plugin_mod)
    dev = FakeDev(6, "Smoke", type_id="shellySmoke")
    plugin_mod.Plugin._apply_webhook_event(
        r, dev, _qs({"type": "smoke", "alarm": "true"}))
    assert dev.states["sensorValue"] is True


def test_qp_float_token_tolerance(plugin_mod):
    P = plugin_mod.Plugin
    assert P._qp_float(_qs({"x": "21.5"}), "x") == 21.5
    assert P._qp_float(_qs({"x": "{tC}"}), "x") is None
    assert P._qp_float(_qs({"x": "${ev.tC}"}), "x") is None
    assert P._qp_float(_qs({"x": ""}), "x") is None
    assert P._qp_float({}, "x") is None
    assert P._qp_float(_qs({"x": "junk"}), "x") is None


# ── v3.11 repair back-off state machine (first-ever coverage) ────────────────

def _health_receiver(plugin_mod, devices, device_hooks, repair_sticks):
    """Fake enough of Plugin for _check_webhook_health. device_hooks maps
    ip -> list of hook dicts; repair_sticks controls whether a repair's
    recheck sees the hooks appear."""
    plugin_mod.indigo.devices.iter = lambda *a, **k: list(devices)
    state = types.SimpleNamespace(repairs=[])

    def _rget(url, params=None, timeout=None):
        ip = url.split("/")[2]
        if "Webhook.List" in url:
            return FakeResp({"hooks": device_hooks.get(ip, [])})
        return FakeResp({})

    def _configure_webhooks(dev):
        state.repairs.append(dev.id)
        if repair_sticks:
            ip = dev.pluginProps["ip_address"]
            device_hooks[ip] = [{"id": 1, "urls":
                                 [f"http://x:8178/shellyEvent?devId={dev.id}&t=s"]}]

    receiver = types.SimpleNamespace(
        server_ip="192.168.1.9",
        logger=_Logger(),
        webhook_repair_fails={},
        _dup_warned=set(),
        _duplicate_device_ids=lambda: (set(), []),
        _rget=_rget,
        _configure_webhooks=_configure_webhooks,
    )
    return receiver, state


def test_backoff_gives_up_after_three_failed_repairs(plugin_mod):
    dev = FakeDev(10, "Flaky", ip="192.168.1.50")
    hooks = {"192.168.1.50": []}
    receiver, state = _health_receiver(plugin_mod, [dev], hooks,
                                       repair_sticks=False)
    for _ in range(5):
        plugin_mod.Plugin._check_webhook_health(receiver)
    # repairs attempted only until the counter hits the cap, then quiet
    assert len(state.repairs) == plugin_mod.MAX_WEBHOOK_REPAIR_FAILS
    assert receiver.webhook_repair_fails[10] == plugin_mod.MAX_WEBHOOK_REPAIR_FAILS
    # the gave-up passes leave a debug trace, not more repairs
    gave_up = [m for lv, m in receiver.logger.lines
               if lv == "DEBUG" and "gave up" in m]
    assert len(gave_up) == 2, "passes 4 and 5 must be quiet give-ups"


def test_backoff_clears_when_repair_sticks(plugin_mod):
    dev = FakeDev(11, "Healthy", ip="192.168.1.51")
    hooks = {"192.168.1.51": []}
    receiver, state = _health_receiver(plugin_mod, [dev], hooks,
                                       repair_sticks=True)
    plugin_mod.Plugin._check_webhook_health(receiver)
    assert state.repairs == [11]
    assert 11 not in receiver.webhook_repair_fails   # stuck -> counter cleared
    # next pass: hooks present, nothing repaired
    plugin_mod.Plugin._check_webhook_health(receiver)
    assert state.repairs == [11]


def test_backoff_partial_count_cleared_by_hook_presence(plugin_mod):
    dev = FakeDev(12, "Recovered", ip="192.168.1.52")
    hooks = {"192.168.1.52": []}
    receiver, state = _health_receiver(plugin_mod, [dev], hooks,
                                       repair_sticks=False)
    plugin_mod.Plugin._check_webhook_health(receiver)   # one failed repair
    assert receiver.webhook_repair_fails[12] == 1
    # hooks appear out-of-band (device recovered)
    hooks["192.168.1.52"] = [{"id": 9, "urls":
                              ["http://x:8178/shellyEvent?devId=12&t=s"]}]
    plugin_mod.Plugin._check_webhook_health(receiver)
    assert 12 not in receiver.webhook_repair_fails


def test_duplicate_devices_never_repaired(plugin_mod):
    dev = FakeDev(13, "Dup", ip="192.168.1.53")
    hooks = {"192.168.1.53": []}
    receiver, state = _health_receiver(plugin_mod, [dev], hooks,
                                       repair_sticks=True)
    receiver._duplicate_device_ids = lambda: ({13}, [])
    plugin_mod.Plugin._check_webhook_health(receiver)
    assert state.repairs == []


def test_health_check_skipped_without_server_ip(plugin_mod):
    dev = FakeDev(14, "Any", ip="192.168.1.54")
    receiver, state = _health_receiver(plugin_mod, [dev],
                                       {"192.168.1.54": []}, True)
    receiver.server_ip = ""
    plugin_mod.Plugin._check_webhook_health(receiver)
    assert state.repairs == []


# ── poll back-off + battery stale threshold ───────────────────────────────────

def test_poll_failed_stamps_last_polled(plugin_mod):
    receiver = types.SimpleNamespace(fail_count={}, last_polled={},
                                     _mark_offline=lambda d, r="": None)
    dev = FakeDev(20, "Dead Plug")
    before = time.time()
    plugin_mod.Plugin._poll_failed(receiver, dev, "no route")
    assert receiver.last_polled[20] >= before, \
        "failed poll must stamp last_polled so retries honour the cadence"
    assert receiver.fail_count[20] == 1


def test_check_online_battery_threshold(plugin_mod):
    marked = []
    receiver = types.SimpleNamespace(
        last_seen={}, stale_minutes=10,
        _pref_int=plugin_mod.Plugin._pref_int,
        pluginPrefs={},
        _mark_offline=lambda d, r="": marked.append((d.id, r)),
    )
    now = time.time()
    ht = FakeDev(21, "H&T", type_id="shellyHT")
    receiver.last_seen[21] = now - 3600          # 1h quiet
    plugin_mod.Plugin._check_online(receiver, ht, now)
    assert marked == [], "1h quiet is NORMAL for a battery sensor (12h default)"
    receiver.last_seen[21] = now - 13 * 3600     # 13h quiet
    plugin_mod.Plugin._check_online(receiver, ht, now)
    assert marked and marked[0][0] == 21


# ── prefs: secrets precedence survives a dialog save ──────────────────────────

def test_closed_prefs_keeps_secrets_precedence(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "_SECRETS_SHELLY_SUBNETS", "192.168.1")
    monkeypatch.setattr(plugin_mod, "_SECRETS_SHELLY_USER", "secretuser")
    monkeypatch.setattr(plugin_mod, "_SECRETS_SHELLY_PASS", "secretpass")
    monkeypatch.setattr(plugin_mod, "_SECRETS_INDIGO_IP", "192.168.1.9")
    receiver = types.SimpleNamespace(
        _pref_int=plugin_mod.Plugin._pref_int,
        indigo_log_handler=types.SimpleNamespace(setLevel=lambda l: None),
    )
    plugin_mod.Plugin.closedPrefsConfigUi(
        receiver, {"discovery_subnets": "10.0.0", "shelly_username": "guiuser",
                   "shelly_password": "guipass"}, False)
    assert receiver.subnets == ["192.168.1"], "secrets must win over the dialog"
    assert receiver.shelly_user == "secretuser"
    assert receiver.shelly_pass == "secretpass"


def test_validate_prefs_allows_blank_subnets_with_secret(plugin_mod, monkeypatch):
    monkeypatch.setattr(plugin_mod, "_SECRETS_SHELLY_SUBNETS", "192.168.1")
    receiver = types.SimpleNamespace()
    ok, _v, errs = plugin_mod.Plugin.validatePrefsConfigUi(
        receiver, {"discovery_subnets": ""})
    assert ok and len(errs) == 0
    monkeypatch.setattr(plugin_mod, "_SECRETS_SHELLY_SUBNETS", "")
    ok, _v, errs = plugin_mod.Plugin.validatePrefsConfigUi(
        receiver, {"discovery_subnets": ""})
    assert not ok and "discovery_subnets" in errs


# ── sensor webhook dedup + BLU gateway discoverability ────────────────────────

def test_sensor_webhook_skips_existing(plugin_mod):
    creates = []

    def _rget(url, params=None, timeout=None):
        if "Webhook.List" in url:
            return FakeResp({"hooks": [{"id": 1, "event": "temperature.change",
                                        "urls": ["http://x:8178/shellyEvent?devId=30&type=ht"]}]})
        if "Webhook.Create" in url:
            creates.append(params)
            return FakeResp({})
        return FakeResp({})

    receiver = types.SimpleNamespace(_rget=_rget, logger=_Logger())
    dev = FakeDev(30, "HT", type_id="shellyHT", ip="192.168.1.60")
    plugin_mod.Plugin._setup_sensor_webhook(
        receiver, "192.168.1.60", dev, "http://x:8178/shellyEvent?devId=30&type=ht&tC=${ev.tC}",
        "temperature.change")
    assert creates == [], "existing hook for this event/devId must not duplicate"


def test_existing_ips_skips_blu_gateway(plugin_mod):
    blu   = FakeDev(40, "BLU Button", type_id="shellyBluButton", ip="192.168.1.70")
    relay = FakeDev(41, "Plug", ip="192.168.1.71")
    plugin_mod.indigo.devices.iter = lambda *a, **k: [blu, relay]
    ips = plugin_mod.Plugin._existing_device_ips(types.SimpleNamespace())
    assert "192.168.1.71" in ips
    assert "192.168.1.70" not in ips, "BLU records carry the GATEWAY's IP"
