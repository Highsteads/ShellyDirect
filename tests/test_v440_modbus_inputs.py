#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v440_modbus_inputs.py
# Description: Contract tests for v4.4.0 Gen 4 input states. The Modbus reader
#              is checked byte by byte against a fake Shelly (both byte orders
#              for the MAC, a wrong MAC, exception replies, a reply for another
#              request, fragments, timeouts), and the poll logic is checked
#              never to write an input it could not read.
# Author:      CliveS & Claude
# Date:        02-11-2026
# Version:     1.0

from __future__ import annotations

import struct

import pytest

MAC = "A085E3BD3928"


# ── A fake Shelly Modbus server, one socket ──────────────────────────────────

class FakeModbusSocket:
    def __init__(self, inputs=None, mac=MAC, swapped=False, fault=None):
        self.inputs   = inputs or {}       # {address: bool}
        self.mac      = mac
        self.swapped  = swapped
        self.fault    = fault
        self.pending  = b""
        self.requests = []
        self.sent_raw = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, _seconds):
        pass

    def sendall(self, data):
        self.sent_raw.append(bytes(data))
        tid, proto, length, unit, fn, addr, count = struct.unpack(">HHHBBHH", data)
        assert (proto, length, unit) == (0, 6, 1)
        self.requests.append((fn, addr, count))
        if fn == 4:
            payload = self.mac.encode("ascii")
            if self.swapped:
                payload = b"".join(payload[i:i + 2][::-1] for i in range(0, 12, 2))
        elif fn == 2:
            payload = bytes([1 if self.inputs.get(addr) else 0])
        else:
            raise AssertionError(f"plugin sent function {fn}: it must only read")
        pdu = bytes([fn, len(payload)]) + payload
        if self.fault == "exception":
            pdu = bytes([fn | 0x80, 2])
        if self.fault == "other_tid":
            tid += 1
        if self.fault == "short_data":
            pdu = bytes([fn, len(payload)]) + payload[:-1]
        self.pending += struct.pack(">HHHB", tid, 0, len(pdu) + 1, 1) + pdu

    def recv(self, size):
        if self.fault == "timeout":
            raise TimeoutError("simulated")
        if self.fault == "closed":
            return b""
        chunk, self.pending = self.pending[:min(size, 3)], self.pending[min(size, 3):]
        return chunk      # TCP may hand the reply over in pieces


def _connector(sock):
    seen = {}

    def connect(addr, timeout=None):
        seen["addr"] = addr
        return sock
    return connect, seen


# ── Register map (Shelly Input / Modbus API) ─────────────────────────────────

def test_input_address_formula(plugin_mod):
    assert plugin_mod.modbus_input_address(0) == 100
    assert plugin_mod.modbus_input_address(1) == 110       # Shelly's own example
    with pytest.raises(ValueError):
        plugin_mod.modbus_input_address(-1)
    with pytest.raises(ValueError):
        plugin_mod.modbus_input_address(7000)


def test_request_bytes(plugin_mod):
    assert plugin_mod.modbus_request(1, 4, 0, 6) == bytes.fromhex("000100000006010400000006")
    assert plugin_mod.modbus_request(2, 2, 110, 1) == bytes.fromhex("0002000000060102006e0001")


# ── The reader ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("swapped", [False, True])
@pytest.mark.parametrize("held", [False, True])
def test_reads_inputs_after_checking_the_mac(plugin_mod, swapped, held):
    sock = FakeModbusSocket(inputs={100: held, 110: not held}, swapped=swapped)
    connect, seen = _connector(sock)
    got = plugin_mod.modbus_read_inputs("192.168.1.80", "a0:85:e3:bd:39:28", [1, 0],
                                        connect=connect)
    assert got == {0: held, 1: not held}
    assert seen["addr"] == ("192.168.1.80", 502)
    assert sock.requests == [(4, 0, 6), (2, 100, 1), (2, 110, 1)]


def test_only_read_functions_are_ever_sent(plugin_mod):
    sock = FakeModbusSocket(inputs={100: True})
    connect, _ = _connector(sock)
    plugin_mod.modbus_read_inputs("h", MAC, [0], connect=connect)
    assert {fn for fn, _a, _c in sock.requests} <= {2, 4}


