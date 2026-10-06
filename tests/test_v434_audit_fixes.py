#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v434_audit_fixes.py
# Description: Regression tests for the three faults the 05-10-2026 audit found.
#              SD-1: commands went to the stored address even when the identity
#              check had POSITIVELY found a different Shelly answering there, so
#              an address clash (July, one address held by two Indigo devices) would switch the wrong
#              plug. A check that merely could not be done must still let the
#              command through. SD-3: the webhook listener wrote states and
#              fired button triggers for a DISABLED device. SD-2: the energy
#              file was truncated and rewritten in place, so a crash or a full
#              disk mid-write left it empty.
# Author:      CliveS & Claude Opus 5.5
# Date:        05-10-2026
# Version:     1.0

from __future__ import annotations

import ast
import io
import json
import os
import stat
import threading
import types
from pathlib import Path

import pytest

from test_mac_identity import make_plugin

SERVER_DIR = (Path(__file__).resolve().parent.parent
              / "ShellyDirect.indigoPlugin" / "Contents" / "Server Plugin")
PLUGIN_PY  = SERVER_DIR / "plugin.py"

LIVE_DEVICE_ACTION = types.SimpleNamespace(
    TurnOn=4, TurnOff=5, Toggle=6, SetBrightness=7, BrightenBy=8, DimBy=9,
    SetColorLevels=10, RequestStatus=11)

STORED_IP  = "192.168.1.50"
STORED_MAC = "AABBCC000001"
OTHER_MAC  = "AABBCC000002"


class _Logger:
    def __init__(self):
        self.lines = []

    def debug(self, msg, *a, **k):   self.lines.append(("DEBUG", str(msg)))
    def info(self, msg, *a, **k):    self.lines.append(("INFO", str(msg)))
    def warning(self, msg, *a, **k): self.lines.append(("WARNING", str(msg)))
    def error(self, msg, *a, **k):   self.lines.append(("ERROR", str(msg)))


class _Dev:
    def __init__(self, dev_id=101, name="Kitchen Plug", type_id="shellyRelay",
                 on=False, enabled=True, configured=True):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = enabled
        self.configured   = configured
        self.onState      = on
        self.pluginId     = "com.clives.indigoplugin.shellydirect"
        self.states       = {"brightnessLevel": 50, "deviceOnline": True}
        self.pluginProps  = {"ip_address": STORED_IP, "channel_id": "0",
                             "mac_address": STORED_MAC}
        self.written      = {}

    def updateStateOnServer(self, key, value, **k):
        self.written[key] = value
        self.states[key] = value


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {}


@pytest.fixture
def host(plugin_mod, monkeypatch):
    """A bare host with the SHIPPED action handlers and command gate bound."""
    monkeypatch.setattr(plugin_mod.indigo, "kDeviceAction", LIVE_DEVICE_ACTION,
                        raising=False)
    event_log, sent = [], []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, str(msg))))
    h = types.SimpleNamespace(
        logger=_Logger(), log_activity=False, last_polled={},
        _identity_bad={}, _identity_bad_ip={}, _rgbw_profile={},
        event_log=event_log, sent=sent, polled=[])
    h._pref_int = plugin_mod.Plugin._pref_int          # a staticmethod
    for name in ("_command_ip", "_log_activity", "_set_output",
                 "_switch_set", "_light_set", "_cover_cmd", "_cover_standard_action"):
        setattr(h, name, getattr(plugin_mod.Plugin, name).__get__(h))
    h._rgbw_set_component = lambda d, ip: "RGBW"
    h._rgbw_component     = lambda d, ip: "rgb"
    h._poll_device        = lambda d: h.polled.append(d.id)
    h._poll_cover         = lambda d: h.polled.append(d.id)

    def _rcommand(url, params=None):
        sent.append(url)
        return _Resp()
    h._rcommand = _rcommand
    return h


