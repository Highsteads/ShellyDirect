#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v312_fixes.py
# Description: Regression tests for the v3.12 deep-review high batch (Fable 5
#              review, 16-07-2026): devId-aware webhook stale test (the
#              multi-channel sibling clobber), in-place energy day/month
#              rollover in _calc_energy, component-correct EM energy keys,
#              and the RGBW profile resolution.
# Author:      CliveS & Claude Fable 5
# Date:        16-07-2026
# Version:     1.0

from __future__ import annotations

import threading
import types


class FakeDev:
    def __init__(self, dev_id, name, type_id="shellyRelay",
                 mac="", ip="", channel="0", enabled=True, props=None):
        self.id           = dev_id
        self.name         = name
        self.deviceTypeId = type_id
        self.enabled      = enabled
        self.configured   = True
        self.pluginProps  = {"mac_address": mac, "ip_address": ip,
                             "channel_id": channel}
        if props:
            self.pluginProps.update(props)
        self.replaced_props = None

    def replacePluginPropsOnServer(self, new_props):
        self.replaced_props = dict(new_props)
        self.pluginProps    = dict(new_props)


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload    = payload
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# ── _ensure_webhooks: devId-aware stale test ─────────────────────────────────

def _hook(hook_id, *urls):
    return {"id": hook_id, "urls": list(urls)}


def _run_ensure(plugin_mod, hooks, wanted, live_devices):
    """Drive the REAL _ensure_webhooks with a canned Webhook.List response.
    Returns (deleted_hook_ids, created_urls)."""
    plugin_mod.indigo.devices.iter = lambda *a, **k: list(live_devices)
    deleted, created = [], []

    def _rget(url, params=None, timeout=None):
        if "Webhook.List" in url:
            return FakeResp({"hooks": hooks})
        if "Webhook.Delete" in url:
            deleted.append((params or {}).get("id"))
            return FakeResp({})
        if "Webhook.Create" in url:
            created.append((params or {}).get("urls"))
            return FakeResp({})
        return FakeResp({})

    receiver = types.SimpleNamespace(
        _rget=_rget,
        logger=types.SimpleNamespace(debug=lambda *a, **k: None),
    )
    dev = FakeDev(101, "Ch1 Relay", ip="192.168.1.50", channel="0")
    plugin_mod.Plugin._ensure_webhooks(receiver, "192.168.1.50", dev, wanted)
    return deleted, created


_WANTED = [("switch.on",  "http://192.168.1.9:8178/shellyEvent?devId=101&ev=on",  0),
           ("switch.off", "http://192.168.1.9:8178/shellyEvent?devId=101&ev=off", 0)]


def test_sibling_channel_hooks_survive(plugin_mod):
    """THE v3.12 headline: channel 0's repair must NOT delete channel 1's
    hooks on the same physical Shelly (the v3.11 ping-pong survivor)."""
    live = [FakeDev(101, "Ch1", ip="192.168.1.50", channel="0"),
            FakeDev(102, "Ch2", ip="192.168.1.50", channel="1")]
    hooks = [_hook(7, "http://192.168.1.9:8178/shellyEvent?devId=102&ev=on"),
             _hook(8, _WANTED[0][1]), _hook(9, _WANTED[1][1])]
    deleted, created = _run_ensure(plugin_mod, hooks, _WANTED, live)
    assert deleted == [], "a live sibling's hooks must never be deleted"
    assert created == []


def test_orphaned_devid_hooks_still_cleaned(plugin_mod):
    """Deleted/recreated devices' leftover devIds must still be swept."""
    live = [FakeDev(101, "Ch1", ip="192.168.1.50", channel="0")]
    hooks = [_hook(7, "http://192.168.1.9:8178/shellyEvent?devId=999&ev=on"),
             _hook(8, _WANTED[0][1]), _hook(9, _WANTED[1][1])]
    deleted, _created = _run_ensure(plugin_mod, hooks, _WANTED, live)
    assert deleted == [7]


def test_multiurl_hook_carrying_wanted_url_survives(plugin_mod):
    """A (hand-edited) hook holding BOTH a wanted and an orphaned URL must not
    be deleted — deleting it would silently lose the working webhook."""
    live = [FakeDev(101, "Ch1", ip="192.168.1.50", channel="0")]
    hooks = [_hook(7, _WANTED[0][1],
                   "http://192.168.1.9:8178/shellyEvent?devId=999&ev=on"),
             _hook(9, _WANTED[1][1])]
    deleted, _created = _run_ensure(plugin_mod, hooks, _WANTED, live)
    assert deleted == []


def test_devid_match_respects_delimiters(plugin_mod):
    """devId=10 must not prefix-match devId=101 (regex boundary check)."""
    live = [FakeDev(101, "Ch1", ip="192.168.1.50", channel="0")]
    hooks = [_hook(7, "http://192.168.1.9:8178/shellyEvent?devId=10&ev=on"),
             _hook(8, _WANTED[0][1]), _hook(9, _WANTED[1][1])]
    deleted, _created = _run_ensure(plugin_mod, hooks, _WANTED, live)
    assert deleted == [7], "devId=10 is NOT live device 101 — orphaned"


def test_missing_wanted_hooks_created(plugin_mod):
    live = [FakeDev(101, "Ch1", ip="192.168.1.50", channel="0")]
    deleted, created = _run_ensure(plugin_mod, [], _WANTED, live)
    assert deleted == []
    assert len(created) == 2


# ── _calc_energy: in-place day/month rollover ────────────────────────────────

def _energy_self(data):
    return types.SimpleNamespace(energy_data=data,
                                 _energy_lock=threading.RLock())