def test_a_different_shelly_is_refused_before_any_input_is_read(plugin_mod):
    sock = FakeModbusSocket(inputs={100: True}, mac="AABBCC000011")
    connect, _ = _connector(sock)
    with pytest.raises(plugin_mod.ModbusError, match="is not"):
        plugin_mod.modbus_read_inputs("h", MAC, [0], connect=connect)
    assert sock.requests == [(4, 0, 6)]


@pytest.mark.parametrize("fault", ["exception", "other_tid", "short_data", "timeout", "closed"])
def test_a_bad_reply_never_becomes_a_reading(plugin_mod, fault):
    sock = FakeModbusSocket(inputs={100: False}, fault=fault)
    connect, _ = _connector(sock)
    with pytest.raises((plugin_mod.ModbusError, OSError)):
        plugin_mod.modbus_read_inputs("h", MAC, [0], connect=connect)


def test_no_stored_mac_means_no_read(plugin_mod):
    sock = FakeModbusSocket()
    connect, _ = _connector(sock)
    with pytest.raises(ValueError):
        plugin_mod.modbus_read_inputs("h", "", [0], connect=connect)
    assert sock.requests == []


# ── The poll logic ───────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body       = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)


class FakeDev:
    def __init__(self, type_id="shellyRelay", channel="0", mac=MAC, dev_id=1):
        self.id           = dev_id
        self.name         = "Hall Light"
        self.deviceTypeId = type_id
        self.pluginProps  = {"ip_address": "192.168.1.80", "channel_id": channel,
                             "mac_address": mac}


class _Logger:
    def __init__(self):
        self.lines = []

    def debug(self, msg):
        self.lines.append(msg)


@pytest.fixture
def host(plugin_mod, monkeypatch):
    """A Plugin with the Gen 4 input caches, a scripted Shelly and captured writes."""
    p = object.__new__(plugin_mod.Plugin)
    p.logger          = _Logger()
    p._gen_cache      = {}
    p._input_cfg      = {}
    p._modbus_cfg     = {}
    p._modbus_backoff = {}
    p._modbus_warned  = set()
    p._components     = {}
    p.shelly          = {"gen": 4, "inputs": {0: {"state": None, "type": "button"}},
                         "modbus": True}
    p.writes          = []
    p.modbus_calls    = []
    p.modbus_result   = {0: True}

    def _rget(url, params=None, timeout=None):
        sh = p.shelly
        if "Shelly.GetDeviceInfo" in url:
            return FakeResp(200, {"gen": sh["gen"], "mac": MAC})
        if "Shelly.GetConfig" in url:
            return FakeResp(200, {f"input:{i}": {} for i in sh["inputs"]} | {"switch:0": {}})
        if "Modbus.GetConfig" in url:
            return FakeResp(200, {"enable": sh["modbus"]})
        i = int(url.rsplit("=", 1)[1]) if "id=" in url else 0
        if "Input.GetStatus" in url:
            return FakeResp(200, {"id": i, "state": sh["inputs"][i]["state"]})
        if "Input.GetConfig" in url:
            return FakeResp(200, {"id": i, "type": sh["inputs"][i]["type"],
                                  "enable": True, "invert": sh["inputs"][i].get("invert", False)})
        return FakeResp(404)

    def _read(ip, mac, ids, **kw):
        p.modbus_calls.append((ip, mac, list(ids)))
        if isinstance(p.modbus_result, Exception):
            raise p.modbus_result
        return {i: p.modbus_result[i] for i in ids}

    p._rget = _rget
    p._capture_unhandled_fields = lambda dev, fields, extra_handled=None: p.writes.append(dict(fields))
    monkeypatch.setattr(plugin_mod, "modbus_read_inputs", _read)
    monkeypatch.setattr(plugin_mod, "log", lambda msg, level="INFO": p.writes.append({"LOG": (level, msg)}))
    return p


def test_gen4_button_is_read_over_modbus(host):
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert host.writes == [{"input0": True, "inputReadVia": "Modbus"}]
    assert host.modbus_calls == [("192.168.1.80", MAC, [0])]


def test_switch_type_input_uses_the_rpc_state_and_no_modbus(host):
    host.shelly["inputs"][0] = {"state": False, "type": "switch"}
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert host.writes == [{"input0": False, "inputReadVia": "Shelly"}]
    assert host.modbus_calls == []


