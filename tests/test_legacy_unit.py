#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_legacy_unit.py
# Description: Unit tests for ShellyDirect plugin (runs without Indigo installed).
#              Moved out of the plugin bundle to repo-root tests/ in v3.16.0 —
#              tests must never ship inside an .indigoPlugin.
# Author:      CliveS & Claude Sonnet 4.6
# Date:        23-03-2026
# Version:     1.0

import re
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal Indigo mock — must be in place before importing plugin.py
# ---------------------------------------------------------------------------

indigo_mock = types.ModuleType("indigo")

# Exceptions and basic types
indigo_mock.PluginBase       = object
indigo_mock.Dict             = dict
indigo_mock.List             = list
indigo_mock.Server           = MagicMock()
indigo_mock.server           = MagicMock()
indigo_mock.server.version   = "2025.1"
indigo_mock.server.apiVersion = "3.0"

# Device action constants
kDeviceAction = MagicMock()
kDeviceAction.TurnOn        = "TurnOn"
kDeviceAction.TurnOff       = "TurnOff"
kDeviceAction.Toggle        = "Toggle"
kDeviceAction.RequestStatus = "RequestStatus"
indigo_mock.kDeviceAction   = kDeviceAction

kDimmerAction = MagicMock()
kDimmerAction.TurnOn        = "TurnOn"
kDimmerAction.TurnOff       = "TurnOff"
kDimmerAction.Toggle        = "Toggle"
kDimmerAction.SetBrightness = "SetBrightness"
kDimmerAction.BrightenBy    = "BrightenBy"
kDimmerAction.DimBy         = "DimBy"
indigo_mock.kDimmerAction   = kDimmerAction

indigo_mock.devices   = MagicMock()
indigo_mock.variables = MagicMock()
indigo_mock.variable  = MagicMock()
indigo_mock.trigger   = MagicMock()

sys.modules["indigo"] = indigo_mock

# ---------------------------------------------------------------------------
# Import module-level constants only (avoid Plugin() instantiation)
# ---------------------------------------------------------------------------

import importlib.util, os

# plugin.py lives in the bundle; this file lives in repo-root tests/
_REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_plugin_path = os.path.join(_REPO_ROOT, "ShellyDirect.indigoPlugin",
                            "Contents", "Server Plugin", "plugin.py")