@pytest.fixture
def logged(plugin_mod, monkeypatch):
    lines = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": lines.append((level, msg)))
    return lines


def _flag_wrong(h, dev, at=STORED_IP):
    h._identity_bad[dev.id]    = OTHER_MAC
    h._identity_bad_ip[dev.id] = at


def _devices(monkeypatch, plugin_mod, dev):
    monkeypatch.setattr(plugin_mod.indigo, "devices", {dev.id: dev})


def _action(**kw):
    return types.SimpleNamespace(**kw)


# ── SD-1: a confirmed wrong Shelly at the address blocks commands ───────────

def test_relay_on_is_sent_when_identity_is_merely_unverified(plugin_mod, host):
    dev = _Dev()
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=4), dev)
    assert host.sent == [f"http://{STORED_IP}/rpc/Switch.Set"]
    assert dev.written["onOffState"] is True


def test_relay_on_is_refused_when_another_shelly_answers_there(plugin_mod, host):
    dev = _Dev()
    _flag_wrong(host, dev)
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=4), dev)
    assert host.sent == []
    assert "onOffState" not in dev.written
    warnings = [m for lvl, m in host.event_log if lvl == "WARNING"]
    assert len(warnings) == 1
    assert dev.name in warnings[0]
    assert STORED_IP in warnings[0]
    assert OTHER_MAC in warnings[0]
    assert "different Shelly" in warnings[0]


def test_toggle_and_off_are_refused_too(plugin_mod, host):
    dev = _Dev(on=True)
    _flag_wrong(host, dev)
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=5), dev)
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=6), dev)
    assert host.sent == []


def test_status_request_is_not_refused(plugin_mod, host):
    # A status request reads; it goes through the poll gate, which refuses to
    # write for the wrong box by itself.
    dev = _Dev()
    _flag_wrong(host, dev)
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=11), dev)
    assert host.polled == [dev.id]
    assert [m for lvl, m in host.event_log if lvl == "WARNING"] == []


def test_a_corrected_address_is_not_held_against_the_device(plugin_mod, host):
    # The mismatch was seen at the OLD address; the user has since typed the
    # right one, so nothing is known to be wrong at the address now stored.
    dev = _Dev()
    _flag_wrong(host, dev, at="192.168.1.99")
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=4), dev)
    assert host.sent == [f"http://{STORED_IP}/rpc/Switch.Set"]


def test_dimmer_actions_are_refused(plugin_mod, host):
    dev = _Dev(type_id="shellyDimmer")
    _flag_wrong(host, dev)
    for act in (4, 5, 6):
        plugin_mod.Plugin.actionControlDimmer(host, _action(deviceAction=act), dev)
    plugin_mod.Plugin.actionControlDimmer(
        host, _action(deviceAction=7, actionValue=40), dev)
    assert host.sent == []
    assert dev.written == {}


def test_dimmer_action_is_sent_when_identity_is_fine(plugin_mod, host):
    dev = _Dev(type_id="shellyDimmer")
    plugin_mod.Plugin.actionControlDimmer(
        host, _action(deviceAction=7, actionValue=40), dev)
    assert host.sent == [f"http://{STORED_IP}/rpc/Light.Set"]


@pytest.mark.parametrize("method,props", [
    ("actionOnForSeconds",      {"seconds": "5"}),
    ("actionCoverOpen",         {}),
    ("actionCoverClose",        {}),
    ("actionCoverStop",         {}),
    ("actionCoverGoToPosition", {"position": "40"}),
    ("actionCoverSetTilt",      {"tilt": "40"}),
    ("actionSetBrightness",     {"brightness": "40"}),
    ("actionSetColor",          {"red": "10", "green": "20", "blue": "30"}),
])
def test_custom_actions_are_refused(plugin_mod, host, monkeypatch, method, props):
    dev = _Dev(type_id="shellyRGBW" if "Color" in method or "Brightness" in method
               else "shellyCover" if "Cover" in method else "shellyRelay")
    _devices(monkeypatch, plugin_mod, dev)
    _flag_wrong(host, dev)
    getattr(plugin_mod.Plugin, method)(host, _action(deviceId=dev.id, props=props))
    assert host.sent == []
    warnings = [m for lvl, m in host.event_log if lvl == "WARNING"]
    assert len(warnings) == 1 and STORED_IP in warnings[0]


