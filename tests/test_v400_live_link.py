#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v400_live_link.py
# Description: Tests for the v4.0.0 live connection: the websocket session loop
#              (against a fake socket), noise filtering, identity by the MAC in
#              `src`, routing pushed deltas to the right device and channel,
#              rate-limiting pushed power readings, button presses fired from
#              NotifyEvent, and the webhook ignored while the link is live.
#              Message shapes are the ones captured live from a Plus Plug UK on
#              2.0.1 firmware on 26-09-2026.
# Author:      CliveS & Claude Opus 5.5
# Date:        26-09-2026
# Version:     1.0

from __future__ import annotations

import json
import types

import pytest


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay", ip="192.168.1.13",
                 chan="0", mac="CC7B5C8A5138", states=None):
        self.id, self.name, self.deviceTypeId = dev_id, name, type_id
        self.enabled = self.configured = True
        self.pluginProps = {"ip_address": ip, "channel_id": chan, "mac_address": mac,
                            "has_pm": True}
        self.states = dict(states or {})


SRC = "shellypluspluguk-cc7b5c8a5138"
FULL = {"id": 1, "src": SRC, "result": {
    "switch:0": {"id": 0, "source": "init", "output": True, "apower": 32.6,
                 "voltage": 255.1, "current": 0.16, "aenergy": {"total": 521217.8},
                 "temperature": {"tC": 43.6}},
    "sys": {"uptime": 10}}}
POWER_ONLY = {"src": SRC, "method": "NotifyStatus",
              "params": {"ts": 1790462160.61, "switch:0": {"apower": 34.8}}}
SWITCHED_OFF = {"src": SRC, "method": "NotifyStatus",
                "params": {"ts": 1790462170.0, "switch:0": {"output": False, "source": "button"}}}
BUTTON = {"src": "shelly1minig4-7c2c6774c698", "method": "NotifyEvent",
          "params": {"ts": 1.0, "events": [{"component": "input:0", "id": 0,
                                            "event": "double_push", "ts": 1.0}]}}


class _Devices:
    """indigo.devices as the code uses it: iter() and [id]."""

    def __init__(self, devices, by_id):
        self._devices, self._by_id = devices, by_id

    def iter(self, *a, **k):
        return list(self._devices)

    def __getitem__(self, dev_id):
        return self._by_id[dev_id]


def _host(plugin_mod, devices, monkeypatch):
    by_id = {d.id: d for d in devices}
    monkeypatch.setattr(plugin_mod.indigo, "devices", _Devices(devices, by_id))
    monkeypatch.setattr(plugin_mod, "log", lambda *a, **k: None)
    host = types.SimpleNamespace(_link_status={}, _link_dirty={}, _link_applied={},
                                 _link_warned=set(), applied=[], polled=[], online=[],
                                 fired=[], logger=types.SimpleNamespace(debug=lambda *a, **k: None),
                                 log_activity=False)
    host._pref_int = plugin_mod.Plugin._pref_int
    host._log_activity = plugin_mod.Plugin._log_activity.__get__(host)
    for name in ("_link_devices", "_link_identity_ok", "_on_link_message", "_link_event",
                 "_apply_link_updates"):
        setattr(host, name, getattr(plugin_mod.Plugin, name).__get__(host))
    host._apply_relay_status = lambda dev, data, ip=None: host.applied.append((dev.id, dict(data)))
    host._poll_device = lambda dev: host.polled.append(dev.id)
    host._mark_online = lambda dev: host.online.append(dev.id)
    host._fire_trigger = lambda t, d, p=None: host.fired.append((t, d, p))
    return host


# ── merging deltas ───────────────────────────────────────────────────────────

def test_a_delta_is_laid_over_the_cached_status(plugin_mod):
    cached = FULL["result"]["switch:0"]
    merged = plugin_mod.merge_status(cached, {"apower": 34.8, "aenergy": {"total": 521300.0}})
    assert merged["apower"] == 34.8 and merged["output"] is True
    assert merged["aenergy"] == {"total": 521300.0}
    assert merged["temperature"] == {"tC": 43.6}


def test_components_follow_the_channel(plugin_mod):
    assert plugin_mod.link_components("shellyRelay", 1) == ("switch:1",)
    assert "input:3" in plugin_mod.link_components("shellyI4", 0)


# ── routing ──────────────────────────────────────────────────────────────────

def test_the_full_status_is_applied_on_the_next_tick(plugin_mod, monkeypatch):
    plug = FakeDev(1, "NAS Plug")
    host = _host(plugin_mod, [plug], monkeypatch)
    host._on_link_message("192.168.1.13", FULL)
    assert host._link_status[1]["apower"] == 32.6
    host._apply_link_updates(1000.0)
    assert host.applied and host.applied[0][0] == 1


