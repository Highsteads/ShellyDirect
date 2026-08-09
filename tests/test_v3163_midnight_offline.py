#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v3163_midnight_offline.py
# Description: Regression tests for the v3.16.3 midnight-reset offline guard.
#
#              _midnight_reset walked EVERY energy device and tried to read its
#              cumulative counter, so a device that was away raised a WARNING
#              every single midnight for as long as it stayed away. Two plugs
#              here are switched off at the wall between uses by design, so the
#              pair produced two warnings a night, every night, for correct
#              behaviour — and the noise is what made a genuinely dead plug
#              (five days gone) look like more of the same.
#
#              The guard must NOT over-reach: an ABSENT deviceOnline state has to
#              read as online, or a device that never reports its status quietly
#              stops resetting its daily baseline and its energy figures drift.
# Author:      CliveS & Claude Opus 5
# Date:        09-08-2026
# Version:     1.0

from __future__ import annotations

import threading

import pytest


class _QuietLogger:
    def __init__(self):
        self.debug_lines = []

    def debug(self, msg, *a, **k):
        self.debug_lines.append(str(msg))

    def info(self, msg, *a, **k):
        pass

    def warning(self, msg, *a, **k):
        pass

    def error(self, msg, *a, **k):
        pass


class _Dev:
    """Minimal device stand-in carrying only what _midnight_reset touches."""

    def __init__(self, name, ip, online=None, dev_id=1):
        self.id            = dev_id
        self.name          = name
        self.deviceTypeId  = "shellyRelay"
        self.pluginProps   = {"ip_address": ip, "has_pm": True, "channel_id": "0"}
        self.states        = {} if online is None else {"deviceOnline": online}


class _Host:
    """Binds the shipped _midnight_reset onto a host that records its reads."""

    def __init__(self, plugin_mod):
        self.energy_data   = {}
        self._energy_lock  = threading.RLock()
        self.logger        = _QuietLogger()
        self.reads         = []
        self.saved         = False
        self._midnight_reset = plugin_mod.Plugin._midnight_reset.__get__(self)

    # -- collaborators the real method calls out to ---------------------------
    def _pref_int(self, props, key, default=0):
        try:
            return int(props.get(key, default))
        except (TypeError, ValueError):
            return default

    def _rget(self, url):
        self.reads.append(url)

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"aenergy": {"total": 1234.0}}

        return _Resp()

    def _get_total_wh(self, blob, key):
        return blob.get(key)

    def _em_total_wh(self, blob):
        return None

    def _save_energy_data(self):
        self.saved = True


@pytest.fixture
def host(plugin_mod, monkeypatch):
    """A host plus a captured module-level log() so warnings can be asserted on."""
    lines = []
    monkeypatch.setattr(
        plugin_mod, "log",
        lambda message, level="INFO": lines.append((level, str(message))),
    )
    h = _Host(plugin_mod)
    h.log_lines = lines
    return h


def _run(plugin_mod, monkeypatch, host, devices):
    # Patch the module object the PLUGIN holds, not a fresh `import indigo`.
    # Earlier suites swap their own fake into sys.modules, so importing it here
    # gives a different object and the patch lands somewhere the code under test
    # never looks — the run then silently exercises the previous suite's devices.
    monkeypatch.setattr(plugin_mod.indigo.devices, "iter", lambda _f: list(devices))
    host._midnight_reset("2026-08-09")


def _warnings(host):
    return [m for lvl, m in host.log_lines if str(lvl).upper() == "WARNING"]


def test_offline_device_is_skipped_silently(plugin_mod, monkeypatch, host):
    """A plug switched off at the wall must not warn every midnight."""
    dev = _Dev("Washing Machine Monitor", "192.168.1.118", online=False)
    _run(plugin_mod, monkeypatch, host, [dev])

    assert host.reads == [], "an offline device must not be polled at all"
    assert _warnings(host) == [], "an expected-offline device must not raise a warning"
    assert any("offline" in line for line in host.logger.debug_lines)


def test_online_device_is_still_polled(plugin_mod, monkeypatch, host):
    """The guard must not stop the reset it exists to protect."""
    dev = _Dev("Dehumidifier Plug", "192.168.1.106", online=True)
    _run(plugin_mod, monkeypatch, host, [dev])

    assert len(host.reads) == 1
    assert "192.168.1.106" in host.reads[0]


def test_absent_online_state_is_treated_as_online(plugin_mod, monkeypatch, host):
    """An ABSENT state is unknown, never a licence to skip.

    A device that has never reported deviceOnline would otherwise stop
    resetting its daily baseline for ever, in silence.
    """
    dev = _Dev("Never Reported Its Status", "192.168.1.107", online=None)
    _run(plugin_mod, monkeypatch, host, [dev])

    assert len(host.reads) == 1, "a device with no deviceOnline state must still be polled"


def test_offline_device_does_not_block_the_rest(plugin_mod, monkeypatch, host):
    """One away plug must not cost the other devices their midnight reset."""
    devices = [
        _Dev("Away Plug", "192.168.1.118", online=False, dev_id=1),
        _Dev("Live Plug", "192.168.1.106", online=True, dev_id=2),
    ]
    _run(plugin_mod, monkeypatch, host, devices)

    assert len(host.reads) == 1
    assert "192.168.1.106" in host.reads[0]
    assert host.saved is True