_spec   = importlib.util.spec_from_file_location("plugin", _plugin_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules["plugin"] = _module

# indigo is already in sys.modules as our mock — exec_module will pick it up
try:
    _spec.loader.exec_module(_module)
except Exception:
    pass  # Plugin() __init__ fails without full Indigo — constants are still defined

APP_INFO     = _module.APP_INFO
RGBW_EFFECTS = _module.RGBW_EFFECTS
PUSH_ONLY_TYPES = _module.PUSH_ONLY_TYPES
LIGHT_TYPES     = _module.LIGHT_TYPES
INPUT_TYPES     = _module.INPUT_TYPES
PLUGIN_ID       = _module.PLUGIN_ID
WEBHOOK_PORT    = _module.WEBHOOK_PORT
VAR_FOLDER      = _module.VAR_FOLDER


# ---------------------------------------------------------------------------
# Helpers: lightweight plugin-method-under-test runner
# (instantiates no Indigo objects — just calls the logic directly)
# ---------------------------------------------------------------------------

def make_plugin(**prefs_overrides):
    """Return a thin object that carries plugin instance state for unit tests.

    v3.12: the rate/cost fields (rate_source, fixed_rate, rate_var,
    currency_prefix/suffix) and the _calc_cost helper + its TestCalcCost suite
    were REMOVED — they tested an isolated copy of a per-kWh cost feature that
    does not exist anywhere in plugin.py (10 phantom tests giving false
    confidence, found by the 16-Jul-2026 deep review)."""
    obj = MagicMock()
    obj.stale_minutes   = prefs_overrides.get("stale_minutes",   10)
    obj.triggers        = prefs_overrides.get("triggers",        [])
    obj.power_alert_active = {}
    obj.last_seen       = {}
    return obj


def _sanitise_var_name(s):
    """Isolated copy of Plugin._sanitise_var_name."""
    return re.sub(r"[^A-Za-z0-9]", "_", s).lower().strip("_")


def _validate_subnet(raw):
    """Isolated copy of subnet validation from validatePrefsConfigUi."""
    errors = {}
    raw = raw.strip()
    if not raw:
        errors["discovery_subnets"] = "required"
        return errors
    for s in raw.split(","):
        s = s.strip()
        parts = s.split(".")
        if len(parts) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            errors["discovery_subnets"] = f"Invalid subnet '{s}'"
            break
    return errors


def _validate_ip(ip):
    """Isolated copy of IP validation from validateDeviceConfigUi."""
    errors = {}
    ip = ip.strip()
    if not ip:
        errors["ip_address"] = "required"
        return errors
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        errors["ip_address"] = "invalid"
    return errors


def _fire_trigger(obj, type_id, dev_id, event_props=None):
    """Isolated copy of Plugin._fire_trigger."""
    fired = []
    for trigger in obj.triggers:
        if trigger.pluginTypeId != type_id:
            continue
        t_dev = trigger.pluginProps.get("deviceId", "any")
        if t_dev and t_dev != "any" and str(dev_id) != t_dev:
            continue
        if type_id == "inputButtonPress" and event_props:
            t_input = trigger.pluginProps.get("inputId", "any")
            t_press = trigger.pluginProps.get("pressType", "any")
            if t_input != "any" and t_input != str(event_props.get("input_id", "0")):
                continue
            if t_press != "any" and t_press != event_props.get("press_type", ""):
                continue
        fired.append(trigger)
    return fired


# NB (v3.12): the _track_energy and _is_stale_webhook_url ISOLATED COPIES and
# their test classes were removed — both had drifted from the real algorithms
# (in-place day rollover; devId-aware stale test). The REAL methods are now
# tested directly in repo tests/test_v312_fixes.py.

# ===========================================================================
# Test classes
# ===========================================================================

class TestConstants(unittest.TestCase):

    def test_plugin_id_format(self):
        self.assertTrue(PLUGIN_ID.startswith("com.clives."))

    def test_webhook_port_nonstandard(self):
        # Must not clash with IWS (8176) or other common ports
        self.assertNotEqual(WEBHOOK_PORT, 8176)
        self.assertNotEqual(WEBHOOK_PORT, 80)
        self.assertNotEqual(WEBHOOK_PORT, 443)

    def test_var_folder_name(self):
        self.assertEqual(VAR_FOLDER, "ShellyDirect")

    def test_app_info_structure(self):
        for key, val in APP_INFO.items():
            self.assertIsInstance(key, str, f"{key}: key must be str")
            self.assertEqual(len(val), 4,  f"{key}: tuple must have 4 elements")
            label, has_pm, type_id, channels = val
            self.assertIsInstance(label,    str,  f"{key}: label must be str")
            self.assertIsInstance(has_pm,   bool, f"{key}: has_pm must be bool")
            self.assertIsInstance(type_id,  str,  f"{key}: type_id must be str")
            self.assertIsInstance(channels, int,  f"{key}: channels must be int")
            self.assertGreaterEqual(channels, 1)

    def test_app_info_type_ids_known(self):
        known = {"shellyRelay", "shellyUni", "shellyCover", "shellyDimmer",
                 "shellyRGBW", "shellyEM", "shellyI4", "shellyHT",
                 "shellySmoke", "shellyFlood"}
        for key, (_, _, type_id, _) in APP_INFO.items():
            self.assertIn(type_id, known, f"{key}: unknown type_id '{type_id}'")

    def test_rgbw_effects_keys_are_numeric_strings(self):
        for k in RGBW_EFFECTS:
            self.assertTrue(k.isdigit(), f"Effect key '{k}' must be numeric string")

    def test_rgbw_effects_zero_is_static(self):
        self.assertIn("Static", RGBW_EFFECTS["0"])

    def test_push_only_types_are_sensors(self):
        for t in PUSH_ONLY_TYPES:
            self.assertTrue(t.startswith("shelly"))

    def test_light_types_subset(self):
        self.assertIn("shellyDimmer", LIGHT_TYPES)
        self.assertIn("shellyRGBW",   LIGHT_TYPES)

    def test_input_types_have_buttons(self):
        self.assertIn("shellyRelay", INPUT_TYPES)
        self.assertIn("shellyI4",    INPUT_TYPES)


class TestSubnetValidation(unittest.TestCase):

    def test_valid_single_subnet(self):
        self.assertEqual(_validate_subnet("192.168.4"), {})

    def test_valid_multiple_subnets(self):
        self.assertEqual(_validate_subnet("192.168.4, 10.0.1"), {})

    def test_empty_string_fails(self):
        errs = _validate_subnet("")
        self.assertIn("discovery_subnets", errs)

    def test_full_ip_fails(self):
        errs = _validate_subnet("192.168.1.1")
        self.assertIn("discovery_subnets", errs)

    def test_non_numeric_fails(self):
        errs = _validate_subnet("192.168.abc")
        self.assertIn("discovery_subnets", errs)

    def test_out_of_range_octet_fails(self):
        errs = _validate_subnet("192.168.256")
        self.assertIn("discovery_subnets", errs)

    def test_two_octets_fails(self):
        errs = _validate_subnet("192.168")
        self.assertIn("discovery_subnets", errs)

    def test_whitespace_trimmed(self):
        self.assertEqual(_validate_subnet("  192.168.4  "), {})

    def test_mixed_valid_invalid_fails(self):
        errs = _validate_subnet("192.168.4, bad")
        self.assertIn("discovery_subnets", errs)


class TestIPValidation(unittest.TestCase):

    def test_valid_ip(self):
        self.assertEqual(_validate_ip("192.168.1.10"), {})

    def test_empty_fails(self):
        self.assertIn("ip_address", _validate_ip(""))

    def test_three_octets_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.4"))

    def test_non_numeric_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.1.x"))

    def test_out_of_range_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.1.256"))

    def test_zero_address_valid(self):
        self.assertEqual(_validate_ip("0.0.0.0"), {})

    def test_broadcast_valid(self):
        self.assertEqual(_validate_ip("255.255.255.255"), {})


class TestSanitiseVarName(unittest.TestCase):

    def test_spaces_become_underscores(self):
        self.assertEqual(_sanitise_var_name("Garage Door"), "garage_door")

    def test_special_chars_removed(self):
        # Trailing ! becomes _ then is stripped by .strip("_")
        self.assertEqual(_sanitise_var_name("Device #1!"), "device__1")

    def test_already_clean(self):
        self.assertEqual(_sanitise_var_name("MyDevice"), "mydevice")

    def test_leading_trailing_underscores_stripped(self):
        result = _sanitise_var_name("_test_")
        self.assertFalse(result.startswith("_"))
        self.assertFalse(result.endswith("_"))

    def test_numbers_preserved(self):
        self.assertIn("4", _sanitise_var_name("Shelly 4PM"))

    def test_unicode_replaced(self):
        result = _sanitise_var_name("Caf\u00e9")
        self.assertNotIn("\u00e9", result)


class TestFireTrigger(unittest.TestCase):

    def _make_trigger(self, type_id, device_id="any", input_id="any", press_type="any"):
        t = MagicMock()
        t.pluginTypeId = type_id
        t.pluginProps  = {"deviceId": device_id, "inputId": input_id, "pressType": press_type}
        t.id           = id(t)
        return t

    def test_offline_trigger_fires_for_matching_device(self):
        t = self._make_trigger("deviceWentOffline", device_id="42")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "deviceWentOffline", 42)
        self.assertIn(t, fired)

    def test_offline_trigger_skips_wrong_device(self):
        t = self._make_trigger("deviceWentOffline", device_id="99")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "deviceWentOffline", 42)
        self.assertNotIn(t, fired)

    def test_any_device_fires_all(self):
        t = self._make_trigger("deviceWentOffline", device_id="any")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "deviceWentOffline", 42)
        self.assertIn(t, fired)

    def test_wrong_event_type_not_fired(self):
        t = self._make_trigger("highPowerAlert", device_id="any")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "deviceWentOffline", 42)
        self.assertNotIn(t, fired)

    def test_button_press_all_filters(self):
        t = self._make_trigger("inputButtonPress", device_id="42",
                               input_id="1", press_type="double")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "inputButtonPress", 42,
                              {"input_id": "1", "press_type": "double"})
        self.assertIn(t, fired)

    def test_button_press_wrong_input_skipped(self):
        t = self._make_trigger("inputButtonPress", device_id="42",
                               input_id="2", press_type="any")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "inputButtonPress", 42,
                              {"input_id": "1", "press_type": "single"})
        self.assertNotIn(t, fired)

    def test_button_press_wrong_press_type_skipped(self):
        t = self._make_trigger("inputButtonPress", device_id="any",
                               input_id="any", press_type="long")
        p = make_plugin(triggers=[t])
        fired = _fire_trigger(p, "inputButtonPress", 42,
                              {"input_id": "0", "press_type": "single"})
        self.assertNotIn(t, fired)

    def test_multiple_triggers_all_matching(self):
        t1 = self._make_trigger("highPowerAlert", device_id="any")
        t2 = self._make_trigger("highPowerAlert", device_id="42")
        p  = make_plugin(triggers=[t1, t2])
        fired = _fire_trigger(p, "highPowerAlert", 42)
        self.assertIn(t1, fired)
        self.assertIn(t2, fired)

    def test_no_triggers_returns_empty(self):
        p = make_plugin(triggers=[])
        fired = _fire_trigger(p, "deviceWentOffline", 42)
        self.assertEqual(fired, [])