def test_power_alone_waits_but_a_switch_is_applied_at_once(plugin_mod, monkeypatch):
    plug = FakeDev(1, "NAS Plug")
    host = _host(plugin_mod, [plug], monkeypatch)
    host._on_link_message("192.168.1.13", FULL)
    host._apply_link_updates(1000.0)
    host.applied.clear()
    host._on_link_message("192.168.1.13", POWER_ONLY)
    assert host.applied == [], "a power change alone is not written straight away"
    host._apply_link_updates(1000.0 + plugin_mod.LINK_APPLY_INTERVAL - 1)
    assert host.applied == [], "nor within the rate limit"
    host._apply_link_updates(1000.0 + plugin_mod.LINK_APPLY_INTERVAL + 1)
    assert host.applied[0][1]["apower"] == 34.8 and host.applied[0][1]["output"] is True
    host.applied.clear()
    host._on_link_message("192.168.1.13", SWITCHED_OFF)
    assert host.applied and host.applied[0][1]["output"] is False, "a switch change is not held back"


def test_each_channel_gets_its_own_component(plugin_mod, monkeypatch):
    ch0 = FakeDev(1, "2PM Ch1", chan="0")
    ch1 = FakeDev(2, "2PM Ch2", chan="1")
    host = _host(plugin_mod, [ch0, ch1], monkeypatch)
    msg = {"src": SRC, "method": "NotifyStatus",
           "params": {"switch:1": {"output": True, "source": "button"}}}
    host._on_link_message("192.168.1.13", msg)
    assert [d for d, _s in host.applied] == [2]


def test_other_types_are_polled_when_they_change(plugin_mod, monkeypatch):
    dimmer = FakeDev(3, "Dimmer", type_id="shellyDimmer")
    host = _host(plugin_mod, [dimmer], monkeypatch)
    host._on_link_message("192.168.1.13", {"src": SRC, "method": "NotifyStatus",
                                           "params": {"light:0": {"brightness": 40}}})
    host._apply_link_updates(1000.0)
    assert host.polled == [3]


def test_a_quiet_keepalive_keeps_other_types_online(plugin_mod, monkeypatch):
    cover = FakeDev(4, "Blind", type_id="shellyCover")
    host = _host(plugin_mod, [cover], monkeypatch)
    host._on_link_message("192.168.1.13", {"id": 2, "src": SRC,
                                           "result": {"cover:0": {"state": "stopped"}}})
    assert host.online == [4]


def test_a_device_at_another_address_is_untouched(plugin_mod, monkeypatch):
    other = FakeDev(5, "Elsewhere", ip="192.168.1.99")
    host = _host(plugin_mod, [other], monkeypatch)
    host._on_link_message("192.168.1.13", FULL)
    host._apply_link_updates(1000.0)
    assert host.applied == [] and host._link_status == {}


# ── identity ─────────────────────────────────────────────────────────────────

def test_the_wrong_box_at_the_address_is_ignored(plugin_mod, monkeypatch):
    plug = FakeDev(1, "NAS Plug", mac="AABBCC000001")
    host = _host(plugin_mod, [plug], monkeypatch)
    host._on_link_message("192.168.1.13", FULL)
    host._apply_link_updates(1000.0)
    assert host.applied == [] and "192.168.1.13" in host._link_warned


# ── button presses ───────────────────────────────────────────────────────────

def test_a_pushed_button_press_fires_the_trigger_once(plugin_mod, monkeypatch):
    garage = FakeDev(6, "Garage", ip="192.168.1.26", mac="7C2C6774C698")
    host = _host(plugin_mod, [garage], monkeypatch)
    host._on_link_message("192.168.1.26", BUTTON)
    assert host.fired == [("inputButtonPress", 6, {"input_id": "0", "press_type": "double"})]


def test_only_the_channel_0_relay_owns_the_input(plugin_mod, monkeypatch):
    ch1 = FakeDev(7, "Ch2", ip="192.168.1.26", chan="1", mac="7C2C6774C698")
    host = _host(plugin_mod, [ch1], monkeypatch)
    host._on_link_message("192.168.1.26", BUTTON)
    assert host.fired == []


def test_a_script_event_is_not_a_button(plugin_mod, monkeypatch):
    garage = FakeDev(6, "Garage", ip="192.168.1.26", mac="7C2C6774C698")
    host = _host(plugin_mod, [garage], monkeypatch)
    host._on_link_message("192.168.1.26", {"src": BUTTON["src"], "method": "NotifyEvent",
                                           "params": {"events": [{"component": "script:1",
                                                                  "event": "single_push"}]}})
    assert host.fired == []


# ── the session loop, against a fake socket ──────────────────────────────────

class FakeSocket:
    def __init__(self, frames, link):
        self.frames, self.sent, self.link = list(frames), [], link

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self, timeout=None):
        if not self.frames:
            self.link.stop()
            raise TimeoutError
        return self.frames.pop(0)


