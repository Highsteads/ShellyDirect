#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    test_plugin.py
# Description: Unit tests for ShellyDirect plugin (runs without Indigo installed)
# Author:      CliveS & Claude Sonnet 4.6
# Date:        23-03-2026
# Version:     1.0

import re
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

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

# Build path relative to this test file
_plugin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")

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
    """Return a thin object that carries plugin instance state for unit tests."""
    obj = MagicMock()
    obj.rate_source     = prefs_overrides.get("rate_source",     "disabled")
    obj.fixed_rate      = prefs_overrides.get("fixed_rate",      "")
    obj.rate_var        = prefs_overrides.get("rate_var",        "elec_unit_rate_p")
    obj.currency_prefix = prefs_overrides.get("currency_prefix", "")
    obj.currency_suffix = prefs_overrides.get("currency_suffix", "p")
    obj.stale_minutes   = prefs_overrides.get("stale_minutes",   10)
    obj.triggers        = prefs_overrides.get("triggers",        [])
    obj.power_alert_active = {}
    obj.last_seen       = {}
    return obj


def _calc_cost(obj, kwh):
    """Isolated copy of Plugin._calc_cost for testing."""
    pre = obj.currency_prefix
    suf = obj.currency_suffix

    def _format(value):
        dp = 1 if (not pre and suf) else 2
        return f"{pre}{value:.{dp}f}{suf}"

    if obj.rate_source == "disabled":
        return 0.0, ""
    if obj.rate_source == "fixed":
        try:
            rate = float(obj.fixed_rate)
            cost = kwh * rate
            return cost, _format(cost)
        except (ValueError, TypeError):
            return 0.0, ""
    if obj.rate_source == "variable":
        try:
            rate = float(indigo_mock.variables[obj.rate_var].value)
            cost = kwh * rate
            return cost, _format(cost)
        except Exception:
            return 0.0, ""
    return 0.0, ""


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


def _track_energy(total_wh, entry, today_str, month_str):
    """Isolated copy of energy baseline arithmetic from _track_energy."""
    if "day_baseline_wh" not in entry or total_wh < entry.get("day_baseline_wh", 0):
        entry["day_baseline_wh"] = total_wh
        entry["day_date"]        = today_str
    if "month_baseline_wh" not in entry or total_wh < entry.get("month_baseline_wh", 0):
        entry["month_baseline_wh"] = total_wh
        entry["month_date"]        = month_str
    today_kwh = max(0.0, (total_wh - entry["day_baseline_wh"])   / 1000.0)
    month_kwh = max(0.0, (total_wh - entry["month_baseline_wh"]) / 1000.0)
    return today_kwh, month_kwh, entry


def _is_stale_webhook_url(url, wanted_urls):
    """Isolated stale detection: any shellyEvent URL not in wanted_urls is stale."""
    if url in wanted_urls:
        return False
    return "shellyEvent" in url


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
        errs = _validate_subnet("192.168.4.1")
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
        self.assertEqual(_validate_ip("192.168.4.10"), {})

    def test_empty_fails(self):
        self.assertIn("ip_address", _validate_ip(""))

    def test_three_octets_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.4"))

    def test_non_numeric_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.4.x"))

    def test_out_of_range_fails(self):
        self.assertIn("ip_address", _validate_ip("192.168.4.256"))

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


class TestCalcCost(unittest.TestCase):

    def test_disabled_returns_zero_empty(self):
        p = make_plugin(rate_source="disabled")
        cost, ui = _calc_cost(p, 1.5)
        self.assertEqual(cost, 0.0)
        self.assertEqual(ui, "")

    def test_fixed_rate_pence(self):
        p = make_plugin(rate_source="fixed", fixed_rate="24.5",
                        currency_prefix="", currency_suffix="p")
        cost, ui = _calc_cost(p, 1.0)
        self.assertAlmostEqual(cost, 24.5)
        self.assertEqual(ui, "24.5p")

    def test_fixed_rate_pence_one_dp(self):
        """Pence (suffix-only) must display 1dp."""
        p = make_plugin(rate_source="fixed", fixed_rate="24.5",
                        currency_prefix="", currency_suffix="p")
        _, ui = _calc_cost(p, 2.0)
        self.assertEqual(ui, "49.0p")

    def test_fixed_rate_dollars_two_dp(self):
        """Dollar prefix must display 2dp."""
        p = make_plugin(rate_source="fixed", fixed_rate="0.12",
                        currency_prefix="$", currency_suffix="")
        cost, ui = _calc_cost(p, 1.0)
        self.assertAlmostEqual(cost, 0.12)
        self.assertEqual(ui, "$0.12")

    def test_fixed_rate_euro(self):
        p = make_plugin(rate_source="fixed", fixed_rate="0.28",
                        currency_prefix="EUR", currency_suffix="")
        cost, ui = _calc_cost(p, 1.0)
        self.assertAlmostEqual(cost, 0.28)
        self.assertTrue(ui.startswith("EUR"))

    def test_fixed_rate_invalid_returns_zero(self):
        p = make_plugin(rate_source="fixed", fixed_rate="not_a_number")
        cost, ui = _calc_cost(p, 1.0)
        self.assertEqual(cost, 0.0)
        self.assertEqual(ui, "")

    def test_fixed_rate_zero_kwh(self):
        p = make_plugin(rate_source="fixed", fixed_rate="24.5",
                        currency_prefix="", currency_suffix="p")
        cost, ui = _calc_cost(p, 0.0)
        self.assertAlmostEqual(cost, 0.0)
        self.assertEqual(ui, "0.0p")

    def test_variable_rate_success(self):
        p = make_plugin(rate_source="variable", rate_var="elec_unit_rate_p",
                        currency_prefix="", currency_suffix="p")
        indigo_mock.variables["elec_unit_rate_p"] = MagicMock()
        indigo_mock.variables["elec_unit_rate_p"].value = "22.0"
        cost, ui = _calc_cost(p, 1.0)
        self.assertAlmostEqual(cost, 22.0)
        self.assertEqual(ui, "22.0p")

    def test_variable_rate_missing_var_returns_zero(self):
        p = make_plugin(rate_source="variable", rate_var="nonexistent_var")
        indigo_mock.variables.__getitem__.side_effect = KeyError("nonexistent_var")
        cost, ui = _calc_cost(p, 1.0)
        self.assertEqual(cost, 0.0)
        self.assertEqual(ui, "")
        indigo_mock.variables.__getitem__.side_effect = None

    def test_fractional_kwh(self):
        p = make_plugin(rate_source="fixed", fixed_rate="24.0",
                        currency_prefix="", currency_suffix="p")
        cost, _ = _calc_cost(p, 0.5)
        self.assertAlmostEqual(cost, 12.0)