def test_missed_midnight_rolls_over_in_place(plugin_mod):
    """Device offline at midnight: the first poll of the new day must bank the
    stale day as a history row and re-baseline — not keep accumulating."""
    from datetime import date
    data = {"55": {"day_baseline_wh": 1000.0, "day_date": "2020-01-01",
                   "month_baseline_wh": 500.0, "month_date": "2020-01",
                   "history": []}}
    receiver = _energy_self(data)
    today_kwh, month_kwh = plugin_mod.Plugin._calc_energy(receiver, 55, 3500.0)
    entry = data["55"]
    assert entry["day_date"] == str(date.today())
    assert entry["day_baseline_wh"] == 3500.0
    assert today_kwh == 0.0, "new day starts from the fresh baseline"
    # the stale period banked against its recorded date
    assert entry["history"] == [{"date": "2020-01-01", "kwh": 2.5}]
    # month also rolled over (2020-01 != this month)
    assert entry["month_baseline_wh"] == 3500.0
    assert month_kwh == 0.0


def test_same_day_accumulation_unchanged(plugin_mod):
    from datetime import date
    today = str(date.today())
    data = {"55": {"day_baseline_wh": 1000.0, "day_date": today,
                   "month_baseline_wh": 1000.0, "month_date": today[:7]}}
    receiver = _energy_self(data)
    today_kwh, month_kwh = plugin_mod.Plugin._calc_energy(receiver, 55, 2500.0)
    assert today_kwh == 1.5
    assert month_kwh == 1.5
    assert "history" not in data["55"], "no rollover on a same-day poll"


def test_counter_reset_still_rebaselines(plugin_mod):
    """A device reboot that resets the meter below the baseline must
    re-baseline (pre-existing rule, must survive the rollover change)."""
    from datetime import date
    today = str(date.today())
    data = {"55": {"day_baseline_wh": 5000.0, "day_date": today,
                   "month_baseline_wh": 5000.0, "month_date": today[:7]}}
    receiver = _energy_self(data)
    today_kwh, _ = plugin_mod.Plugin._calc_energy(receiver, 55, 100.0)
    assert data["55"]["day_baseline_wh"] == 100.0
    assert today_kwh == 0.0


# ── EM energy keys (component-correct) ───────────────────────────────────────

def test_em_total_wh_prefers_total_act(plugin_mod):
    assert plugin_mod.Plugin._em_total_wh(
        {"total_act": 1234.5, "a_total_act_energy": 1.0}) == 1234.5


def test_em_total_wh_falls_back_to_phase_sum(plugin_mod):
    emdata = {"a_total_act_energy": 100.0, "b_total_act_energy": 200.0,
              "c_total_act_energy": 300.0}
    assert plugin_mod.Plugin._em_total_wh(emdata) == 600.0


def test_em_total_wh_never_fabricates_from_partial(plugin_mod):
    emdata = {"a_total_act_energy": 100.0, "b_total_act_energy": 200.0}
    assert plugin_mod.Plugin._em_total_wh(emdata) is None
    assert plugin_mod.Plugin._em_total_wh({}) is None


# ── RGBW profile resolution ──────────────────────────────────────────────────

def _rgbw_receiver(config_payload, status=200):
    def _rget(url, params=None, timeout=None):
        assert "Shelly.GetConfig" in url
        return FakeResp(config_payload, status)
    return types.SimpleNamespace(_rget=_rget)


def test_rgbw_profile_detected_and_cached(plugin_mod):
    dev = FakeDev(60, "Strip", type_id="shellyRGBW", ip="192.168.1.60")
    receiver = _rgbw_receiver({"rgbw:0": {}, "sys": {}})
    prof = plugin_mod.Plugin._rgbw_component(receiver, dev, "192.168.1.60")
    assert prof == "rgbw"
    assert dev.replaced_props["rgbw_profile"] == "rgbw", "probe result cached"


def test_rgb_profile_detected(plugin_mod):
    dev = FakeDev(61, "Strip", type_id="shellyRGBW", ip="192.168.1.61")
    receiver = _rgbw_receiver({"rgb:0": {}, "sys": {}})
    assert plugin_mod.Plugin._rgbw_component(receiver, dev, "192.168.1.61") == "rgb"


def test_cached_profile_skips_probe(plugin_mod):
    dev = FakeDev(62, "Strip", type_id="shellyRGBW",
                  props={"rgbw_profile": "rgb"})
    def _boom(*a, **k):
        raise AssertionError("must not probe when the profile is cached")
    receiver = types.SimpleNamespace(_rget=_boom)
    assert plugin_mod.Plugin._rgbw_component(receiver, dev, "x") == "rgb"


def test_failed_probe_defaults_light_without_persisting(plugin_mod):
    dev = FakeDev(63, "Strip", type_id="shellyRGBW")
    def _fail(*a, **k):
        raise OSError("no route")
    receiver = types.SimpleNamespace(_rget=_fail)
    assert plugin_mod.Plugin._rgbw_component(receiver, dev, "x") == "light"
    assert dev.replaced_props is None, "an inconclusive probe must not persist"


def test_set_component_mapping(plugin_mod):
    dev = FakeDev(64, "Strip", type_id="shellyRGBW",
                  props={"rgbw_profile": "rgbw"})
    receiver = types.SimpleNamespace(
        _rgbw_component=lambda d, i: d.pluginProps["rgbw_profile"])
    comp = plugin_mod.Plugin._rgbw_set_component(receiver, dev, "x")
    assert comp == "RGBW"
