#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# Filename:    test_sql_logger_churn.py
# Description: v3.18.4. countsOnTime ticks on every poll, and sysUptime and wifiRssi
#              change on most, so SQL Logger stored ~100 rows an hour per plug for
#              counters nobody charts. deviceStartComm adds them to the device's
#              sqlLoggerIgnoreStates shared prop without overriding the user.
# Author:      CliveS & Claude Opus 5.5
# Date:        23-09-2026
# Version:     1.0

from unittest.mock import MagicMock


class FakeDev:
    def __init__(self, shared=None):
        self.name = "Test Plug"
        self.sharedProps = dict(shared or {})
        self.shared_writes = 0

    def replaceSharedPropsOnServer(self, props):
        self.sharedProps = dict(props)
        self.shared_writes += 1


def _plugin(mod):
    p = mod.Plugin.__new__(mod.Plugin)
    p.logger = MagicMock()
    return p


def test_the_merge_keeps_the_user_and_never_narrows_star(plugin_mod):
    assert plugin_mod.merge_sql_logger_ignore("") == "countsOnTime, sysUptime, wifiRssi"
    assert plugin_mod.merge_sql_logger_ignore("voltage") == \
        "voltage, countsOnTime, sysUptime, wifiRssi"
    assert plugin_mod.merge_sql_logger_ignore("WIFIRSSI, sysuptime, CountsOnTime") is None
    assert plugin_mod.merge_sql_logger_ignore(" * ") is None


def test_the_list_is_written_once(plugin_mod):
    p = _plugin(plugin_mod)
    dev = FakeDev()
    p._keep_churn_out_of_sql_logger(dev)
    p._keep_churn_out_of_sql_logger(dev)
    assert dev.sharedProps["sqlLoggerIgnoreStates"] == "countsOnTime, sysUptime, wifiRssi"
    assert dev.shared_writes == 1


def test_a_failed_write_is_a_warning_not_a_crash(plugin_mod):
    p = _plugin(plugin_mod)
    dev = FakeDev()

    def boom(props):
        raise RuntimeError("server said no")
    dev.replaceSharedPropsOnServer = boom
    p._keep_churn_out_of_sql_logger(dev)
    assert p.logger.warning.called


def test_start_comm_calls_it(plugin_mod):
    import ast
    import inspect
    src = inspect.getsource(plugin_mod.Plugin.deviceStartComm)
    calls = [n for n in ast.walk(ast.parse(src.strip() and "\n".join(
        l[4:] if l.startswith("    ") else l for l in src.splitlines())))
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "_keep_churn_out_of_sql_logger"]
    assert calls, "deviceStartComm no longer applies the SQL Logger ignore list"