class TestTrackEnergy(unittest.TestCase):

    def test_first_reading_sets_baseline(self):
        entry = {}
        today_kwh, month_kwh, entry = _track_energy(5000, entry, "2026-03-23", "2026-03")
        self.assertEqual(entry["day_baseline_wh"],   5000)
        self.assertEqual(entry["month_baseline_wh"], 5000)
        self.assertEqual(today_kwh,  0.0)
        self.assertEqual(month_kwh,  0.0)

    def test_energy_consumed_since_baseline(self):
        entry = {"day_baseline_wh": 5000, "day_date": "2026-03-23",
                 "month_baseline_wh": 4000, "month_date": "2026-03"}
        today_kwh, month_kwh, _ = _track_energy(6000, entry, "2026-03-23", "2026-03")
        self.assertAlmostEqual(today_kwh,  1.0)
        self.assertAlmostEqual(month_kwh,  2.0)

    def test_meter_rollover_resets_baseline(self):
        """If total_wh drops below baseline (rollover/replacement), baseline resets."""
        entry = {"day_baseline_wh": 9999, "day_date": "2026-03-23",
                 "month_baseline_wh": 9999, "month_date": "2026-03"}
        today_kwh, month_kwh, entry = _track_energy(100, entry, "2026-03-23", "2026-03")
        self.assertEqual(entry["day_baseline_wh"], 100)
        self.assertEqual(today_kwh, 0.0)

    def test_no_negative_kwh(self):
        """Energy must never go negative."""
        entry = {"day_baseline_wh": 5000, "day_date": "2026-03-23",
                 "month_baseline_wh": 5000, "month_date": "2026-03"}
        today_kwh, _, _ = _track_energy(4999, entry, "2026-03-23", "2026-03")
        self.assertEqual(today_kwh, 0.0)

    def test_conversion_wh_to_kwh(self):
        entry = {"day_baseline_wh": 0, "day_date": "2026-03-23",
                 "month_baseline_wh": 0, "month_date": "2026-03"}
        today_kwh, _, _ = _track_energy(2500, entry, "2026-03-23", "2026-03")
        self.assertAlmostEqual(today_kwh, 2.5)


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


class TestStaleWebhookDetection(unittest.TestCase):

    def test_wanted_url_not_stale(self):
        url     = "http://192.168.100.160:8178/shellyEvent?devId=100&type=switch&state=on"
        wanted  = {url}
        self.assertFalse(_is_stale_webhook_url(url, wanted))

    def test_old_device_id_is_stale(self):
        old_url = "http://192.168.100.160:8178/shellyEvent?devId=9999&type=switch&state=on"
        new_url = "http://192.168.100.160:8178/shellyEvent?devId=100&type=switch&state=on"
        wanted  = {new_url}
        self.assertTrue(_is_stale_webhook_url(old_url, wanted))

    def test_non_plugin_url_not_stale(self):
        url    = "http://192.168.100.160:8080/other_endpoint?foo=bar"
        wanted = set()
        self.assertFalse(_is_stale_webhook_url(url, wanted))

    def test_old_server_ip_is_stale(self):
        old_url = "http://192.168.100.50:8178/shellyEvent?devId=100&type=switch&state=on"
        new_url = "http://192.168.100.160:8178/shellyEvent?devId=100&type=switch&state=on"
        wanted  = {new_url}
        self.assertTrue(_is_stale_webhook_url(old_url, wanted))

    def test_empty_wanted_any_plugin_url_is_stale(self):
        url    = "http://192.168.100.160:8178/shellyEvent?devId=42&type=button&event=single"
        self.assertTrue(_is_stale_webhook_url(url, set()))


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

if __name__ == "__main__":
    unittest.main(verbosity=2)