class TestMultiSubnetParsing(unittest.TestCase):

    def _parse_subnets(self, raw):
        return [s.strip() for s in raw.split(",") if s.strip()]

    def test_single_subnet(self):
        self.assertEqual(self._parse_subnets("192.168.4"), ["192.168.4"])

    def test_multiple_subnets(self):
        result = self._parse_subnets("192.168.4, 10.0.1, 172.16.0")
        self.assertEqual(result, ["192.168.4", "10.0.1", "172.16.0"])

    def test_trailing_comma_ignored(self):
        result = self._parse_subnets("192.168.4,")
        self.assertEqual(result, ["192.168.4"])

    def test_extra_spaces_stripped(self):
        result = self._parse_subnets("  192.168.4  ,  10.0.1  ")
        self.assertEqual(result, ["192.168.4", "10.0.1"])

    def test_empty_string_gives_empty_list(self):
        self.assertEqual(self._parse_subnets(""), [])


class TestAppInfoCoverage(unittest.TestCase):
    """Spot-checks on specific known device models."""

    def test_plus_plug_uk_is_relay_with_pm(self):
        label, has_pm, type_id, channels = APP_INFO["PlusPlugUK"]
        self.assertTrue(has_pm)
        self.assertEqual(type_id, "shellyRelay")
        self.assertEqual(channels, 1)

    def test_pro4pm_has_four_channels(self):
        _, _, _, channels = APP_INFO["Pro4PM"]
        self.assertEqual(channels, 4)

    def test_plus2pm_has_two_channels(self):
        _, _, _, channels = APP_INFO["Plus2PM"]
        self.assertEqual(channels, 2)

    def test_plus_ht_is_ht_type(self):
        _, _, type_id, _ = APP_INFO["PlusHT"]
        self.assertEqual(type_id, "shellyHT")

    def test_plus_rgbw_pm_is_rgbw(self):
        _, has_pm, type_id, _ = APP_INFO["PlusRGBWPM"]
        self.assertEqual(type_id, "shellyRGBW")
        self.assertTrue(has_pm)

    def test_pro_em_is_em_type(self):
        _, _, type_id, _ = APP_INFO["ProEM"]
        self.assertEqual(type_id, "shellyEM")

    def test_plus_i4_is_i4_type(self):
        _, _, type_id, _ = APP_INFO["PlusI4"]
        self.assertEqual(type_id, "shellyI4")

    def test_no_pm_on_plus1(self):
        _, has_pm, _, _ = APP_INFO["Plus1"]
        self.assertFalse(has_pm)