@pytest.mark.parametrize("method,props", [
    ("actionOnForSeconds",      {"seconds": "5"}),
    ("actionCoverOpen",         {}),
    ("actionCoverGoToPosition", {"position": "40"}),
    ("actionCoverSetTilt",      {"tilt": "40"}),
    ("actionSetBrightness",     {"brightness": "40"}),
    ("actionSetColor",          {"red": "10", "green": "20", "blue": "30"}),
])
def test_custom_actions_still_send_when_identity_is_unverified(
        plugin_mod, host, monkeypatch, method, props):
    dev = _Dev(type_id="shellyRGBW" if "Color" in method or "Brightness" in method
               else "shellyCover" if "Cover" in method else "shellyRelay")
    _devices(monkeypatch, plugin_mod, dev)
    getattr(plugin_mod.Plugin, method)(host, _action(deviceId=dev.id, props=props))
    assert len(host.sent) == 1 and host.sent[0].startswith(f"http://{STORED_IP}/")


def test_cover_standard_action_is_refused(plugin_mod, host, monkeypatch):
    dev = _Dev(type_id="shellyCover")
    _devices(monkeypatch, plugin_mod, dev)
    _flag_wrong(host, dev)
    plugin_mod.Plugin.actionControlDevice(host, _action(deviceAction=4), dev)
    assert host.sent == []


def test_mismatch_records_where_it_was_seen_and_clearing_forgets_it(plugin_mod, logged):
    p = make_plugin(plugin_mod)
    dev = types.SimpleNamespace(id=7, name="Garage Plug",
                                pluginProps={"ip_address": STORED_IP,
                                             "mac_address": STORED_MAC})
    p._identity_mismatch(dev, STORED_IP, OTHER_MAC)
    assert p._identity_bad == {7: OTHER_MAC}
    assert p._identity_bad_ip == {7: STORED_IP}
    p._identity_cleared(dev)
    assert p._identity_bad == {} and p._identity_bad_ip == {}


def test_poll_gate_mismatch_then_relocation_lets_commands_resume(plugin_mod, logged):
    """End to end on the shipped identity code: the poll finds the wrong box,
    commands are refused; mDNS then finds the device elsewhere, the gate moves
    it, and commands go to the new address."""
    new_ip = "192.168.1.77"
    p = make_plugin(plugin_mod, macs_at={STORED_IP: OTHER_MAC, new_ip: STORED_MAC})
    dev = types.SimpleNamespace(id=9, name="Fridge Plug", deviceTypeId="shellyRelay",
                                pluginProps={"ip_address": STORED_IP,
                                             "mac_address": STORED_MAC})

    def _store(props):
        dev.pluginProps = dict(props)
    dev.replacePluginPropsOnServer = _store

    assert p._target_ip(dev) is None
    assert p._command_ip(dev, "on") is None

    with p._mdns_lock:
        p._mdns_map[STORED_MAC] = (new_ip, 0, 0)
    p._confirm_attempt.clear()
    assert p._target_ip(dev) == new_ip
    assert p._command_ip(dev, "on") == new_ip


def test_no_direct_writes_to_identity_bad_outside_the_flagging_helper():
    """Both places that find a wrong box must record WHERE they found it, or
    the command gate cannot tell a stale flag from a live one."""
    tree = ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))
    offenders = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name == "_flag_identity_bad":
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if (isinstance(t, ast.Subscript)
                            and isinstance(t.value, ast.Attribute)
                            and t.value.attr == "_identity_bad"):
                        offenders.append(f"{fn.name}:{node.lineno}")
    assert offenders == []


