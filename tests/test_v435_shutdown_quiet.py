#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v435_shutdown_quiet.py
# Description: v4.3.5 -- nothing touches indigo.* once the plugin is stopping.
#              While 4.3.3 shut down, two live-link messages still arrived after
#              Indigo had closed its connection and logged "UnexpectedNullError
#              -- CClientMgr not created". Indigo stops the concurrent thread
#              BEFORE shutdown(), so the flag is raised by stopConcurrentThread
#              and again at the very start of shutdown(); every link, webhook and
#              poll path checks it first.
# Author:      CliveS & Claude Sonnet 5.5
# Date:        05-10-2026
# Version:     1.0

from __future__ import annotations

import ast
import json
import types
from pathlib import Path

import pytest

from test_v400_live_link import (BUTTON, FULL, POWER_ONLY, SWITCHED_OFF, FakeDev,
                                 FakeSocket, _host)

SERVER = Path(__file__).resolve().parent.parent / "ShellyDirect.indigoPlugin" \
    / "Contents" / "Server Plugin" / "plugin.py"


class _Boom(Exception):
    pass


def _no_indigo_calls(plugin_mod, monkeypatch):
    """indigo.devices that records every touch and then fails, like a dead
    connection does."""
    touched = []

    class Dead:
        def iter(self, *a, **k):
            touched.append("iter")
            raise _Boom("CClientMgr not created")

        def __getitem__(self, key):
            touched.append("getitem")
            raise _Boom("CClientMgr not created")

    monkeypatch.setattr(plugin_mod.indigo, "devices", Dead())
    return touched


# -- link messages after stopping write nothing --------------------------------

@pytest.mark.parametrize("msg", [FULL, POWER_ONLY, SWITCHED_OFF, BUTTON])
def test_a_link_message_after_stopping_touches_nothing(plugin_mod, monkeypatch, msg):
    host = _host(plugin_mod, [FakeDev(1, "NAS Plug")], monkeypatch)
    touched = _no_indigo_calls(plugin_mod, monkeypatch)
    host._stopping = True
    host._on_link_message("192.168.1.13", msg)
    assert touched == [], "no indigo.* call once stopping"
    assert host.applied == [] and host.fired == [] and host._link_status == {}


def test_pushed_readings_are_not_written_once_stopping(plugin_mod, monkeypatch):
    host = _host(plugin_mod, [FakeDev(1, "NAS Plug")], monkeypatch)
    host._on_link_message("192.168.1.13", FULL)
    assert host._link_dirty, "the reading is waiting for the next tick"
    touched = _no_indigo_calls(plugin_mod, monkeypatch)
    host._stopping = True
    host._apply_link_updates(10_000.0)
    assert touched == [] and host.applied == [] and host.polled == []


def test_the_message_still_works_before_stopping(plugin_mod, monkeypatch):
    """The guard must not be a blanket refusal."""
    host = _host(plugin_mod, [FakeDev(1, "NAS Plug")], monkeypatch)
    host._stopping = False
    host._on_link_message("192.168.1.13", SWITCHED_OFF)
    assert host.applied and host.applied[0][1]["output"] is False


def test_a_poll_after_stopping_asks_nobody(plugin_mod):
    calls = []
    host = types.SimpleNamespace(_stopping=True)
    for name in ("_poll_relay", "_poll_uni", "_poll_cover", "_poll_dimmer", "_poll_i4",
                 "_poll_em", "_poll_rgbw", "_poll_blu_sensor"):
        setattr(host, name, lambda dev, n=name: calls.append(n))
    plugin_mod.Plugin._poll_device(host, FakeDev(1, "NAS Plug"))
    assert calls == []
    host._stopping = False
    plugin_mod.Plugin._poll_device(host, FakeDev(1, "NAS Plug"))
    assert calls == ["_poll_relay"]


def test_new_links_are_not_started_once_stopping(plugin_mod, monkeypatch):
    touched = _no_indigo_calls(plugin_mod, monkeypatch)
    host = types.SimpleNamespace(_links={}, _stopping=True)
    plugin_mod.Plugin._manage_links(host)
    assert touched == [] and host._links == {}


# -- the session loop stops delivering ------------------------------------------

def test_the_session_hands_nothing_on_once_the_plugin_is_stopping(plugin_mod):
    got = []
    plugin = types.SimpleNamespace(_on_link_message=lambda ip, m: got.append(m),
                                   _link_up=lambda ip: got.append("up"),
                                   _link_down=lambda ip: None, _stopping=False,
                                   logger=types.SimpleNamespace(debug=lambda *a, **k: None))

    class Sock(FakeSocket):
        def recv(self, timeout=None):
            raw = super().recv(timeout)
            plugin._stopping = True          # Indigo closes while the frame is in flight
            return raw

    link = plugin_mod.ShellyLink(plugin, "192.168.1.13",
                                 connect=lambda url, **kw: Sock([json.dumps(FULL),
                                                                 json.dumps(POWER_ONLY)], link))
    link._session()
    assert got == [], "a frame read after stopping began is dropped, not delivered"


