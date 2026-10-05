#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v433_dimmer_action_enum.py
# Description: actionControlDimmer compared action.deviceAction against
#              indigo.kDimmerAction.*, which Indigo does not have (the dimmer
#              actions live in indigo.kDeviceAction). Every Dimmer and RGBW
#              action therefore raised AttributeError, was caught and logged as
#              "actionControlDimmer exception", and nothing was ever sent to the
#              light. These tests drive the shipped handler with the real
#              indigo.kDeviceAction values (TurnOn 4, TurnOff 5, Toggle 6,
#              SetBrightness 7, BrightenBy 8, DimBy 9, RequestStatus 11, read
#              live from Indigo 2025.2.0 on 05-10-2026) and a stub that has NO
#              kDimmerAction, as Indigo has none.
# Author:      CliveS & Claude Sonnet 5.5
# Date:        05-10-2026
# Version:     1.0

from __future__ import annotations

import pathlib
import types

import pytest

from test_v318_event_log_quiet import _Dev, _host

LIVE_DEVICE_ACTION = types.SimpleNamespace(
    TurnOn=4, TurnOff=5, Toggle=6, SetBrightness=7, BrightenBy=8, DimBy=9,
    SetColorLevels=10, RequestStatus=11)


@pytest.fixture
def run(plugin_mod, monkeypatch):
    """Run the shipped actionControlDimmer; return (calls, polled, event_log, dev)."""
    monkeypatch.setattr(plugin_mod.indigo, "kDeviceAction", LIVE_DEVICE_ACTION,
                        raising=False)
    # Indigo has no kDimmerAction. Remove the stub's so a reference to it fails.
    monkeypatch.delattr(plugin_mod.indigo, "kDimmerAction", raising=False)

    def _run(act, value=None, type_id="shellyDimmer", on=False, brightness=50):
        event_log, calls, polled = [], [], []
        monkeypatch.setattr(plugin_mod, "log",
                            lambda msg, level="INFO": event_log.append((level, str(msg))))
        dev = _Dev(type_id=type_id, on=on)
        dev.states = {"brightnessLevel": brightness}

        def light_set(ip, channel_id, on, brightness=None, component="Light"):
            calls.append({"ip": ip, "channel": channel_id, "on": on,
                          "brightness": brightness, "component": component})
            return True

        h = _host(plugin_mod,
                  _light_set=light_set,
                  _pref_int=lambda props, key, default=0: default,
                  _rgbw_set_component=lambda d, ip: "RGBW",
                  _poll_device=lambda d: polled.append(d))
        action = types.SimpleNamespace(deviceAction=act, actionValue=value)
        plugin_mod.Plugin.actionControlDimmer(h, action, dev)
        return calls, polled, event_log, dev

    return _run


def test_turn_on_reaches_the_light(run):
    calls, _, event_log, dev = run(LIVE_DEVICE_ACTION.TurnOn)
    assert calls == [{"ip": "192.168.1.50", "channel": 0, "on": True,
                      "brightness": None, "component": "Light"}]
    assert dev.written["onOffState"] is True
    assert event_log == []


def test_turn_off_reaches_the_light(run):
    calls, _, event_log, dev = run(LIVE_DEVICE_ACTION.TurnOff, on=True)
    assert [c["on"] for c in calls] == [False]
    assert dev.written["onOffState"] is False
    assert event_log == []


def test_toggle_flips_the_current_state(run):
    calls, _, event_log, dev = run(LIVE_DEVICE_ACTION.Toggle, on=True)
    assert [c["on"] for c in calls] == [False]
    assert dev.written["onOffState"] is False
    assert event_log == []


def test_set_brightness_reaches_the_light(run):
    calls, _, event_log, dev = run(LIVE_DEVICE_ACTION.SetBrightness, value=42)
    assert [(c["on"], c["brightness"]) for c in calls] == [(True, 42)]
    assert dev.written["brightnessLevel"] == 42
    assert dev.written["onOffState"] is True
    assert event_log == []


def test_set_brightness_zero_turns_it_off(run):
    calls, _, _, dev = run(LIVE_DEVICE_ACTION.SetBrightness, value=0, on=True)
    assert [(c["on"], c["brightness"]) for c in calls] == [(False, 0)]
    assert dev.written["onOffState"] is False


def test_brighten_by_adds_to_the_current_level(run):
    calls, _, _, dev = run(LIVE_DEVICE_ACTION.BrightenBy, value=20, brightness=50)
    assert [c["brightness"] for c in calls] == [70]
    assert dev.written["brightnessLevel"] == 70


def test_dim_by_takes_from_the_current_level(run):
    calls, _, _, dev = run(LIVE_DEVICE_ACTION.DimBy, value=20, brightness=50)
    assert [c["brightness"] for c in calls] == [30]
    assert dev.written["brightnessLevel"] == 30


def test_request_status_polls_the_device(run):
    calls, polled, event_log, dev = run(LIVE_DEVICE_ACTION.RequestStatus)
    assert calls == [] and polled == [dev]
    assert event_log == []


def test_an_rgbw_light_uses_its_own_component(run):
    calls, _, event_log, _ = run(LIVE_DEVICE_ACTION.TurnOn, type_id="shellyRGBW")
    assert [c["component"] for c in calls] == ["RGBW"]
    assert event_log == []


def test_the_plugin_never_names_kDimmerAction(plugin_mod):
    """Indigo has no such enum; the dimmer actions are in kDeviceAction."""
    src = pathlib.Path(plugin_mod.__file__).read_text(encoding="utf-8")
    assert "indigo.kDimmerAction" not in src