# ── SD-3: the webhook listener ignores disabled devices ─────────────────────

@pytest.fixture
def handler_cls(plugin_mod, monkeypatch):
    """The real WebhookHandler class from _start_webhook_server, captured
    without binding a socket or starting a thread."""
    captured = {}

    def _fake_tcp_init(self, addr, handler, *a, **k):
        captured["cls"] = handler

    monkeypatch.setattr(plugin_mod.socketserver.TCPServer, "__init__", _fake_tcp_init)
    monkeypatch.setattr(plugin_mod.threading, "Thread",
                        lambda *a, **k: types.SimpleNamespace(start=lambda: None))
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    owner = types.SimpleNamespace(webhook_port=0)
    plugin_mod.Plugin._start_webhook_server(owner)
    return captured["cls"]


def _webhook_plugin(plugin_mod, applied):
    p = types.SimpleNamespace(
        logger=_Logger(), last_seen={}, webhook_source_check=True,
        _mdns_lock=threading.RLock(), _mdns_map={}, repairs=[])
    p._webhook_source_ok    = plugin_mod.Plugin._webhook_source_ok.__get__(p)
    p._link_live_for        = lambda d: False
    p._note_back_online     = lambda *a: None
    p._apply_webhook_event  = lambda d, params: applied.append(("get", d.id))
    p._process_blu_event    = lambda d, payload: applied.append(("post", d.id))
    p._repair_stale_webhook = lambda *a, **k: p.repairs.append(a)
    p._refuse_foreign_webhook = lambda *a: applied.append(("foreign",))
    return p


def _call(handler_cls, method, path, body=b""):
    h = object.__new__(handler_cls)
    h.path           = path
    h.client_address = (STORED_IP, 12345)
    h.headers        = {"Content-Length": str(len(body))}
    h.rfile          = io.BytesIO(body)
    h.wfile          = io.BytesIO()
    h.codes          = []
    h.send_response  = lambda code, *a: h.codes.append(code)
    h.end_headers    = lambda: None
    getattr(h, method)()
    return h.codes


@pytest.mark.parametrize("enabled,configured", [(False, True), (True, False)])
def test_webhook_get_for_an_inactive_device_writes_nothing(
        plugin_mod, handler_cls, monkeypatch, enabled, configured):
    applied = []
    plugin = _webhook_plugin(plugin_mod, applied)
    dev = _Dev(enabled=enabled, configured=configured)
    dev.states["deviceOnline"] = False
    _devices(monkeypatch, plugin_mod, dev)
    # The handler class closes over `plugin`; rebuild it with ours.
    cls = _rebind(handler_cls, plugin)
    codes = _call(cls, "do_GET", f"/shellyEvent?devId={dev.id}&type=button&event=single")
    assert codes == [200]
    assert applied == []
    assert dev.written == {}
    assert plugin.repairs == []
    assert plugin.last_seen == {}


def test_webhook_get_for_an_enabled_device_is_applied(plugin_mod, handler_cls, monkeypatch):
    applied = []
    plugin = _webhook_plugin(plugin_mod, applied)
    dev = _Dev()
    _devices(monkeypatch, plugin_mod, dev)
    cls = _rebind(handler_cls, plugin)
    codes = _call(cls, "do_GET", f"/shellyEvent?devId={dev.id}&type=switch&state=on")
    assert codes == [200]
    assert applied == [("get", dev.id)]


def test_webhook_post_for_a_disabled_blu_device_is_ignored(
        plugin_mod, handler_cls, monkeypatch):
    applied = []
    plugin = _webhook_plugin(plugin_mod, applied)
    dev = _Dev(type_id="shellyBluButton", enabled=False)
    _devices(monkeypatch, plugin_mod, dev)
    cls = _rebind(handler_cls, plugin)
    body = json.dumps({"event": "single_push"}).encode()
    codes = _call(cls, "do_POST", f"/shellyBluEvent?devId={dev.id}", body)
    assert codes == [200]
    assert applied == []
    assert plugin.repairs == []


