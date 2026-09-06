#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v318_event_log_quiet.py
# Description: The Indigo event log is shared by every plugin on the server and
#              was running at roughly 2,031 lines a day. ShellyDirect's share of
#              it, measured from the dated Events.txt files for 31-Aug to
#              05-Sep-2026, was 61 lines a day, and 55 of those were routine
#              narration nobody reads: 124 'sent "X" off' and 94 'sent "X" on'
#              over the six days, 48 '[X] Webhooks OK' saying nothing was wrong,
#              11 monthly baseline resets and 6 daily ones.
#
#              These tests pin the split. Routine narration goes to the plugin's
#              own log file and reaches the event log only when the user ticks
#              the new preference; every WARNING and every ERROR reaches the
#              event log whatever that preference says. That second half is the
#              one that matters: Log_Error_Watch.py reads the EVENT log and
#              nothing else, so a fault demoted into a plugin's own file is a
#              fault nobody is watching.
# Author:      CliveS & Claude Opus 5
# Date:        06-09-2026
# Version:     1.0

from __future__ import annotations

import ast
import io
import types
from pathlib import Path

import pytest

SERVER_DIR = (Path(__file__).resolve().parent.parent
              / "ShellyDirect.indigoPlugin" / "Contents" / "Server Plugin")
PLUGIN_PY  = SERVER_DIR / "plugin.py"
CONFIG_XML = SERVER_DIR / "PluginConfig.xml"


# ── scaffolding ──────────────────────────────────────────────────────────────

class _Logger:
    """Records which handler each line was aimed at.

    In Indigo, self.logger.info() echoes into the shared event log and
    self.logger.debug() does not (the plugin's own file handler runs at
    THREADDEBUG). So "did this reach the event log?" is exactly "was info,
    warning or error used?".
    """

    def __init__(self):
        self.lines = []

    def debug(self, msg, *a, **k):   self.lines.append(("DEBUG", str(msg)))
    def info(self, msg, *a, **k):    self.lines.append(("INFO", str(msg)))
    def warning(self, msg, *a, **k): self.lines.append(("WARNING", str(msg)))
    def error(self, msg, *a, **k):   self.lines.append(("ERROR", str(msg)))

    def at(self, level):
        return [m for lvl, m in self.lines if lvl == level]

    @property
    def reached_event_log(self):
        return [m for lvl, m in self.lines if lvl != "DEBUG"]


class _Dev:
    def __init__(self, dev_id=101, name="Kitchen Plug", type_id="shellyRelay",
                 on=False, props=None):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = True
        self.onState      = on
        self.states       = {"brightnessLevel": 50}
        self.pluginProps  = {"ip_address": "192.168.1.50", "channel_id": "0"}
        if props:
            self.pluginProps.update(props)
        self.written      = {}

    def updateStateOnServer(self, key, value, **k):
        self.written[key] = value


def _host(plugin_mod, log_activity=False, **extra):
    """A bare host carrying the SHIPPED _log_activity, never a stub.

    Binding the real method is the whole point: a stub would prove only that
    the stub works, which is how a routing change gets tested into thin air.
    """
    h = types.SimpleNamespace(logger=_Logger(), log_activity=log_activity,
                              _webhook_bad=set(), **extra)
    h._log_activity = plugin_mod.Plugin._log_activity.__get__(h)
    return h


# ── the helper itself ────────────────────────────────────────────────────────

def test_narration_defaults_to_the_plugins_own_log(plugin_mod):
    h = _host(plugin_mod)
    h._log_activity('sent "Kitchen Plug" on')
    assert h.logger.at("DEBUG") == ['sent "Kitchen Plug" on']
    assert h.logger.reached_event_log == []


def test_narration_reaches_the_event_log_when_the_user_asks(plugin_mod):
    h = _host(plugin_mod, log_activity=True)
    h._log_activity('sent "Kitchen Plug" on')
    assert h.logger.at("INFO") == ['sent "Kitchen Plug" on']
    assert h.logger.at("DEBUG") == []


