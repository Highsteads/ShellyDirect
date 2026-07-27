#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_v3162_phantom_energy.py
# Description: Regression tests for the v3.16.2 phantom lifetime-total fix.
#
#              Root cause: _calc_energy treated ANY reading below the running
#              baseline as a cumulative-counter reset and re-baselined at once.
#              _get_total_wh only returns None for an ABSENT field, so a device
#              REPORTING `aenergy.total: 0` passed a real 0.0 through, zeroed the
#              baseline, and the next poll published the whole LIFETIME total as
#              today's usage. NOTE the 20-07-2026 live near-miss (~3446 kWh armed to
#              announce "Used 3446.59 kWh (~£911.97)") was caused by the IP-collision
#              bug fixed in v3.16.0 — two Indigo records polling one plug. This is a
#              SECOND, independent route to an identical figure that survived it.
#
#              Also covers the stale-rollover guard: a device offline for weeks
#              must not bank months of accumulation as one day's history row.
# Author:      CliveS & Claude Opus 5
# Date:        27-07-2026
# Version:     1.0

from __future__ import annotations

import threading
from datetime import date, timedelta

import pytest


# The real _calc_energy is pulled off the Plugin class by conftest's loader in the
# other suites; here we bind the unbound functions onto a minimal host so the test
# exercises the shipped implementation rather than a paraphrase of it.
class Host:
    """Minimal stand-in carrying only what _calc_energy touches."""

    def __init__(self, plugin_mod):
        self.energy_data  = {}
        self._energy_lock = threading.RLock()
        self.logger       = _QuietLogger()
        self._calc_energy   = plugin_mod.Plugin._calc_energy.__get__(self)
        self._get_total_wh  = plugin_mod.Plugin._get_total_wh


class _QuietLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *a, **k):
        self.warnings.append(str(msg))

    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


@pytest.fixture
def host(plugin_mod):
    return Host(plugin_mod)


LIFETIME_WH = 3_446_590.0     # the real near-miss figure, in Wh


# ── the root cause ──────────────────────────────────────────────────────────

def test_reported_zero_does_not_zero_the_baseline(host):
    """A single reported 0 must NOT be believed as a counter reset."""
    host._calc_energy(1, 100_000.0)                      # establish a baseline
    today, month = host._calc_energy(1, 120_000.0)       # 20 kWh so far
    assert today == pytest.approx(20.0)

    # The glitch: the device reports aenergy.total = 0 for one poll.
    today_g, month_g = host._calc_energy(1, 0.0)
    assert today_g == pytest.approx(20.0), "should preserve last known-good, not fabricate 0"
    assert host.energy_data["1"]["day_baseline_wh"] == 100_000.0, "baseline must be untouched"

    # The counter comes back at its real lifetime value.
    today_after, _ = host._calc_energy(1, LIFETIME_WH)
    assert today_after < 5000.0
    assert today_after == pytest.approx((LIFETIME_WH - 100_000.0) / 1000.0)


def test_the_actual_3446_kwh_regression(host):
    """The exact shape of the 20-07-2026 near-miss must not reproduce."""
    host._calc_energy(2, LIFETIME_WH - 1_000.0)          # baseline near lifetime
    host._calc_energy(2, 0.0)                            # the phantom zero
    today, _ = host._calc_energy(2, LIFETIME_WH)         # counter returns
    assert today < 100.0, f"phantom lifetime total leaked into today: {today} kWh"


def test_two_consecutive_lows_are_believed(host):
    """A GENUINE counter reset (device reflashed) must still re-baseline."""
    host._calc_energy(3, 500_000.0)
    host._calc_energy(3, 12.0)                           # strike one — held
    assert host.energy_data["3"]["day_baseline_wh"] == 500_000.0
    today, month = host._calc_energy(3, 15.0)            # strike two — believed
    assert today == 0.0 and month == 0.0
    assert host.energy_data["3"]["day_baseline_wh"] == 15.0
    # and it accumulates normally from the new baseline
    today_next, _ = host._calc_energy(3, 1_015.0)
    assert today_next == pytest.approx(1.0)


def test_recovery_clears_the_pending_flag(host):
    """A glitch followed by a normal reading must not leave a latch set."""
    host._calc_energy(4, 100_000.0)
    host._calc_energy(4, 0.0)                            # suspect
    assert "pending_reset_wh" in host.energy_data["4"]
    host._calc_energy(4, 101_000.0)                      # back to normal
    assert "pending_reset_wh" not in host.energy_data["4"]
    # a LATER lone zero is therefore still only strike one
    today, _ = host._calc_energy(4, 0.0)
    assert host.energy_data["4"]["day_baseline_wh"] == 100_000.0
    assert today == pytest.approx(1.0)


def test_first_ever_reading_is_zero_today(host):
    """A device seen for the first time reports 0 today, not its lifetime."""
    today, month = host._calc_energy(5, LIFETIME_WH)
    assert today == 0.0 and month == 0.0


def test_a_device_that_genuinely_starts_at_zero(host):
    """A brand-new meter reading 0 must behave, not trip the pending path."""
    today, _ = host._calc_energy(6, 0.0)
    assert today == 0.0
    today2, _ = host._calc_energy(6, 250.0)
    assert today2 == pytest.approx(0.25)


# ── the stale-rollover guard ────────────────────────────────────────────────

def test_stale_baseline_is_not_banked_as_one_day(host):
    """A device offline for months must not write months of kWh as one day."""
    key = "7"
    host._calc_energy(7, 150_000.0)
    long_ago = str(date.today() - timedelta(days=84))
    host.energy_data[key]["day_date"] = long_ago          # simulate the offline gap

    host._calc_energy(7, 400_000.0)                       # device returns
    hist = host.energy_data[key].get("history", [])
    assert not any(h["kwh"] > 100 for h in hist), f"banked an implausible row: {hist}"
    assert host.energy_data[key]["day_baseline_wh"] == 400_000.0, "must still re-baseline"


def test_normal_overnight_rollover_still_banks(host):
    """The ordinary one-day rollover must keep working."""
    key = "8"
    host._calc_energy(8, 10_000.0)
    host.energy_data[key]["day_date"] = str(date.today() - timedelta(days=1))
    host._calc_energy(8, 13_500.0)
    hist = host.energy_data[key].get("history", [])
    assert len(hist) == 1
    assert hist[0]["kwh"] == pytest.approx(3.5)


def test_days_between_handles_rubbish(plugin_mod):
    f = plugin_mod._days_between
    assert f("", "2026-07-27") is None
    assert f("not-a-date", "2026-07-27") is None
    assert f("2026-07-25", "2026-07-27") == 2