def test_the_session_subscribes_filters_noise_and_hands_on_messages(plugin_mod):
    got, ups = [], []
    plugin = types.SimpleNamespace(_on_link_message=lambda ip, m: got.append(m),
                                   _link_up=lambda ip: ups.append(ip),
                                   _link_down=lambda ip: None,
                                   logger=types.SimpleNamespace(debug=lambda *a, **k: None))
    noise = json.dumps({"src": SRC, "method": "NotifyEvent", "params": {"events": [
        {"component": "script:1", "event": "ble.scan_result", "data": [2, []]}]}})
    holder = {}

    def connect(url, **kwargs):
        assert url == "ws://192.168.1.13/rpc"
        holder["sock"] = FakeSocket([noise, json.dumps(FULL), "not json", noise,
                                     json.dumps(POWER_ONLY)], link)
        return holder["sock"]

    link = plugin_mod.ShellyLink(plugin, "192.168.1.13", connect=connect)
    link._session()
    assert holder["sock"].sent[0]["method"] == "Shelly.GetStatus"
    assert holder["sock"].sent[0]["src"] == plugin_mod.LINK_SRC
    assert got == [FULL, POWER_ONLY], "noise and junk never reach the plugin"
    assert ups == ["192.168.1.13"] and link.connected


def test_a_link_counts_as_live_only_while_it_hears_something(plugin_mod):
    link = plugin_mod.ShellyLink(types.SimpleNamespace(), "192.168.1.13", connect=lambda *a, **k: None)
    link.connected, link.last_msg = True, 1000.0
    assert link.live(1000.0 + 60)
    assert not link.live(1000.0 + plugin_mod.LINK_LIVE_WINDOW + 1)


def test_a_dropped_link_reconnects_with_back_off_until_stopped(plugin_mod, monkeypatch):
    attempts, downs = [], []
    plugin = types.SimpleNamespace(_on_link_message=lambda *a: None, _link_up=lambda ip: None,
                                   _link_down=lambda ip: downs.append(ip),
                                   logger=types.SimpleNamespace(debug=lambda *a, **k: None))

    def connect(url, **kwargs):
        attempts.append(url)
        if len(attempts) >= 3:
            link.stop()
        raise OSError("no route")

    link = plugin_mod.ShellyLink(plugin, "192.168.1.13", connect=connect)
    monkeypatch.setattr(link.stop_event, "wait", lambda t: link.stop_event.is_set())
    link._run()
    assert len(attempts) == 3 and downs == [], "never connected, so never announced down"


# ── the webhook is ignored while the link is live ────────────────────────────

def test_link_live_for_reads_the_devices_address(plugin_mod):
    link = types.SimpleNamespace(live=lambda now=None: True)
    host = types.SimpleNamespace(_links={"192.168.1.13": link})
    assert plugin_mod.Plugin._link_live_for(host, FakeDev(1, "NAS Plug")) is True
    assert plugin_mod.Plugin._link_live_for(host, FakeDev(2, "Other", ip="192.168.1.99")) is False


def test_no_links_while_authentication_is_on(plugin_mod):
    host = types.SimpleNamespace(live_connection=True, shelly_user="admin")
    assert plugin_mod.Plugin._link_capable(host) is False


@pytest.mark.parametrize("pref", [False])
def test_no_links_when_switched_off(plugin_mod, pref):
    host = types.SimpleNamespace(live_connection=pref, shelly_user="")
    assert plugin_mod.Plugin._link_capable(host) is False


def test_links_are_started_and_stopped_to_match_the_devices(plugin_mod, monkeypatch):
    plug = FakeDev(1, "NAS Plug")
    blu = FakeDev(2, "Button", type_id="shellyBluButton", ip="192.168.1.50")
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda *a, **k: [plug, blu],
                        raising=False)
    started, stopped = [], []

    class StubLink:
        def __init__(self, plugin, ip, secure=False, connect=None):
            self.ip = ip

        def start(self):
            started.append(self.ip)

        def stop(self):
            stopped.append(self.ip)

    monkeypatch.setattr(plugin_mod, "ShellyLink", StubLink)
    old = StubLink(None, "192.168.1.77")
    host = types.SimpleNamespace(_links={"192.168.1.77": old}, _https_hosts=set(),
                                 live_connection=True, shelly_user="",
                                 _dup_ids_cached=lambda: set(), _link_warned=set())
    host._link_capable = plugin_mod.Plugin._link_capable.__get__(host)
    host._link_warned_import = plugin_mod.Plugin._link_warned_import.__get__(host)
    plugin_mod.Plugin._manage_links(host)
    assert started == ["192.168.1.13"], "the BLU button has no link of its own"
    assert stopped == ["192.168.1.77"]
    assert set(host._links) == {"192.168.1.13"}