def test_modbus_off_writes_no_input_value(host):
    """An unreadable button is not shown as off."""
    host.shelly["modbus"] = False
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert host.writes == [{"inputReadVia": "button presses"}]
    assert host.modbus_calls == []


def test_inverted_button_is_not_read_over_modbus(host):
    host.shelly["inputs"][0] = {"state": None, "type": "button", "invert": True}
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert host.writes == []
    assert host.modbus_calls == []


@pytest.mark.parametrize("gen", [2, 3])
def test_older_generations_are_left_alone(host, gen):
    host.shelly["gen"] = gen
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert host.writes == [] and host.modbus_calls == []


def test_other_device_types_are_left_alone(host):
    host._poll_inputs(FakeDev(type_id="shellyI4"), "192.168.1.80")
    assert host.writes == [] and host.modbus_calls == []


def test_relay_owns_only_its_own_channels_input(host):
    host.shelly["inputs"] = {0: {"state": True, "type": "switch"},
                             1: {"state": False, "type": "switch"}}
    host._poll_inputs(FakeDev(channel="1"), "192.168.1.80")
    assert host.writes == [{"input1": False, "inputReadVia": "Shelly"}]


def test_dimmer_owns_every_input(host):
    host.shelly["inputs"] = {0: {"state": True, "type": "switch"},
                             1: {"state": False, "type": "switch"}}
    host._poll_inputs(FakeDev(type_id="shellyDimmer"), "192.168.1.80")
    assert host.writes == [{"input0": True, "input1": False, "inputReadVia": "Shelly"}]


def test_failed_modbus_read_backs_off_and_writes_no_value(host, plugin_mod):
    host.modbus_result = TimeoutError("no answer")
    host._poll_inputs(FakeDev(), "192.168.1.80")
    host._poll_inputs(FakeDev(), "192.168.1.80")
    assert len(host.modbus_calls) == 1                     # second poll backs off
    assert all("input0" not in w for w in host.writes)


def test_wrong_shelly_on_modbus_warns_once(host, plugin_mod):
    host.modbus_result = plugin_mod.ModbusError("the Shelly answering Modbus at x is not y")
    host._poll_inputs(FakeDev(), "192.168.1.80")
    host._modbus_backoff.clear()
    host._poll_inputs(FakeDev(), "192.168.1.80")
    warnings = [w["LOG"] for w in host.writes if "LOG" in w and w["LOG"][0] == "WARNING"]
    assert len(warnings) == 1


def test_a_poll_input_error_never_escapes(host):
    def boom(*a, **k):
        raise RuntimeError("network fell over")
    host._rget = boom
    host._poll_inputs(FakeDev(), "192.168.1.80")          # must not raise


def test_live_button_edges_set_the_state(host):
    host._gen_cache["192.168.1.80"] = (1e12, 4)
    devs = [FakeDev(channel="0"), FakeDev(channel="1", dev_id=2)]
    host._link_event(devs, {"component": "input:0", "event": "btn_down"}, "192.168.1.80")
    host._link_event(devs, {"component": "input:0", "event": "btn_up"}, "192.168.1.80")
    assert host.writes == [{"input0": True, "inputReadVia": "button presses"},
                           {"input0": False, "inputReadVia": "button presses"}]


def test_live_edges_ignored_until_the_generation_is_known(host):
    host._link_event([FakeDev()], {"component": "input:0", "event": "btn_down"}, "192.168.1.80")
    assert host.writes == []


def test_live_switch_input_status_sets_the_state(host):
    host._gen_cache["192.168.1.80"] = (1e12, 4)
    host._link_devices      = lambda ip: [FakeDev(channel="0")]
    host._link_identity_ok  = lambda ip, msg, devs: True
    host._link_status, host._link_dirty, host._link_applied = {}, {}, {}
    host._stopping = False
    host._on_link_message("192.168.1.80", {"method": "NotifyStatus",
                                           "params": {"input:0": {"id": 0, "state": True}}})
    host._on_link_message("192.168.1.80", {"method": "NotifyStatus",
                                           "params": {"input:0": {"id": 0, "state": None}}})
    assert host.writes == [{"input0": True, "inputReadVia": "Shelly"}]    # null ignored
