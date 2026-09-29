#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v432_midnight_jitter.py
# Description: v4.3.2 - a reading a few tenths of a Wh below the day baseline is
#              an older status, not a counter reset. Every midnight 27-29 Sep the
#              reset read each plug directly, the next poll came in 0.0-0.5 Wh
#              lower, and five or six plugs a night logged "cumulative energy went
#              backwards" and started the two-strike rule.
# Author:      CliveS & Claude Opus 5.5
# Date:        29-09-2026
# Version:     1.0

from __future__ import annotations

import threading
from datetime import date

import pytest


class Host:
    """Minimal stand-in carrying only what _calc_energy touches."""

    def __init__(self, plugin_mod):
        self.energy_data  = {}
        self._energy_lock = threading.RLock()
        self._calc_energy = plugin_mod.Plugin._calc_energy.__get__(self)


@pytest.fixture
def host(plugin_mod):
    return Host(plugin_mod)


def _baselined(host, dev_id, wh):
    host.energy_data[str(dev_id)] = {
        "day_baseline_wh":   wh,
        "day_date":          str(date.today()),
        "month_baseline_wh": wh - 10_000.0,
        "month_date":        str(date.today())[:7],
    }


def test_the_real_midnight_shape_is_not_a_suspected_reset(host):
    """522839.4 at the midnight read, 522839.3 at the next poll (29-Sep, 00:00)."""
    _baselined(host, 1, 522_839.4)
    today, month = host._calc_energy(1, 522_839.3)
    entry = host.energy_data["1"]
    assert "pending_reset_wh" not in entry, "a 0.1 Wh dip must not start the two-strike rule"
    assert entry["day_baseline_wh"] == 522_839.4, "baseline untouched"
    assert today == 0.0
    assert month == pytest.approx(9.9999, abs=1e-3)


def test_two_small_dips_in_a_row_never_rebaseline(host):
    """The second strike used to fire on the next dip and then undo itself."""
    _baselined(host, 2, 8_683.4)
    host._calc_energy(2, 8_683.0)
    host._calc_energy(2, 8_683.0)
    entry = host.energy_data["2"]
    assert entry["day_baseline_wh"] == 8_683.4
    assert "reset_undo" not in entry
    today, _ = host._calc_energy(2, 9_683.4)
    assert today == pytest.approx(1.0)


def test_a_drop_just_past_the_margin_is_still_suspected(host, plugin_mod):
    base = 100_000.0
    _baselined(host, 3, base)
    host._calc_energy(3, base - plugin_mod.ENERGY_JITTER_WH - 1.0)
    assert "pending_reset_wh" in host.energy_data["3"]


def test_a_phantom_zero_still_gets_two_strikes(host):
    _baselined(host, 4, 3_446_590.0)
    today, _ = host._calc_energy(4, 0.0)
    assert "pending_reset_wh" in host.energy_data["4"]
    assert today == 0.0
    assert host.energy_data["4"]["day_baseline_wh"] == 3_446_590.0