# ===========================================================================
# v3.6 regression tests — call the REAL Plugin methods (not isolated copies),
# so a future signature/logic change is caught instead of silently drifting.
# ===========================================================================

class TestPrefInt(unittest.TestCase):
    """Plugin._pref_int — guarded coercion of a pref/prop value (real staticmethod)."""

    def test_valid_string(self):
        self.assertEqual(_module.Plugin._pref_int({"x": "30"}, "x", 10), 30)

    def test_int_passthrough(self):
        self.assertEqual(_module.Plugin._pref_int({"x": 5}, "x", 10), 5)

    def test_blank_falls_back(self):
        self.assertEqual(_module.Plugin._pref_int({"x": ""}, "x", 10), 10)

    def test_missing_key_falls_back(self):
        self.assertEqual(_module.Plugin._pref_int({}, "x", 10), 10)

    def test_garbage_falls_back(self):
        self.assertEqual(_module.Plugin._pref_int({"x": "abc"}, "x", 10), 10)

    def test_none_falls_back(self):
        self.assertEqual(_module.Plugin._pref_int({"x": None}, "x", 10), 10)


class TestGetTotalWh(unittest.TestCase):
    """Plugin._get_total_wh — present->float, absent/bad->None (phantom-zero guard)."""

    def test_present_value(self):
        self.assertEqual(_module.Plugin._get_total_wh({"total": 1234.5}, "total"), 1234.5)

    def test_genuine_zero_is_a_real_reading(self):
        # A genuine 0 (fresh/reset meter) IS a value, not 'absent'.
        self.assertEqual(_module.Plugin._get_total_wh({"total": 0}, "total"), 0.0)

    def test_missing_key_is_none(self):
        self.assertIsNone(_module.Plugin._get_total_wh({}, "total"))

    def test_none_value_is_none(self):
        self.assertIsNone(_module.Plugin._get_total_wh({"total": None}, "total"))

    def test_non_dict_is_none(self):
        self.assertIsNone(_module.Plugin._get_total_wh(None, "total"))

    def test_non_numeric_is_none(self):
        self.assertIsNone(_module.Plugin._get_total_wh({"total": "n/a"}, "total"))