# -- shutdown --------------------------------------------------------------------

def _shutdown_host(plugin_mod, order, **overrides):
    class Link:
        def __init__(self, name):
            self.name = name

        def stop(self):
            order.append(("link.stop", host._stopping))

        def join(self, timeout=None):
            order.append(("link.join", host._stopping))

    class Server:
        def shutdown(self):
            order.append(("server.shutdown", host._stopping))

        def server_close(self):
            order.append(("server.close", host._stopping))

    host = types.SimpleNamespace(
        _stopping=False,
        logger=types.SimpleNamespace(debug=lambda *a, **k: None),
        _links={"a": Link("a"), "b": Link("b")},
        webhook_server=Server(),
        _save_energy_data=lambda: order.append(("save", host._stopping)),
        _stop_mdns=lambda: order.append(("mdns", host._stopping)))
    host.__dict__.update(overrides)
    host._begin_stopping = plugin_mod.Plugin._begin_stopping.__get__(host)
    host._close_links = plugin_mod.Plugin._close_links.__get__(host)
    host._note_stopping = plugin_mod.Plugin._note_stopping.__get__(host)
    return host


def test_shutdown_raises_the_flag_before_anything_else(plugin_mod):
    order = []
    host = _shutdown_host(plugin_mod, order)
    plugin_mod.Plugin.shutdown(host)
    assert order and all(flag is True for _what, flag in order), order
    whats = [w for w, _f in order]
    assert whats.count("link.stop") == 2 and "link.join" in whats
    assert "save" in whats and "mdns" in whats and "server.close" in whats


def test_shutdown_never_raises_whatever_fails(plugin_mod):
    order = []

    def boom(*a, **k):
        raise _Boom("dead connection")

    host = _shutdown_host(plugin_mod, order, _save_energy_data=boom, _stop_mdns=boom,
                          logger=types.SimpleNamespace(debug=boom))
    host._links = {"a": types.SimpleNamespace(stop=boom, join=boom)}
    host.webhook_server = types.SimpleNamespace(shutdown=boom, server_close=boom)
    plugin_mod.Plugin.shutdown(host)          # must not raise
    assert host._stopping is True


def test_closing_the_links_is_bounded(plugin_mod, monkeypatch):
    """join is given a timeout each, and the whole wait has a ceiling."""
    seen = []
    clock = [1000.0]
    monkeypatch.setattr(plugin_mod.time, "time", lambda: clock[0])

    class Slow:
        def stop(self):
            pass

        def join(self, timeout=None):
            seen.append(timeout)
            clock[0] += 5.0                 # a link that never exits

    host = types.SimpleNamespace(_stopping=False, _links={str(i): Slow() for i in range(6)})
    plugin_mod.Plugin._close_links(host)
    assert all(t is not None and t <= 3.0 for t in seen)
    assert len(seen) <= 2, "the ceiling stops the wait; six stuck links do not take 30 s"


def test_stop_concurrent_thread_raises_the_flag_and_stops_the_links(plugin_mod):
    stopped = []
    host = types.SimpleNamespace(_stopping=False,
                                 _links={"a": types.SimpleNamespace(
                                     stop=lambda: stopped.append("a"))})
    host._begin_stopping = plugin_mod.Plugin._begin_stopping.__get__(host)
    plugin_mod.Plugin._note_stopping(host)
    assert host._stopping is True and stopped == ["a"]


def test_the_plugin_overrides_both_spellings_of_stop_concurrent_thread():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    names = set()
    for node in plugin.body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    assert {"stop_concurrent_thread", "stopConcurrentThread"} <= names


def test_shutdown_does_not_use_self_sleep():
    """Indigo has already stopped the thread, so self.sleep raises in shutdown."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    for node in plugin.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("shutdown", "_close_links",
                                                                "_begin_stopping"):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Attribute) and sub.attr == "sleep"
                        and isinstance(sub.value, ast.Name) and sub.value.id == "self"):
                    pytest.fail(f"self.sleep in {node.name}")


# -- the webhook listener --------------------------------------------------------

def test_the_webhook_handlers_check_the_flag_first():
    """Both do_GET and do_POST must test plugin._stopping before any indigo call."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    handlers = [n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name in ("do_GET", "do_POST")]
    assert len(handlers) == 2
    for fn in handlers:
        src = ast.get_source_segment(SERVER.read_text(encoding="utf-8"), fn)
        flag = src.find("_stopping")
        first_indigo = src.find("indigo.")
        assert flag != -1, f"{fn.name} never checks the stopping flag"
        assert flag < first_indigo, f"{fn.name} touches indigo before checking the flag"