def test_the_helper_can_only_ever_use_info_or_debug(plugin_mod):
    """Structural: _log_activity must have no route to warning or error.

    If a future edit lets a fault in here, the preference would decide whether
    that fault is visible, and off is the default.
    """
    tree = ast.parse(io.open(PLUGIN_PY, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_log_activity")
    used = {n.func.attr for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert used == {"info", "debug"}, used


def test_no_call_site_passes_a_level_to_the_helper(plugin_mod):
    """_log_activity takes a message only. A `level=` there would be silently
    swallowed as a TypeError inside a webhook thread, i.e. a dropped fault."""
    tree = ast.parse(io.open(PLUGIN_PY, encoding="utf-8").read())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_log_activity"]
    assert calls, "the scan found no call sites — it is passing vacuously"
    for c in calls:
        assert not c.keywords, ast.dump(c)[:200]
        assert len(c.args) == 1, ast.dump(c)[:200]


# ── the command echo, and the faults beside it ───────────────────────────────

def _drive_relay(plugin_mod, monkeypatch, device_action, succeeds=True,
                 log_activity=False, props=None):
    """Run the shipped actionControlDevice and collect BOTH log routes."""
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    dev = _Dev(props=props)
    h = _host(plugin_mod, log_activity=log_activity,
              _set_output=lambda d, ip, on: succeeds,
              _poll_device=lambda d: None)
    action = types.SimpleNamespace(deviceAction=device_action)
    plugin_mod.Plugin.actionControlDevice(h, action, dev)
    return h.logger, event_log


def test_relay_on_no_longer_narrates_to_the_event_log(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOn)
    assert logger.at("DEBUG") == ['sent "Kitchen Plug" on']
    assert event_log == []


def test_relay_off_no_longer_narrates_to_the_event_log(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOff)
    assert logger.at("DEBUG") == ['sent "Kitchen Plug" off']
    assert event_log == []


def test_relay_echo_still_available_on_request(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOn,
        log_activity=True)
    assert logger.at("INFO") == ['sent "Kitchen Plug" on']


def test_a_failed_on_is_still_an_ERROR_in_the_event_log(plugin_mod, monkeypatch):
    """THE test. A command that did not reach the device is a fault, and it must
    stay where Log_Error_Watch.py can see it — preference or no preference."""
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOn,
        succeeds=False)
    assert event_log == [("ERROR", 'failed to send on to "Kitchen Plug"')]


def test_a_failed_off_is_still_an_ERROR_in_the_event_log(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOff,
        succeeds=False)
    assert event_log == [("ERROR", 'failed to send off to "Kitchen Plug"')]


def test_a_locked_device_still_WARNS_in_the_event_log(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOff,
        props={"lock_off": True})
    assert event_log == [("WARNING",
                          "[Kitchen Plug] Turn Off blocked - device is locked")]


def test_a_missing_ip_is_still_an_ERROR_in_the_event_log(plugin_mod, monkeypatch):
    logger, event_log = _drive_relay(
        plugin_mod, monkeypatch, plugin_mod.indigo.kDeviceAction.TurnOn,
        props={"ip_address": "  "})
    assert event_log == [("ERROR", "[Kitchen Plug] No IP address configured")]


def test_dimmer_brightness_echo_is_quiet_too(plugin_mod, monkeypatch):
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    dev = _Dev(type_id="shellyDimmer")
    h = _host(plugin_mod,
              _light_set=lambda *a, **k: True,
              _pref_int=lambda props, key, default=0: default,
              _poll_device=lambda d: None)
    action = types.SimpleNamespace(
        deviceAction=plugin_mod.indigo.kDimmerAction.SetBrightness, actionValue=42)
    plugin_mod.Plugin.actionControlDimmer(h, action, dev)
    assert h.logger.at("DEBUG") == ['sent "Kitchen Plug" brightness -> 42%']
    assert event_log == []
    assert dev.written["brightnessLevel"] == 42   # the work still happened


# ── 'Webhooks OK' is now once-on-change ──────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def raise_for_status(self): pass
    def json(self): return self._p


def _ensure(plugin_mod, host, create_ok=True):
    wanted = [("switch.on", "http://192.168.1.9:8178/shellyEvent?devId=101&ev=on", 0)]

    def _rget(url, params=None, timeout=None):
        if "Webhook.List" in url:
            return _Resp({"hooks": []})
        if "Webhook.Create" in url:
            return _Resp({} if create_ok else {"code": -103}, 200 if create_ok else 400)
        return _Resp({})

    host._rget = _rget
    plugin_mod.indigo.devices.iter = lambda *a, **k: []
    plugin_mod.Plugin._ensure_webhooks(host, "192.168.1.50", _Dev(), wanted)


def test_a_healthy_webhook_pass_says_nothing_in_the_event_log(plugin_mod, monkeypatch):
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    h = _host(plugin_mod)
    _ensure(plugin_mod, h)
    _ensure(plugin_mod, h)          # and again, and again, all day
    assert event_log == []
    oks = [m for m in h.logger.at("DEBUG") if m.endswith("Webhooks OK")]
    assert oks == ["[Kitchen Plug] Webhooks OK"] * 2   # the plugin's own log keeps it


def test_a_repair_that_worked_is_announced_once_and_then_falls_quiet(plugin_mod,
                                                                    monkeypatch):
    """The latch. A failure warns, the recovery says so, and the steady state
    after it is silent — which is what 48 lines in six days was buying."""
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    h = _host(plugin_mod)

    _ensure(plugin_mod, h, create_ok=False)
    assert event_log[0][0] == "WARNING"
    assert 101 in h._webhook_bad

    _ensure(plugin_mod, h)
    assert event_log[1] == ("INFO", "[Kitchen Plug] Webhooks OK again")
    assert 101 not in h._webhook_bad

    _ensure(plugin_mod, h)
    assert len(event_log) == 2, event_log


def test_an_unreachable_device_arms_the_latch(plugin_mod, monkeypatch):
    """A device that was away must get its recovery announced when it returns,
    so the WARNING in the event log is not left dangling with no all-clear."""
    import requests
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    h = _host(plugin_mod)

    def _boom(url, params=None, timeout=None):
        raise requests.exceptions.ConnectionError("no route")

    h._rget = _boom
    plugin_mod.indigo.devices.iter = lambda *a, **k: []
    plugin_mod.Plugin._ensure_webhooks(h, "192.168.1.50", _Dev(), [])
    assert event_log[0][0] == "WARNING"
    assert 101 in h._webhook_bad

    _ensure(plugin_mod, h)
    assert event_log[1] == ("INFO", "[Kitchen Plug] Webhooks OK again")


# ── sensor reports: the routine one is narration, the alarm is not ───────────

def _webhook_receiver(plugin_mod):
    h = _host(plugin_mod, last_polled={},
              _fire_trigger=lambda *a, **k: None,
              _mirror_states=lambda *a, **k: None,
              _qp=plugin_mod.Plugin._qp,
              _qp_int=plugin_mod.Plugin._qp_int,
              _qp_float=plugin_mod.Plugin._qp_float)
    return h


def _fire(plugin_mod, host, ev, params):
    dev = _Dev(type_id="shellySmoke")
    dev.updateStatesOnServer = lambda kv: None
    qs = {k: [str(v)] for k, v in dict(params, type=ev).items()}
    plugin_mod.Plugin._apply_webhook_event(host, dev, qs)
    return host.logger


@pytest.mark.parametrize("ev,quiet,loud", [
    ("smoke", {"alarm": "false", "battery": 88}, {"alarm": "true", "battery": 88}),
    ("flood", {"flood": "false", "battery": 71}, {"flood": "true", "battery": 71}),
])
def test_a_routine_sensor_report_is_quiet_but_the_alarm_is_not(plugin_mod, ev,
                                                               quiet, loud):
    """A smoke or flood sensor reports on a timer whether or not anything is
    wrong. The all-clear is narration; the alarm is an event a person has to
    see, so it stays in the event log exactly as it was."""
    h = _webhook_receiver(plugin_mod)
    _fire(plugin_mod, h, ev, quiet)
    assert h.logger.reached_event_log == []
    assert len(h.logger.at("DEBUG")) == 1

    h2 = _webhook_receiver(plugin_mod)
    _fire(plugin_mod, h2, ev, loud)
    assert len(h2.logger.at("INFO")) == 1
    assert h2.logger.at("DEBUG") == []


def test_an_hourly_temperature_report_is_quiet(plugin_mod):
    h = _webhook_receiver(plugin_mod)
    dev = _Dev(type_id="shellyHT")
    dev.updateStatesOnServer = lambda kv: None
    plugin_mod.Plugin._apply_webhook_event(
        h, dev, {k: [str(v)] for k, v in
                 {"type": "ht", "tC": 19.4, "humidity": 55.0,
                  "battery": 90}.items()})
    assert h.logger.reached_event_log == []
    assert "HT: temp=19.4C" in h.logger.at("DEBUG")[0]


def test_a_button_press_is_quiet(plugin_mod):
    h = _webhook_receiver(plugin_mod)
    dev = _Dev(type_id="shellyI4")
    plugin_mod.Plugin._apply_webhook_event(
        h, dev, {"type": ["button"], "event": ["single"], "input_id": ["2"]})
    assert h.logger.reached_event_log == []
    assert h.logger.at("DEBUG") == ['[webhook] "Kitchen Plug" input2 single_press']


# ── the preference is real, reaches both readers, and defaults to quiet ──────

def test_the_config_field_exists_and_defaults_to_quiet():
    import xml.etree.ElementTree as ET
    root = ET.parse(CONFIG_XML).getroot()
    field = next(f for f in root.iter("Field")
                 if f.get("id") == "logActivityToEventLog")
    assert field.get("type") == "checkbox"
    assert field.get("defaultValue") == "false"


def test_closedPrefsConfigUi_mirrors_startup():
    """A pref read in __init__ and forgotten in closedPrefsConfigUi silently
    reverts to the startup value the moment the user saves the dialog."""
    src = io.open(PLUGIN_PY, encoding="utf-8").read()
    tree = ast.parse(src)
    for fname in ("__init__", "closedPrefsConfigUi"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fname)
        got = {c.value for c in ast.walk(fn)
               if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        assert "logActivityToEventLog" in got, fname


def test_a_pref_stored_as_the_string_false_reads_as_false(plugin_mod):
    """Indigo re-serialises saved dialog values, and bool("false") is True."""
    assert plugin_mod.as_bool("false", False) is False
    assert plugin_mod.as_bool("", False) is False
    assert plugin_mod.as_bool(None, False) is False
    assert plugin_mod.as_bool("true", False) is True


def test_both_readers_coerce_the_pref_through_as_bool():
    """The test above proves as_bool works; this one proves it is USED.

    A mutation sweep on 06-09-2026 swapped the __init__ read for a bare bool()
    and the suite stayed green — the helper was tested, the call site was not,
    so the "false" trap could have walked straight back in. Assert the shape of
    the ASSIGNMENT in both readers, not the presence of a word in the file.
    """
    tree = ast.parse(io.open(PLUGIN_PY, encoding="utf-8").read())
    seen = {}
    for fname in ("__init__", "closedPrefsConfigUi"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fname)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.attr for t in node.targets
                       if isinstance(t, ast.Attribute)]
            if "log_activity" not in targets:
                continue
            call = node.value
            assert isinstance(call, ast.Call), f"{fname}: not a call"
            assert isinstance(call.func, ast.Name) and call.func.id == "as_bool", (
                f"{fname}: log_activity must be coerced with as_bool, "
                f"not {ast.dump(call.func)}")
            # ... and the default must be the QUIET one.
            assert isinstance(call.args[1], ast.Constant)
            assert call.args[1].value is False, f"{fname}: default is not False"
            seen[fname] = True
    assert set(seen) == {"__init__", "closedPrefsConfigUi"}, seen


# ── a cover moving is an action, not narration ───────────────────────

def _cover_host(plugin_mod, monkeypatch, dev, raises=None):
    """A host wired to drive the real cover methods against one fake device."""
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    monkeypatch.setattr(plugin_mod.indigo.devices.__getitem__, "return_value", dev)

    def _rget(url, params=None, timeout=None):
        if raises:
            raise raises
        return _Resp({})

    h = _host(plugin_mod, last_polled={}, _rget=_rget,
              _pref_int=plugin_mod.Plugin._pref_int)
    return h, event_log


@pytest.mark.parametrize("rpc", ["Cover.Open", "Cover.Close", "Cover.Stop"])
def test_a_cover_command_stays_in_the_event_log(plugin_mod, monkeypatch, rpc):
    """Driving a motorised cover is an action on the house, so it keeps its
    event-log line whatever the narration preference says.

    These lines were never part of the problem: over 31-Aug to 05-Sep-2026 the
    plugin put 365 lines into the event log and NONE of them was a cover
    command, so quietening them saved nothing and cost the only record that
    the plugin had moved something physical.
    """
    dev = _Dev(dev_id=202, name="Landing Blind", type_id="shellyCover")
    h, event_log = _cover_host(plugin_mod, monkeypatch, dev)

    plugin_mod.Plugin._cover_cmd(h, dev.id, rpc)

    assert event_log == [("INFO", f"[Landing Blind] {rpc}")]
    assert h.logger.at("DEBUG") == []
    assert h.last_polled[dev.id] == 0        # the work still happened


def test_a_cover_command_is_loud_even_with_narration_switched_on(plugin_mod,
                                                                 monkeypatch):
    """The preference must not be able to move this line at all -- in either
    direction. Routing it through the switch would make an action on the house
    depend on a logging checkbox."""
    dev = _Dev(dev_id=202, name="Landing Blind", type_id="shellyCover")
    h, event_log = _cover_host(plugin_mod, monkeypatch, dev)
    h.log_activity = True

    plugin_mod.Plugin._cover_cmd(h, dev.id, "Cover.Open")

    assert event_log == [("INFO", "[Landing Blind] Cover.Open")]
    assert h.logger.lines == []              # nothing went near the helper


def test_a_failed_cover_command_is_still_an_ERROR(plugin_mod, monkeypatch):
    dev = _Dev(dev_id=202, name="Landing Blind", type_id="shellyCover")
    h, event_log = _cover_host(plugin_mod, monkeypatch, dev,
                               raises=RuntimeError("no route"))

    plugin_mod.Plugin._cover_cmd(h, dev.id, "Cover.Open")

    assert event_log == [("ERROR", "[202] Cover.Open failed: no route")]


def test_a_blind_sent_to_a_position_is_recorded(plugin_mod, monkeypatch):
    """A blind automated by position alone never calls Cover.Open, so if this
    line were narration there would be no event-log record of it ever moving."""
    dev = _Dev(dev_id=202, name="Landing Blind", type_id="shellyCover")
    h, event_log = _cover_host(plugin_mod, monkeypatch, dev)
    action = types.SimpleNamespace(deviceId=dev.id, props={"position": 40})

    plugin_mod.Plugin.actionCoverGoToPosition(h, action)

    assert event_log == [("INFO", "[Landing Blind] going to position 40%")]
    assert dev.written["targetPosition"] == 40


def test_a_tilt_change_is_recorded(plugin_mod, monkeypatch):
    dev = _Dev(dev_id=202, name="Landing Blind", type_id="shellyCover")
    h, event_log = _cover_host(plugin_mod, monkeypatch, dev)
    action = types.SimpleNamespace(deviceId=dev.id, props={"tilt": 75})

    plugin_mod.Plugin.actionCoverSetTilt(h, action)

    assert event_log == [("INFO", "[Landing Blind] tilt set to 75%")]
    assert dev.written["tiltTargetPosition"] == 75


def test_no_cover_method_routes_through_the_narration_switch():
    """Structural, because the behavioural tests above only cover the paths a
    test happens to drive. A later logging tidy-up must not be able to put
    these back behind the preference without this failing.
    """
    tree = ast.parse(io.open(PLUGIN_PY, encoding="utf-8").read())
    checked = set()
    for fname in ("_cover_cmd", "actionCoverGoToPosition", "actionCoverSetTilt"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fname)
        called = {n.func.attr for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert "_log_activity" not in called, fname
        plain = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "log"]
        assert plain, f"{fname}: no log() call found -- the scan is vacuous"
        checked.add(fname)
    assert len(checked) == 3, checked


# ── nothing was demoted ──────────────────────────────────────────────────────

def test_every_fault_still_goes_through_a_route_that_reaches_the_event_log():
    """Scan the module for calls to log(..., level="WARNING"/"ERROR") and to
    logger.warning/error, and assert the count has not fallen. The measured
    baseline is what the plugin carried before the quietening pass; a future
    edit that quietly turns a fault into narration drops below it.
    """
    tree = ast.parse(io.open(PLUGIN_PY, encoding="utf-8").read())
    fault_sites = 0
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        if isinstance(n.func, ast.Name) and n.func.id == "log":
            for kw in n.keywords:
                if (kw.arg == "level" and isinstance(kw.value, ast.Constant)
                        and kw.value.value in ("WARNING", "ERROR", "CRITICAL")):
                    fault_sites += 1
        elif (isinstance(n.func, ast.Attribute)
              and n.func.attr in ("warning", "error", "critical")):
            fault_sites += 1
    # 77 fault sites, counted with this very algorithm on 06-09-2026: 69
    # log(..., level=) calls plus 8 logger.warning/error attribute calls. The
    # same count run over the pre-quietening commit (396fcc8) is also 77, which
    # is the evidence that the pass demoted nothing.
    #
    # The floor was first written as 62 -- 15 below the truth, so the guard
    # could have lost a quarter of the plugin's faults and still passed. A
    # tripwire set below the real value cannot fire; re-measure it here rather
    # than carrying a remembered number forward.
    assert fault_sites >= 77, fault_sites