class TestCalcEnergyPhantomZero(unittest.TestCase):
    """Real Plugin._calc_energy plus the call-site phantom-zero guard."""

    @staticmethod
    def _stub():
        s = types.SimpleNamespace()
        s.energy_data  = {}
        s._energy_lock = threading.RLock()   # _calc_energy guards energy_data with this
        return s

    def test_baseline_and_accumulation(self):
        s = self._stub()
        today, _month = _module.Plugin._calc_energy(s, 1, 1000.0)
        self.assertEqual(today, 0.0)                      # first reading -> baseline
        today, _month = _module.Plugin._calc_energy(s, 1, 1500.0)
        self.assertAlmostEqual(today, 0.5)               # +500 Wh -> 0.5 kWh

    def test_genuine_meter_reset_rebaselines(self):
        # v3.16.2: a low reading is now HELD for confirmation before it is
        # believed, because a REPORTED `aenergy.total: 0` is indistinguishable
        # from a real reset on a single sample and used to zero the baseline —
        # publishing the whole lifetime total as "today" on the next poll. A
        # genuine reset persists, so it still re-baselines; it just takes the
        # second consecutive low reading.
        s = self._stub()
        _module.Plugin._calc_energy(s, 1, 5000.0)
        _module.Plugin._calc_energy(s, 1, 10.0)                   # power-cycled — strike one
        self.assertEqual(s.energy_data["1"]["day_baseline_wh"], 5000.0,
                         "a single low reading must be held, not believed")
        today, _month = _module.Plugin._calc_energy(s, 1, 12.0)   # strike two — believed
        self.assertEqual(today, 0.0)
        self.assertEqual(s.energy_data["1"]["day_baseline_wh"], 12.0)

    def test_reported_zero_does_not_zero_the_baseline(self):
        # The gap the v3.6 guard left open: it only filtered an ABSENT field.
        # A device REPORTING 0 handed a real 0.0 straight to _calc_energy.
        s = self._stub()
        _module.Plugin._calc_energy(s, 1, 100_000.0)
        _module.Plugin._calc_energy(s, 1, 120_000.0)
        today, _ = _module.Plugin._calc_energy(s, 1, 0.0)          # the glitch
        self.assertEqual(s.energy_data["1"]["day_baseline_wh"], 100_000.0)
        self.assertAlmostEqual(today, 20.0)                        # last known-good preserved
        today_after, _ = _module.Plugin._calc_energy(s, 1, 3_446_590.0)
        self.assertLess(today_after, 5000.0, "lifetime total leaked into today")

    def test_phantom_zero_is_filtered_before_calc(self):
        # The v3.6 fix: a poll missing the cumulative field yields None from
        # _get_total_wh, so the poll path skips _calc_energy and the baseline
        # is preserved (no phantom multi-thousand-kWh spike next poll).
        s = self._stub()
        _module.Plugin._calc_energy(s, 1, 5000.0)
        baseline_before = s.energy_data["1"]["day_baseline_wh"]
        total = _module.Plugin._get_total_wh({"voltage": 240.0}, "total")  # no 'total' key
        self.assertIsNone(total)
        if total is not None:                            # mirrors the guard in _poll_*
            _module.Plugin._calc_energy(s, 1, total)
        self.assertEqual(s.energy_data["1"]["day_baseline_wh"], baseline_before)


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