def test_webhook_post_for_an_enabled_blu_device_is_processed(
        plugin_mod, handler_cls, monkeypatch):
    applied = []
    plugin = _webhook_plugin(plugin_mod, applied)
    dev = _Dev(type_id="shellyBluButton")
    _devices(monkeypatch, plugin_mod, dev)
    cls = _rebind(handler_cls, plugin)
    body = json.dumps({"event": "single_push"}).encode()
    codes = _call(cls, "do_POST", f"/shellyBluEvent?devId={dev.id}", body)
    assert codes == [200]
    assert applied == [("post", dev.id)]


def _rebind(handler_cls, plugin):
    """Copy the handler's methods onto a class whose closure cell holds `plugin`."""
    import types as _t
    ns = {}
    for name in ("do_GET", "do_POST"):
        fn = handler_cls.__dict__[name]
        cells = []
        for var, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ()):
            cells.append(_t.CellType(plugin) if var == "plugin" else cell)
        ns[name] = _t.FunctionType(fn.__code__, fn.__globals__, name,
                                   fn.__defaults__, tuple(cells))
    return type("Rebound", (handler_cls,), ns)


# ── SD-2: the energy file is replaced atomically ────────────────────────────

def _energy_host(plugin_mod, path, data, event_log):
    h = types.SimpleNamespace(energy_data=data, _energy_lock=threading.RLock(),
                              _energy_save_lock=threading.Lock(), logger=_Logger())
    h._energy_data_path = lambda: str(path)
    return h


def test_energy_save_never_exposes_a_partial_file_and_keeps_the_mode(
        plugin_mod, tmp_path, monkeypatch):
    path = tmp_path / "energy_data.json"
    path.write_text(json.dumps({"old": 1}), encoding="utf-8")
    os.chmod(path, 0o640)
    event_log, seen_during_write = [], []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, msg)))
    real_fsync = os.fsync

    def _fsync(fd):
        # At the moment the new bytes are being flushed, the real file must
        # still hold the whole OLD content.
        seen_during_write.append(json.loads(path.read_text(encoding="utf-8")))
        return real_fsync(fd)
    monkeypatch.setattr(plugin_mod.os, "fsync", _fsync)

    h = _energy_host(plugin_mod, path, {"new": 2}, event_log)
    plugin_mod.Plugin._save_energy_data(h)

    assert seen_during_write == [{"old": 1}]
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": 2}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640
    assert sorted(p.name for p in tmp_path.iterdir()) == ["energy_data.json"]
    assert event_log == []


def test_a_failed_energy_save_leaves_the_old_file_whole(plugin_mod, tmp_path, monkeypatch):
    path = tmp_path / "energy_data.json"
    path.write_text(json.dumps({"old": 1}), encoding="utf-8")
    event_log = []
    monkeypatch.setattr(plugin_mod, "log",
                        lambda msg, level="INFO": event_log.append((level, msg)))

    def _full_disk(fd):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(plugin_mod.os, "fsync", _full_disk)

    h = _energy_host(plugin_mod, path, {"new": 2}, event_log)
    plugin_mod.Plugin._save_energy_data(h)

    assert json.loads(path.read_text(encoding="utf-8")) == {"old": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["energy_data.json"]
    assert [lvl for lvl, _ in event_log] == ["WARNING"]


def test_first_energy_save_creates_a_readable_file(plugin_mod, tmp_path, monkeypatch):
    path = tmp_path / "energy_data.json"
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    h = _energy_host(plugin_mod, path, {"new": 2}, [])
    plugin_mod.Plugin._save_energy_data(h)
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": 2}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
