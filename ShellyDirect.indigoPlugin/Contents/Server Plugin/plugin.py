#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Shelly Gen 2/3/4 direct-to-Indigo control plugin
#              Relay, Cover, Dimmer, RGBW, Energy Meter, Sensors
# Author:      CliveS & Claude Fable 5
# Date:        17-07-2026
# Version:     3.15
#
# v3.15 (17-07-2026) — Fable 5 deep-review improvements batch.
#   * NEW "Test Shelly Connection" menu item (estate convention): full banner
#     + live checks (listener up, server IP, subnets, every pollable device
#     probed) in one log dump made for support posts. Show Plugin Info gains
#     device counts + webhook-listener status (shared _banner_extras).
#   * Webhook listener port is a guarded pref (webhook_port, default 8178) —
#     a port collision used to leave the plugin permanently webhook-dead with
#     no user remedy; existing device hooks re-point automatically on reload.
#   * requirements.txt emptied: `requests` is pre-installed in Indigo's Python
#     (FlyingDiver-confirmed) — the old pin dragged a redundant requests +
#     certifi + urllib3 copy into Contents/Packages/ on every install.
#     Contents/Packages purged on deploy so imports fall through to Indigo's.
#   * Discovery: progress line every 64 IPs (sparse subnets used to mean
#     minutes of silence) and a summary naming configured devices that did
#     NOT respond to the scan.
#   * Heavy menu callbacks (Device Health Summary, Check Firmware, Reconfigure
#     Webhooks, the new connection test) run their serial network I/O in a
#     worker thread instead of blocking the menu.
#   * Shelly password field is secure="true" (masked in the dialog — NB Indigo
#     stores prefs in plain text either way; IndigoSecrets.py remains the
#     recommended home for credentials).
#   * plugin_utils.py refreshed from the master (duplicate-filter guard).
#   * Device-catalogue note: unknown apps are handled by the v3.9 component
#     classifier (+ v3.13's empty-classification skip and PM probe), so new
#     Gen3/Gen4 models classify correctly without APP_INFO entries — table
#     additions deliberately NOT made without verified app strings.
#
# v3.14 (17-07-2026) — Fable 5 deep-review batch 3 (lows + infos).
#   * Instantaneous relay readings (apower/voltage/current/tC) written only
#     when PRESENT — partial responses fabricated 0 W/0 V readings (the
#     non-energy edition of the v3.6 phantom-zero class).
#   * Webhook.Create responses checked — a failed create (20-hook cap) used to
#     log 'Webhooks OK' anyway; menuResetWebhooks reports a REAL device count
#     (_configure_webhooks now returns a result).
#   * Webhook poll stamping: a light webhook queues an immediate poll
#     (brightness isn't in the event — it stayed stale a full interval); a PM
#     relay's switch webhook keeps the poll cadence (frequent toggling used to
#     defer power/energy polling indefinitely).
#   * runConcurrentThread's WHOLE tick body guarded (a non-StopThread error
#     outside the device loop silently killed polling); deviceStartComm's
#     initial poll + webhook configure moved to a worker thread (startup used
#     to stall serially on offline devices).
#   * _is_cover_mode returns inconclusive on network failure — a transient
#     timeout used to permanently misclassify a 2PM as two relays; discovery
#     retries next run.
#   * Duplicate guard catches mixed identities (an IP-only record now adopts
#     the MAC another record stores for the same IP).
#   * _poll_i4 tolerates fewer than 4 inputs (component-classified devices).
#   * New props RMW lock (MAC backfill vs dynamic capture); energy CSV export
#     snapshots under the energy lock; energy JSON carries last_date in
#     __meta__ so the midnight boundary survives a CRASH (pluginPrefs only
#     flush on graceful shutdown).
#   * shellyHT gains a declared temperature state (its reading previously
#     landed only in the dead sensorValue); brightnessLevel declarations
#     removed from the two dimmer types (natively reserved — same class as
#     the v3.10 sensorValue cleanup); PluginConfig double separator replaced
#     by the new battery_stale_hours field.
#
# v3.13 (17-07-2026) — Fable 5 deep-review batch 2 (mediums).
#   * Webhook event handling EXTRACTED from the HTTP-handler closure into
#     Plugin._apply_webhook_event (+_qp/_qp_int/_qp_float helpers) — the push
#     path is finally unit-testable, per-field coercion is guarded (one blank/
#     unsubstituted token skips that field, not the whole request), and the
#     Shelly Uni's input events now write its declared input0/input1 states
#     (the sensorValue write was dead on a relay-class device).
#   * Stale-devId auto-repair rate-limited (one per source IP per 60s — a
#     chatty device used to spawn one repair thread PER REQUEST).
#   * _configure_webhooks: skips when server_ip is unconfigured (used to
#     install 'http://:8178/...' hooks), and consults the duplicate guard via
#     a 60s cache — deviceStartComm/menuResetWebhooks can no longer let a
#     duplicate record clobber the keeper's hooks between health checks
#     (_check_webhook_health also skips entirely without server_ip).
#   * Battery-sensor webhooks: real ${ev.*} macros and real event names
#     (temperature.change/humidity.change, smoke.alarm/_off, flood.alarm/_off)
#     — the old {token} placeholders were never substituted and two event
#     names didn't exist (per API docs; no battery sensor hardware in the
#     fleet to live-verify). _setup_sensor_webhook dedupes via Webhook.List
#     (duplicates used to accumulate on awake sensors every restart).
#   * Poll back-off: a failed poll stamps last_polled (was retried every 10s
#     tick) and 3+ consecutive failures stretch the retry to >=300s; battery
#     sensors get their own stale threshold (battery_stale_hours pref, default
#     12h — the global 10-minute rule made hourly reporters flap offline).
#   * Prefs: closedPrefsConfigUi keeps the IndigoSecrets-first precedence for
#     subnets + Shelly credentials (a dialog save used to drop it until
#     restart); blank Discovery Subnets is valid when the secret provides them.
#   * Discovery: BLU records no longer block their gateway's discovery; live
#     MAC verified on IP-match (hardware replaced at the same IP is re-bound
#     with a WARNING instead of silently misbound); scan snapshots maintained
#     during the run (DHCP-freed IP usable in the same pass); empty component
#     classification SKIPS instead of persisting a guessed relay; unknown
#     switch devices get one Switch.GetStatus PM probe (power data was
#     silently discarded on PM-capable unknowns).
#   * Remaining null-unsafe float()/int() pulls guarded; remaining bare
#     channel_id int() coercions swept to _pref_int.
#   * Tests 181 -> 199 (tests/test_v313_fixes.py): first-ever coverage for the
#     v3.11 repair back-off state machine, the extracted webhook applier, poll
#     back-off, battery threshold, secrets precedence, sensor-webhook dedup.
#
# v3.12 (17-07-2026) — Fable 5 deep-review batch 1 (highs; 80 confirmed findings
# total, fixed in severity batches).
#   * HIGH: _ensure_webhooks' stale test is now devId-AWARE — the old "any
#     shellyEvent URL not in MY wanted set is stale" rule made sibling channels
#     of multi-channel Shellys (Plus 2PM / Pro 4PM / 2-ch dimmers) perpetually
#     delete each other's webhooks: the exact ping-pong v3.11 fixed for
#     duplicate records survived for LEGITIMATE multi-channel devices (and the
#     v3.11 back-off never engaged because each repair's own recheck passed).
#     A hook is stale only when its parsed devId belongs to no live self-owned
#     device; deletion is per-hook and never removes a hook carrying a wanted URL.
#   * HIGH: discovery creates one device per channel for EVERY channel-
#     addressable type — the old gate (relays only) silently dropped channel 2+
#     of a Pro Dimmer 2PM or multi-EM1 device. Pro 3EM's num_ch=3 still means
#     3-PHASE (one device); ProEM corrected to its real 2 EM1 clamps. Cover
#     commands/polls honour channel_id (were hardcoded id=0).
#   * HIGH: EM energy wiring is component-correct per the Shelly API docs (NB
#     no EM hardware in the dev fleet to live-verify): 3-phase reads EMData
#     `total_act` (the old `total_act_energy` key never exists there — EM
#     energy was dead) with a full-phase-sum fallback; single-phase EM1
#     hardware reads EM1.GetStatus/EM1Data.GetStatus with the channel id (the
#     old EM.GetStatus call is not answered by EM1 components). Mirrored in
#     _midnight_reset.
#   * HIGH: a device offline at midnight no longer corrupts the day —
#     _calc_energy detects a stale day_date on the first poll of a new day,
#     banks the elapsed period as a history row and re-baselines in place
#     (month boundary likewise). _midnight_reset remains the exact-boundary owner.
#   * HIGH: RGBW colour is component-correct (per API docs — no RGBW hardware
#     in the fleet): Gen2+ rgb/rgbw profiles use RGB.Set/RGBW.Set + matching
#     GetStatus (profile probed once via Shelly.GetConfig and cached in a new
#     rgbw_profile prop); the Gen1-era Light.Set colour params never existed on
#     Gen2+. Set Effect now logs an honest WARNING (no Gen2+ RPC equivalent).
#     Cover tilt commands/status use the Gen2+ slat_pos field; cover poll no
#     longer crashes on present-but-null fields.
#   * Tests: phantom TestCalcCost suite REMOVED from test_plugin.py (10 tests
#     for a cost feature that does not exist in plugin.py), along with the
#     drifted _track_energy / _is_stale_webhook_url isolated copies — replaced
#     by 16 real-method tests in repo tests/test_v312_fixes.py (sibling
#     protection, orphan cleanup, multi-URL safety, devId boundary, energy
#     rollover, EM keys, RGBW profiles). Suite 185 -> 181 net (10 phantoms out).
#
# v3.11 (19-06-2026) — stop the perpetual webhook "missing - repairing" log churn.
# Root cause was two Indigo device records bound to the SAME physical Shelly (same
# MAC + IP): each 6-hourly health check saw only the other's webhooks, deleted them
# as stale and reinstalled its own, ping-ponging forever (amplified by the flaky
# .4.x 2.4GHz subnet dropping writes mid-repair as "no route").
# - NEW _duplicate_device_ids(): detects self-owned records colliding on the same
#   MAC (or IP when no MAC), keyed by channel_id so multi-channel devices and
#   BLU gateway-sharing are NOT flagged. _check_webhook_health now skips the
#   duplicate(s) entirely (keeping the lowest-id record) and logs ONE WARNING per
#   colliding identity naming the duplicate and telling the user to delete it.
# - NEW webhook repair back-off: after MAX_WEBHOOK_REPAIR_FAILS (3) consecutive
#   repairs that don't "stick" (unreachable mid-write / clobbered), the health
#   check stops the noisy delete/create/fail dance and stays quietly poll-only,
#   logging a single WARNING. A successful poll (_mark_online) clears the back-off
#   so a recovered device is retried. Repair now re-reads the hook list to confirm
#   it actually landed before counting the device repaired.
#
# v3.10 (13-06-2026) — remove redundant native sensorValue state declarations from the
# seven sensor device types (shellyHT, shellyI4, shellySmoke, shellyFlood, shellyEM,
# shellyBluButton, shellyBluRC4). Indigo rejected them at startup with "native state keys
# cannot be overriden (ignoring)"; sensorValue is provided natively for type="sensor"
# devices, so this is a behaviour-neutral fix that just clears the startup log noise.
#
# v3.9 (13-06-2026) — discovery: classify unknown-app devices from components.
# - Discovery previously fell back to "single relay, no PM" for any device whose
#   `app` was not in the curated APP_INFO table — so an unknown/new model that is
#   really a dimmer/cover/RGBW/multi-channel was created as the wrong Indigo type
#   (or lost channels). New module-level classifier `detect_shelly_devices(
#   device_info, config_keys)` reads the live Shelly.GetConfig component set
#   (switch/light/cover/rgb/em/input) and returns one device spec per channel;
#   the unknown-app branch of _discover_thread now uses it (known apps still go
#   straight through the table, no extra RPC). Future-proofs discovery against
#   new Shelly models. No change for known-app or already-configured devices.
# - NEW device-zoo test layer (tests/): declarative self-description -> expected
#   per-channel devices contract + invariants (known-types-only, never-BLU-from-
#   IP-discovery, distinct channels, deterministic). Real fleet captures in
#   tests/zoo_real/. Harvested from Simon's indigo-matter "device zoo" method.
#
# v3.7 (06-06-2026) — deep-review batch 2 (sensible mediums):
# - energy_data now guarded by a reentrant lock (RLock): _calc_energy,
#   _midnight_reset and _save_energy_data no longer race the poll loop vs
#   action-triggered polls.
# - Midnight reset idempotent across a restart spanning midnight: last_date is
#   persisted to pluginPrefs["lastEnergyDate"] and read back on startup, so the
#   daily reset still fires on the first tick instead of being silently skipped.
# - Webhook do_POST: Content-Length coercion guarded + 64 KB body cap (the
#   unauthenticated LAN listener can't be made to allocate an unbounded buffer).
# - High Power Alert event selector (getPMDevices) now lists only shellyRelay PM
#   devices — the only type whose poll evaluates the threshold (was offering
#   dimmer/RGBW PM devices whose trigger could never fire).
# - Bundled IndigoSecrets_example.py now documents the ShellyDirect keys
#   (INDIGO_SERVER_IP, SHELLY_USERNAME/PASSWORD, SHELLY_DISCOVERY_SUBNETS),
#   matching the master template.
#
# v3.6 (06-06-2026) — deep-review batch 1 (HIGH + robustness):
# - Energy phantom-zero FIX: a successful poll missing aenergy.total /
#   total_act_energy used to default to 0, tripping _calc_energy's counter-reset
#   rule and zeroing the day/month baseline -> phantom multi-thousand-kWh spike.
#   New _get_total_wh() returns None for an absent field; _poll_relay/_poll_em/
#   _midnight_reset now skip the energy update and preserve last-known-good.
# - runConcurrentThread hardened: whole per-device body wrapped, poll_interval
#   coercion guarded (_pref_int), midnight reset wrapped — one bad device/error
#   can no longer kill the polling thread.
# - _poll_* generic except now marks the device offline (a device returning
#   malformed JSON no longer stays "online" forever).
# - __init__/closedPrefsConfigUi int() coercions guarded via _pref_int.
# - shutdown() now server_close()s the webhook socket (FD leak on reload).
# - Energy JSON read/write use encoding="utf-8"; hardcoded "192.168.4" fallback
#   removed; dead `base` var in _check_webhook_health removed. +15 tests.
#
# v3.4 (23-05-2026): Millisecond timestamp [HH:MM:SS.mmm] prefix on every
# log line via plugin_utils.install_timestamp_filter() — matches Device
# Activity Monitor convention. Module-level log() helper bumped to
# ms-precision so indigo.server.log()-routed lines also match.
# New "Toggle Timestamps in Log" menu item.
#
# v3.2 (16-05-2026):
# - Standardised logging: replaced all self.logger.info/warning/error calls
#   (109 sites) with the project-standard log() helper that prefixes each
#   entry with [HH:MM:SS]. self.logger.debug calls retained — they remain
#   filtered by the user-configurable plugin log level handler.
#
# v3.1 (15-05-2026):
# - Demoted webhook switch/light echo log lines to debug to avoid duplicate
#   log entries (the action handler's `sent "name" on/off` line is the single
#   info-level record per device action). External physical toggles still
#   update device state; enable debug logging to see the webhook echo.
#
# v3.0 (13-05-2026) — BREAKING:
# - State IDs renamed from snake_case to camelCase across Devices.xml and
#   plugin.py (16 IDs total): power_watts -> powerWatts, current_amps ->
#   currentAmps, energy_kwh_today/month -> energyKwhToday/Month, device_temp_c
#   -> deviceTempC, addon_temp_c -> addonTempC, battery_pct -> batteryPct,
#   voltage_a/b/c -> voltageA/B/C, current_a/b/c -> currentA/B/C, power_a/b/c
#   -> powerA/B/C. Indigo state IDs must be camelCase ASCII (the underscore
#   form worked statically but violated CLAUDE.md naming rule and would have
#   blown up if these states were ever declared dynamically). EXISTING
#   TRIGGERS AND CONTROL PAGES REFERENCING THE OLD STATE NAMES WILL NEED TO
#   BE UPDATED. State history on existing Indigo devices is lost.
# - Indigo server IP moved to IndigoSecrets.INDIGO_SERVER_IP with PluginConfig
#   fallback. The hardcoded server IP removed from plugin.py (2 places)
#   and PluginConfig.xml defaultValue. ERROR-log if neither source resolves.
#
# v2.7 (10-05-2026):
# - Capture every Shelly RPC field as a dynamic Indigo state.  The curated
#   per-device-type state lists in Devices.xml stay exactly as-is (so existing
#   triggers and control pages keep working), but anything ELSE that the
#   Shelly returns from Switch.GetStatus / Light.GetStatus / EM.GetStatus /
#   Cover.GetStatus / Sys.GetStatus is now imported as a dynamic state on
#   the matching Indigo device.  This surfaces:
#     * power factor (pf), frequency (freq)
#     * total returned/exported energy (total_returned_energy)
#     * last command source (source: "MQTT", "HTTP", "switch")
#     * Wi-Fi RSSI, uptime, free RAM/flash, restart_required (diagnostics)
#     * any future Shelly firmware additions, automatically.
# - Implementation copies the Z2M v1.7.1 / Ecowitt v2.1.0 pattern: strict
#   ASCII state-id sanitiser, declare-before-write phase ordering to avoid
#   one-off "state key not defined" errors on first encounter, and a
#   getDeviceStateList override that returns a fresh list copy per call.
# - Plugin version is now read dynamically from Info.plist (self.pluginVersion);
#   no separate Python constant.

import csv
import http.server
import indigo
import json
import logging
import os
import re
import socketserver
import sys as _sys
import threading
import time
import urllib.parse
from datetime import datetime, date
from requests.auth import HTTPDigestAuth

import requests

_sys.path.insert(0, os.getcwd())
try:
    from plugin_utils import log_startup_banner
except ImportError:
    log_startup_banner = None
try:
    from plugin_utils import install_timestamp_filter
except ImportError:
    install_timestamp_filter = None

_sys.path.insert(0, "/Library/Application Support/Perceptive Automation")
# Per-key try/except so a missing single key does not blank the others.
try:
    from IndigoSecrets import INDIGO_SERVER_IP as _SECRETS_INDIGO_IP
except ImportError:
    _SECRETS_INDIGO_IP = ""
try:
    from IndigoSecrets import SHELLY_USERNAME as _SECRETS_SHELLY_USER
except ImportError:
    _SECRETS_SHELLY_USER = ""
try:
    from IndigoSecrets import SHELLY_PASSWORD as _SECRETS_SHELLY_PASS
except ImportError:
    _SECRETS_SHELLY_PASS = ""
try:
    from IndigoSecrets import SHELLY_DISCOVERY_SUBNETS as _SECRETS_SHELLY_SUBNETS
except ImportError:
    _SECRETS_SHELLY_SUBNETS = ""


def log(message, level="INFO"):
    indigo.server.log(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}", level=level)


PLUGIN_ID    = "com.clives.indigoplugin.shellydirect"
WEBHOOK_PORT = 8178   # Plugin-owned HTTP listener
VAR_FOLDER   = "ShellyDirect"
HISTORY_DAYS = 30     # Rolling daily energy history retained per device

# Webhook repair backoff: after this many consecutive health-check repairs that
# fail to "stick" (device unreachable mid-write, or a duplicate record clobbering
# them), stop the noisy delete/create/fail dance and stay quietly poll-only until
# the device next polls successfully (which resets the counter via _mark_online).
MAX_WEBHOOK_REPAIR_FAILS = 3

# ---------------------------------------------------------------------------
# APP_INFO  {app_field: (display_label, has_pm, device_type_id, num_channels)}
# device_type_id matches Devices.xml <Device id="...">
# num_channels > 1 triggers multi-device creation in discovery
# ---------------------------------------------------------------------------
APP_INFO = {
    # Single relay ---------------------------------------------------------
    "PlusPlugUK":    ("Plus Plug UK",          True,  "shellyRelay",  1),
    "PlugUK":        ("Plug UK Gen 4",         True,  "shellyRelay",  1),
    "PlugSG3":       ("Plug S Gen 3",          True,  "shellyRelay",  1),
    "PlusPlugS":     ("Plus Plug S",           True,  "shellyRelay",  1),
    "PlusPlugIT":    ("Plus Plug IT",          True,  "shellyRelay",  1),
    "PlusPlugUS":    ("Plus Plug US",          True,  "shellyRelay",  1),
    "Plus1":         ("Plus 1",               False,  "shellyRelay",  1),
    "Plus1PM":       ("Plus 1PM",              True,  "shellyRelay",  1),
    "Pro1":          ("Pro 1",                False,  "shellyRelay",  1),
    "Pro1PM":        ("Pro 1PM",               True,  "shellyRelay",  1),
    "Pro1G3":        ("Pro 1 Gen 3",          False,  "shellyRelay",  1),
    "Pro1PMG3":      ("Pro 1PM Gen 3",         True,  "shellyRelay",  1),
    "Mini1G3":       ("1 Mini Gen 3",         False,  "shellyRelay",  1),
    "Mini1PMG3":     ("1PM Mini Gen 3",        True,  "shellyRelay",  1),
    "Mini1G3DC":     ("1 Mini Gen 3 DC",      False,  "shellyRelay",  1),
    "Mini1PMG3DC":   ("1PM Mini Gen 3 DC",     True,  "shellyRelay",  1),
    "S1G4":          ("Shelly 1 Gen 4",       False,  "shellyRelay",  1),
    "S1PMG4":        ("1PM Gen 4",             True,  "shellyRelay",  1),
    # Multi-channel relay (discovery creates N devices, probes cover mode)
    "Plus2PM":       ("Plus 2PM",              True,  "shellyRelay",  2),
    "Pro2":          ("Pro 2",                False,  "shellyRelay",  2),
    "Pro2PM":        ("Pro 2PM",               True,  "shellyRelay",  2),
    "Pro4PM":        ("Pro 4PM",               True,  "shellyRelay",  4),
    # Universal ------------------------------------------------------------
    "PlusUni":       ("Plus Uni",             False,  "shellyUni",    1),
    # Dimmer ---------------------------------------------------------------
    "PlusDimmerUL":  ("Plus Dimmer 0/1-10V",   True,  "shellyDimmer", 1),
    "WallDimmer":    ("Wall Dimmer",           False,  "shellyDimmer", 1),
    "ProDimmer1PM":  ("Pro Dimmer 1PM",        True,  "shellyDimmer", 1),
    "ProDimmer2PM":  ("Pro Dimmer 2PM",        True,  "shellyDimmer", 2),
    # Sensors (battery / push model) --------------------------------------
    "PlusHT":        ("Plus H&T",             False,  "shellyHT",     1),
    "HTNG":          ("Plus H&T Gen 3",       False,  "shellyHT",     1),
    "PlusSmoke":     ("Plus Smoke",           False,  "shellySmoke",  1),
    "PlusFlood":     ("Plus Flood",           False,  "shellyFlood",  1),
    # Input ----------------------------------------------------------------
    "PlusI4":        ("Plus i4",              False,  "shellyI4",     1),
    "PlusI4DC":      ("Plus i4 DC",           False,  "shellyI4",     1),
    # Energy meter ---------------------------------------------------------
    "ProEM":         ("Pro EM",               False,  "shellyEM",     2),   # 2x EM1 clamps (v3.12)
    "Pro3EM":        ("Pro 3EM",              False,  "shellyEM",     3),
    "Pro3EM400":     ("Pro 3EM-400",          False,  "shellyEM",     3),
    "3EMG3":         ("3EM Gen 3",            False,  "shellyEM",     3),
    # RGBW -----------------------------------------------------------------
    "PlusRGBWPM":    ("Plus RGBW PM",          True,  "shellyRGBW",   1),
}

# Device types that run on battery and cannot be polled on demand
PUSH_ONLY_TYPES = {"shellyHT", "shellySmoke", "shellyFlood"}

# Bluetooth devices — no IP of their own; reach Indigo via gateway POST webhooks
BLU_TYPES       = {"shellyBluButton", "shellyBluRC4"}

# Device types that use Light.Set / Light.GetStatus instead of Switch.*
LIGHT_TYPES     = {"shellyDimmer", "shellyRGBW"}

# Device types that have physical button inputs
INPUT_TYPES     = {"shellyRelay", "shellyUni", "shellyI4"}


def detect_shelly_devices(device_info, config_keys):
    """Classify a Shelly Gen2+ device into the Indigo device(s) it maps to —
    one per channel. Pure function: the testable core a future "Discover &
    Create Shelly Devices" menu will call after probing each responder.

    Inputs:
      device_info  — dict from Shelly.GetDeviceInfo (we use ``app``; ``gen``,
                     ``model`` etc. are available but not required).
      config_keys  — the component-key list from Shelly.GetConfig /
                     Shelly.GetComponents, e.g. ['switch:0', 'input:0', 'sys'].

    Returns a list of dicts (one per channel), each:
      {device_type_id, channel, has_pm, app, source}
    where source is 'app' (matched the curated APP_INFO table) or 'components'
    (fallback classification for an app not yet in the table). Empty list = not
    a recognisable controllable Shelly (discovery would skip it / ask the user).

    Primary path is APP_INFO[app] — authoritative, and carries num_channels +
    has_pm. The component fallback means a brand-new Shelly model still maps
    sensibly instead of failing (e.g. the Gen-4 'Mini1G4', not yet in the
    table, classifies as a single relay from its 'switch:0').

    NB: this is IP/RPC discovery, so it never yields a BLU (Bluetooth) device —
    those have no IP of their own and are reached via a gateway, so they stay
    manual. Gen-1 devices have no RPC at all and are out of scope (the separate
    ShellyGen1 plugin owns them).
    """
    info = device_info or {}
    app  = info.get("app", "") or ""
    keys = list(config_keys or [])

    # Primary: the curated app -> (label, has_pm, type, channels) table.
    if app in APP_INFO:
        _label, has_pm, type_id, n = APP_INFO[app]
        n = max(1, int(n))
        return [{"device_type_id": type_id, "channel": i, "has_pm": bool(has_pm),
                 "app": app, "source": "app"} for i in range(n)]

    # Fallback: classify from the component keys (unknown / new app).
    def _ids(prefix):
        out = []
        for k in keys:
            if k.startswith(prefix + ":"):
                try:
                    out.append(int(k.split(":", 1)[1]))
                except (ValueError, IndexError):
                    pass
        return sorted(out)

    covers   = _ids("cover")
    rgbs     = _ids("rgb") + _ids("rgbw")
    lights   = _ids("light")
    ems      = _ids("em") + _ids("em1")
    switches = _ids("switch")
    inputs   = _ids("input")
    has_pm   = bool(_ids("pm1")) or bool(ems)

    def _mk(type_id, channels, pm):
        return [{"device_type_id": type_id, "channel": c, "has_pm": pm,
                 "app": app, "source": "components"} for c in channels]

    # Priority mirrors the natural Shelly hierarchy (a cover/light/rgb device
    # is never "just a switch" even though it has an underlying relay).
    if covers:
        return _mk("shellyCover", covers, has_pm)
    if rgbs:
        return _mk("shellyRGBW", [0], has_pm)
    if lights:
        return _mk("shellyDimmer", lights, has_pm)
    if ems:
        return _mk("shellyEM", ems, True)
    if switches:
        return _mk("shellyRelay", switches, has_pm)
    if inputs:
        return _mk("shellyI4", [0], False)
    return []

# Shelly RPC payload keys handled directly by the per-type _poll_* methods.
# Anything NOT in this set is captured as a dynamic state by
# _capture_unhandled_fields().  This is a UNION across all device types;
# each individual poll passes its own subset so its native states aren't
# duplicated as dynamics.
_RPC_HANDLED_KEYS = {
    # Switch / Light common
    "id", "output", "apower", "voltage", "current", "temperature", "aenergy",
    "ret_aenergy", "errors",
    # Light specific
    "brightness", "rgb", "white", "mode", "transition", "effect",
    # Cover specific
    "state", "current_pos", "target_pos", "slat", "pos_control",
    "last_direction", "move_started_at", "move_timeout",
    # EM specific
    "act_power", "aprt_power", "pf", "freq",
    "a_voltage", "a_current", "a_act_power", "a_aprt_power", "a_pf", "a_freq",
    "b_voltage", "b_current", "b_act_power", "b_aprt_power", "b_pf", "b_freq",
    "c_voltage", "c_current", "c_act_power", "c_aprt_power", "c_pf", "c_freq",
    "n_current", "total_current", "total_act_power", "total_aprt_power",
    "user_calibrated_phase",
}

# Indigo-reserved native device-property names.  Never use these as custom
# state IDs — Indigo silently routes writes to the native slot.  See the
# Z2M v1.7 + Ecowitt v2.1 work and feedback_indigo_state_visibility.md.
_RESERVED_STATE_NAMES = {
    "batteryLevel", "brightnessLevel", "onOffState", "sensorValue",
    "whiteTemperature", "redLevel", "greenLevel", "blueLevel", "whiteLevel",
    "coolerIsOn", "heaterIsOn", "hvacOperationMode", "temperatureInput1",
    "setpointHeat", "setpointCool", "colorMode",
}

# RGBW built-in effects
RGBW_EFFECTS = {
    "0": "Static (no effect)",
    "1": "Meteor shower",
    "2": "Gradual change",
    "3": "Flash / blink",
    "4": "Gradual on/off",
    "5": "Random flicker",
}


class Plugin(indigo.PluginBase):

    # ---------------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------------

    def __init__(self, plugin_id, display_name, version, prefs):
        super().__init__(plugin_id, display_name, version, prefs)

        self.timestamp_enabled = bool(prefs.get("timestampEnabled", True))
        if install_timestamp_filter:
            self._ts_filter = install_timestamp_filter(self, enabled=self.timestamp_enabled)
        else:
            self._ts_filter = None

        self.timeout         = self._pref_int(prefs, "timeout_secs",   3)
        self.server_ip       = _SECRETS_INDIGO_IP or prefs.get("indigo_server_ip", "")
        if not self.server_ip:
            log(
                "No Indigo server IP configured. Set INDIGO_SERVER_IP in IndigoSecrets.py "
                "OR fill Indigo Server IP in Plugins -> ShellyDirect -> Configure.", level="ERROR"
            )
        # discovery_subnets / shelly auth: IndigoSecrets first, PluginConfig fallback.
        # No hardcoded default subnet — it depended on the developer's LAN.
        self.subnets_raw     = (_SECRETS_SHELLY_SUBNETS or prefs.get("discovery_subnets", "")).strip()
        self.subnets         = [s.strip() for s in self.subnets_raw.split(",") if s.strip()]
        if not self.subnets:
            log(
                "No discovery subnets configured. Set SHELLY_DISCOVERY_SUBNETS in "
                "IndigoSecrets.py OR fill Discovery Subnets in Plugins -> ShellyDirect "
                "-> Configure (e.g. '192.168.1' for a 192.168.1.0/24 LAN).",
                level="ERROR",
            )
        self.stale_minutes   = self._pref_int(prefs, "stale_minutes",  10)
        # v3.15: webhook listener port is configurable — a port collision used
        # to leave the plugin permanently webhook-dead with no user remedy.
        self.webhook_port    = self._pref_int(prefs, "webhook_port", WEBHOOK_PORT)
        self.shelly_user     = (_SECRETS_SHELLY_USER or prefs.get("shelly_username", "")).strip()
        self.shelly_pass     = (_SECRETS_SHELLY_PASS or prefs.get("shelly_password", "")).strip()
        self.firmware_notify = prefs.get("firmware_notify_enabled", False)

        self.last_polled          = {}   # {dev_id: float}
        self.last_seen            = {}   # {dev_id: float}
        self.fail_count           = {}   # {dev_id: int}  consecutive poll failures
        self._webhook_repairs     = {}   # {shelly_ip: ts} stale-devId repair rate limit (v3.13)
        # Serialises pluginProps read-modify-write cycles between the MAC
        # backfill thread and the poll thread's dynamic-state capture —
        # deliberately held across replacePluginPropsOnServer: an
        # interleaved RMW silently drops one side's changes (v3.14).
        self._props_lock          = threading.RLock()
        self.webhook_server       = None
        self.energy_data          = {}   # {str(dev_id): {...baselines + history...}}
        self._energy_lock         = threading.RLock()  # guards energy_data RMW across threads
        # last_date persisted across restarts so a restart spanning midnight still
        # triggers the daily reset on the first tick (network available), instead of
        # silently skipping it because __init__ seeded today.
        # v3.14: the energy JSON's __meta__.last_date is authoritative — it is
        # written atomically with the baselines it describes, and survives a
        # CRASH (pluginPrefs only flush to disk on a graceful shutdown).
        self.last_date            = prefs.get("lastEnergyDate") or str(date.today())
        self.power_alert_active   = {}   # {dev_id: bool}
        self.triggers             = []   # active Indigo trigger objects
        self.var_folder_id        = None # lazy-created ShellyDirect variable folder
        self.last_webhook_check   = 0.0  # timestamp of last webhook health check
        self.last_firmware_check  = 0.0  # timestamp of last firmware notify check
        self.webhook_repair_fails = {}   # {dev_id: int}  consecutive repairs that didn't stick
        self._dup_warned          = set()# MAC/IP+channel keys already warned about as duplicates

        log_level = self._pref_int(prefs, "logLevel", logging.INFO)
        self.indigo_log_handler.setLevel(log_level)
        self._load_energy_data()

        # Startup banner moved to showPluginInfo on demand (revised 25-May-2026 per Jay).

    def startup(self):
        self._start_webhook_server()

    def shutdown(self):
        log("Shelly Direct plugin stopping")
        self._save_energy_data()
        if self.webhook_server:
            self.webhook_server.shutdown()
            self.webhook_server.server_close()   # release the listening socket FD

    # ---------------------------------------------------------------------------
    # Device lifecycle
    # ---------------------------------------------------------------------------

    def deviceStartComm(self, dev):
        self.logger.debug(f"deviceStartComm: {dev.name} ({dev.deviceTypeId})")
        # Refresh state list so any new states added in Devices.xml are available
        dev.stateListOrDisplayStateIdChanged()
        self.last_polled[dev.id] = 0
        self.last_seen[dev.id]   = time.time()
        dev.updateStateOnServer("deviceOnline", True)
        # v3.14: the initial poll + webhook configure moved OFF the lifecycle
        # thread — with several offline devices, plugin startup used to stall
        # for (devices x timeout) seconds doing serial blocking network I/O.
        def _start_net():
            try:
                # BLU devices are pure-event Bluetooth peripherals — no direct poll
                if dev.deviceTypeId not in BLU_TYPES:
                    self._poll_device(dev)
                self._configure_webhooks(dev)
            except Exception as exc:
                self.logger.debug(f"[{dev.name}] startComm network init: {exc}")
        threading.Thread(target=_start_net, daemon=True).start()
        # Backfill MAC address for existing devices that pre-date MAC storage.
        # Guard: only run if mac_address not yet stored, avoiding recursive trigger
        # from replacePluginPropsOnServer inside _backfill_mac.
        if not dev.pluginProps.get("mac_address") and dev.deviceTypeId not in BLU_TYPES:
            threading.Thread(
                target=self._backfill_mac, args=(dev,), daemon=True
            ).start()

    def deviceStopComm(self, dev):
        self.logger.debug(f"deviceStopComm: {dev.name}")
        self.last_polled.pop(dev.id, None)
        self.last_seen.pop(dev.id, None)

    # ---------------------------------------------------------------------------
    # Trigger lifecycle
    # ---------------------------------------------------------------------------

    def triggerStartProcessing(self, trigger):
        self.triggers.append(trigger)

    def triggerStopProcessing(self, trigger):
        self.triggers = [t for t in self.triggers if t.id != trigger.id]

    # ---------------------------------------------------------------------------
    # Preferences
    # ---------------------------------------------------------------------------

    def validatePrefsConfigUi(self, values_dict):
        errors = indigo.Dict()
        raw = values_dict.get("discovery_subnets", "").strip()
        if not raw:
            # v3.13: a blank field is fine when IndigoSecrets provides the
            # subnets — the dialog help text promises 'set one or the other'.
            if not _SECRETS_SHELLY_SUBNETS:
                errors["discovery_subnets"] = ("At least one subnet is required "
                                               "(e.g. 192.168.1), or set "
                                               "SHELLY_DISCOVERY_SUBNETS in IndigoSecrets.py")
        else:
            for s in raw.split(","):
                s = s.strip()
                parts = s.split(".")
                if len(parts) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    errors["discovery_subnets"] = (
                        f"Invalid subnet '{s}'. Use three octets only, e.g. 192.168.1"
                    )
                    break
        return (len(errors) == 0), values_dict, errors

    def closedPrefsConfigUi(self, values_dict, user_cancelled):
        if not user_cancelled:
            # v3.13: mirror __init__'s IndigoSecrets-first resolution exactly —
            # a dialog save used to DROP the secrets precedence for subnets and
            # the Shelly credentials until the next restart.
            self.timeout         = self._pref_int(values_dict, "timeout_secs", 3)
            self.server_ip       = _SECRETS_INDIGO_IP or values_dict.get("indigo_server_ip", "")
            self.subnets_raw     = (_SECRETS_SHELLY_SUBNETS
                                    or values_dict.get("discovery_subnets", "")).strip()
            self.subnets         = [s.strip() for s in self.subnets_raw.split(",") if s.strip()]
            self.stale_minutes   = self._pref_int(values_dict, "stale_minutes", 10)
            self.shelly_user     = (_SECRETS_SHELLY_USER
                                    or values_dict.get("shelly_username", "")).strip()
            self.shelly_pass     = (_SECRETS_SHELLY_PASS
                                    or values_dict.get("shelly_password", "")).strip()
            self.firmware_notify = values_dict.get("firmware_notify_enabled", False)
            self.indigo_log_handler.setLevel(self._pref_int(values_dict, "logLevel", logging.INFO))

    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):
        errors = indigo.Dict()
        ip = values_dict.get("ip_address", "").strip()
        if not ip:
            label = "Gateway IP address is required." if type_id in BLU_TYPES else "IP address is required."
            errors["ip_address"] = label
        else:
            parts = ip.split(".")
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                errors["ip_address"] = "Please enter a valid IPv4 address (e.g. 192.168.1.10)."
        if type_id in BLU_TYPES:
            bthome_id = values_dict.get("bthome_id", "").strip()
            if not bthome_id:
                errors["bthome_id"] = "BTHome Device ID is required (integer, e.g. 200)."
            else:
                try:
                    int(bthome_id)
                except ValueError:
                    errors["bthome_id"] = "BTHome Device ID must be an integer (e.g. 200, 201, 202)."
        if type_id == "shellyRelay" and values_dict.get("power_alert_enabled", False):
            try:
                float(values_dict.get("power_alert_watts", ""))
            except (ValueError, TypeError):
                errors["power_alert_watts"] = "Enter a valid wattage threshold (e.g. 2000)"
        return (len(errors) == 0), values_dict, errors

    def closedDeviceConfigUi(self, values_dict, user_cancelled, type_id, dev_id):
        if user_cancelled:
            return
        try:
            dev = indigo.devices[dev_id]
        except KeyError:
            return
        new_ip = values_dict.get("ip_address", "").strip()
        old_ip = dev.pluginProps.get("ip_address", "").strip()
        if new_ip and new_ip != old_ip:
            log(f"[{dev.name}] IP changed {old_ip} -> {new_ip}; reconfiguring webhooks")
            threading.Thread(
                target=self._configure_webhooks, args=(dev,), daemon=True
            ).start()

    # ---------------------------------------------------------------------------
    # Standard device actions  (relay, uni, cover on/off, dimmer on/off)
    # ---------------------------------------------------------------------------

    def actionControlSensor(self, action, dev):
        # Seven device types are declared type="sensor" (shellyHT/I4/Smoke/Flood/EM/BluButton/BluRC4).
        # Without this method Indigo logs "plugin does not define method actionControlSensor" and drops
        # the action. RequestStatus re-polls via _poll_device (a no-op for the push-only types).
        try:
            if action.sensorAction == indigo.kSensorAction.RequestStatus:
                self._poll_device(dev)
            else:
                self.logger.warning(f"{dev.name}: unsupported sensor action {action.sensorAction}")
        except Exception as e:
            self.logger.error(f"{dev.name}: actionControlSensor failed — {e}")

    def actionControlDevice(self, action, dev):
        try:
            if not dev.enabled:
                return

            type_id = dev.deviceTypeId

            if type_id == "shellyCover":
                self._cover_standard_action(action, dev)
                return

            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                log(f'[{dev.name}] No IP address configured', level="ERROR")
                return

            if action.deviceAction == indigo.kDeviceAction.TurnOn:
                if self._set_output(dev, ip, True):
                    log(f'sent "{dev.name}" on')
                    dev.updateStateOnServer("onOffState", True)
                else:
                    log(f'failed to send on to "{dev.name}"', level="ERROR")

            elif action.deviceAction == indigo.kDeviceAction.TurnOff:
                if dev.pluginProps.get("lock_off", False):
                    log(f'[{dev.name}] Turn Off blocked - device is locked', level="WARNING")
                    return
                if self._set_output(dev, ip, False):
                    log(f'sent "{dev.name}" off')
                    dev.updateStateOnServer("onOffState", False)
                else:
                    log(f'failed to send off to "{dev.name}"', level="ERROR")

            elif action.deviceAction == indigo.kDeviceAction.Toggle:
                new_state = not dev.onState
                if new_state is False and dev.pluginProps.get("lock_off", False):
                    log(f'[{dev.name}] Toggle to Off blocked - device is locked', level="WARNING")
                    return
                if self._set_output(dev, ip, new_state):
                    label = "on" if new_state else "off"
                    log(f'sent "{dev.name}" toggle -> {label}')
                    dev.updateStateOnServer("onOffState", new_state)
                else:
                    log(f'failed to toggle "{dev.name}"', level="ERROR")

            elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
                self._poll_device(dev)

        except Exception as exc:
            log(f'actionControlDevice exception for "{dev.name}": {exc}', level="ERROR")

    def actionControlDimmer(self, action, dev):
        """Handle brightness actions for shellyDimmer and shellyRGBW devices."""
        try:
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                log(f'[{dev.name}] No IP address configured', level="ERROR")
                return

            channel_id = self._pref_int(dev.pluginProps, "channel_id", 0)
            # v3.12: RGBW devices in rgb/rgbw profile don't answer Light.Set
            component = ("Light" if dev.deviceTypeId != "shellyRGBW"
                         else self._rgbw_set_component(dev, ip))

            if action.deviceAction == indigo.kDimmerAction.TurnOn:
                if self._light_set(ip, channel_id, on=True, component=component):
                    dev.updateStateOnServer("onOffState", True)
                    log(f'sent "{dev.name}" on')

            elif action.deviceAction == indigo.kDimmerAction.TurnOff:
                if self._light_set(ip, channel_id, on=False, component=component):
                    dev.updateStateOnServer("onOffState", False)
                    log(f'sent "{dev.name}" off')

            elif action.deviceAction == indigo.kDimmerAction.Toggle:
                new_state = not dev.onState
                if self._light_set(ip, channel_id, on=new_state, component=component):
                    dev.updateStateOnServer("onOffState", new_state)
                    log(f'sent "{dev.name}" toggle -> {"on" if new_state else "off"}')

            elif action.deviceAction == indigo.kDimmerAction.SetBrightness:
                brightness = max(0, min(100, int(action.actionValue)))
                if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness, component=component):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", brightness > 0)
                    log(f'sent "{dev.name}" brightness -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.BrightenBy:
                current    = dev.states.get("brightnessLevel", 0)
                brightness = min(100, current + int(action.actionValue))
                if self._light_set(ip, channel_id, on=True, brightness=brightness, component=component):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", True)
                    log(f'sent "{dev.name}" brighten -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.DimBy:
                current    = dev.states.get("brightnessLevel", 100)
                brightness = max(0, current - int(action.actionValue))
                if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness, component=component):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", brightness > 0)
                    log(f'sent "{dev.name}" dim -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.RequestStatus:
                self._poll_device(dev)

        except Exception as exc:
            log(f'actionControlDimmer exception for "{dev.name}": {exc}', level="ERROR")

    # ---------------------------------------------------------------------------
    # Custom actions
    # ---------------------------------------------------------------------------

    def actionOnForSeconds(self, action):
        """Turn relay on for N seconds using Shelly's native toggle_after."""
        try:
            dev     = indigo.devices[action.deviceId]
            seconds = int(action.props.get("seconds", 1))
            ip      = dev.pluginProps.get("ip_address", "").strip()
            chan    = self._pref_int(dev.pluginProps, "channel_id", 0)
            if not ip:
                log(f'[{dev.name}] No IP for on_for_seconds', level="ERROR")
                return
            resp = self._rget(
                f"http://{ip}/rpc/Switch.Set?id={chan}&on=true&toggle_after={seconds}"
            )
            resp.raise_for_status()
            log(f'[{dev.name}] on for {seconds}s')
            dev.updateStateOnServer("onOffState", True)
        except Exception as exc:
            log(f'[{action.deviceId}] on_for_seconds failed: {exc}', level="ERROR")

    def actionCoverOpen(self, action):
        self._cover_cmd(action.deviceId, "Cover.Open")

    def actionCoverClose(self, action):
        self._cover_cmd(action.deviceId, "Cover.Close")

    def actionCoverStop(self, action):
        self._cover_cmd(action.deviceId, "Cover.Stop")

    def actionCoverGoToPosition(self, action):
        try:
            pos = max(0, min(100, int(action.props.get("position", 50))))
            dev = indigo.devices[action.deviceId]
            ip  = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            resp = self._rget(f"http://{ip}/rpc/Cover.GoToPosition", params={"id": chan, "pos": pos})
            resp.raise_for_status()
            dev.updateStateOnServer("targetPosition", pos)
            log(f'[{dev.name}] going to position {pos}%')
        except Exception as exc:
            log(f'[{action.deviceId}] GoToPosition failed: {exc}', level="ERROR")

    def actionCoverSetTilt(self, action):
        """Set venetian blind tilt angle (0=closed slats, 100=open slats)."""
        try:
            tilt = max(0, min(100, int(action.props.get("tilt", 50))))
            dev  = indigo.devices[action.deviceId]
            ip   = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            resp = self._rget(
                f"http://{ip}/rpc/Cover.GoToPosition",
                params={"id": chan, "slat_pos": tilt}
            )
            resp.raise_for_status()
            dev.updateStateOnServer("tiltTargetPosition", tilt)
            log(f'[{dev.name}] tilt set to {tilt}%')
        except Exception as exc:
            log(f'[{action.deviceId}] SetTilt failed: {exc}', level="ERROR")

    def actionSetBrightness(self, action):
        try:
            dev        = indigo.devices[action.deviceId]
            brightness = max(0, min(100, int(action.props.get("brightness", 100))))
            ip         = dev.pluginProps.get("ip_address", "").strip()
            channel_id = self._pref_int(dev.pluginProps, "channel_id", 0)
            if not ip:
                return
            component = ("Light" if dev.deviceTypeId != "shellyRGBW"
                         else self._rgbw_set_component(dev, ip))
            if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness, component=component):
                dev.updateStateOnServer("brightnessLevel", brightness)
                dev.updateStateOnServer("onOffState", brightness > 0)
                log(f'[{dev.name}] brightness set to {brightness}%')
        except Exception as exc:
            log(f'[{action.deviceId}] SetBrightness failed: {exc}', level="ERROR")

    def actionSetColor(self, action):
        try:
            dev = indigo.devices[action.deviceId]
            ip  = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            r  = max(0, min(255, int(action.props.get("red",        255))))
            g  = max(0, min(255, int(action.props.get("green",      255))))
            b  = max(0, min(255, int(action.props.get("blue",       255))))
            w  = max(0, min(255, int(action.props.get("white",        0))))
            br = max(0, min(100, int(action.props.get("brightness", 100))))
            # v3.12: Gen2+ colour goes through the RGB/RGBW component — the
            # old Light.Set red=/green=/blue= params don't exist on Gen2+.
            prof = self._rgbw_component(dev, ip)
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            if prof == "rgbw":
                params = {"id": chan, "on": "true",
                          "rgb": json.dumps([r, g, b]), "white": w,
                          "brightness": br}
                resp = self._rget(f"http://{ip}/rpc/RGBW.Set", params=params)
            elif prof == "rgb":
                params = {"id": chan, "on": "true",
                          "rgb": json.dumps([r, g, b]), "brightness": br}
                resp = self._rget(f"http://{ip}/rpc/RGB.Set", params=params)
            else:
                log(f'[{dev.name}] Set Color skipped — device is in "light" '
                    f'profile (independent white channels, no colour component)',
                    level="WARNING")
                return
            resp.raise_for_status()
            dev.updateStateOnServer("onOffState",     True)
            dev.updateStateOnServer("brightnessLevel", br)
            dev.updateStateOnServer("redLevel",        r)
            dev.updateStateOnServer("greenLevel",      g)
            dev.updateStateOnServer("blueLevel",       b)
            dev.updateStateOnServer("whiteLevel",      w)
            dev.updateStateOnServer("colorMode",       "color")
            log(f'[{dev.name}] color set R={r} G={g} B={b} W={w} @{br}%')
        except Exception as exc:
            log(f'[{action.deviceId}] SetColor failed: {exc}', level="ERROR")

    def actionSetEffect(self, action):
        """Trigger a built-in light effect on a Shelly RGBW device.

        v3.12: the Gen1-era Light.Set effect= param does not exist on Gen2+
        RPC — the old call silently did nothing. Honest WARNING until a
        Gen2+ effects surface exists to wire up (kept so existing Indigo
        actions don't break with a missing-callback error)."""
        try:
            dev = indigo.devices[action.deviceId]
            log(f'[{dev.name}] Set Effect is not supported on Gen2+ Shelly '
                f'firmware (the Gen1 effect parameter has no RPC equivalent) '
                f'— action skipped', level="WARNING")
        except Exception as exc:
            log(f'[{action.deviceId}] SetEffect failed: {exc}', level="ERROR")

    # ---------------------------------------------------------------------------
    # Polling thread
    # ---------------------------------------------------------------------------

    def runConcurrentThread(self):
        try:
            while True:
              # v3.14: the WHOLE tick body is guarded — a non-StopThread
              # exception outside the per-device loop (e.g. devices.iter
              # hiccup) used to kill polling silently for the rest of the run.
              try:
                today_str = str(date.today())
                if today_str != self.last_date:
                    try:
                        self._midnight_reset(today_str)
                    except Exception as exc:
                        log(f"Midnight reset error: {exc}", level="ERROR")
                    self.last_date = today_str
                    self.pluginPrefs["lastEnergyDate"] = today_str   # survive a restart
                    with self._energy_lock:                          # survive a CRASH (v3.14)
                        self.energy_data.setdefault("__meta__", {})["last_date"] = today_str

                now = time.time()

                # Webhook health check every 6 hours (v3.14: the pre-loop tick
                # body is guarded further below via the per-device try; the
                # scheduling block itself is simple arithmetic)
                if (now - self.last_webhook_check) >= 21600:
                    self.last_webhook_check = now
                    threading.Thread(
                        target=self._check_webhook_health, daemon=True
                    ).start()

                # Firmware notification once per day (if enabled)
                if self.firmware_notify and (now - self.last_firmware_check) >= 86400:
                    self.last_firmware_check = now
                    threading.Thread(
                        target=self._firmware_daily_check, daemon=True
                    ).start()

                for dev in indigo.devices.iter("self"):
                    # Whole per-device body guarded: one bad device (config fault,
                    # transient API error in _check_online, etc.) must never escape
                    # to the while-body and kill the entire polling thread.
                    try:
                        if not dev.enabled or not dev.configured:
                            continue
                        # BLU devices are event-driven via gateway webhooks — no polling or
                        # stale-check possible (they sleep between button presses)
                        if dev.deviceTypeId in BLU_TYPES:
                            continue
                        if dev.deviceTypeId in PUSH_ONLY_TYPES:
                            self._check_online(dev, now)
                            continue

                        self._check_online(dev, now)

                        interval = self._pref_int(dev.pluginProps, "poll_interval", 30)
                        if self.fail_count.get(dev.id, 0) >= 3:
                            interval = max(interval, 300)   # offline back-off (v3.13)
                        if (now - self.last_polled.get(dev.id, 0)) >= interval:
                            self._poll_device(dev)
                    except Exception as exc:
                        log(f'poll loop error "{getattr(dev, "name", "?")}": {exc}', level="WARNING")
              except self.StopThread:
                raise
              except Exception as exc:
                log(f"poll tick error: {exc}", level="WARNING")

              self.sleep(10)
        except self.StopThread:
            pass

    # ---------------------------------------------------------------------------
    # Menu actions
    # ---------------------------------------------------------------------------

    def menuDiscoverDevices(self, values_dict=None, type_id=""):
        for subnet in self.subnets:
            log(f"Discovery started - scanning {subnet}.1 to {subnet}.254 ...")
            threading.Thread(
                target=self._discover_thread, args=(subnet,), daemon=True
            ).start()
        return True

    def menuCheckFirmware(self, values_dict=None, type_id=""):
        # v3.15: serial network I/O off the menu callback thread
        threading.Thread(target=self._menu_check_firmware_body, daemon=True).start()
        return True

    def _menu_check_firmware_body(self, values_dict=None, type_id=""):
        log("Checking firmware versions ...")
        for dev in indigo.devices.iter("self"):
            if not dev.enabled:
                continue
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                continue
            try:
                resp = self._rget(f"http://{ip}/rpc/Shelly.CheckForUpdate")
                resp.raise_for_status()
                stable = resp.json().get("stable", {})
                msg    = f"update available: {stable.get('version','?')}" if stable else "up to date"
                log(f'[{dev.name}] ({ip}) firmware {msg}')
            except Exception as exc:
                log(f'[{dev.name}] ({ip}) firmware check failed: {exc}', level="WARNING")
        return True

    def menuResetWebhooks(self, values_dict=None, type_id=""):
        # v3.15: serial network I/O off the menu callback thread
        threading.Thread(target=self._menu_reset_webhooks_body, daemon=True).start()
        return True

    def _menu_reset_webhooks_body(self):
        log("Reconfiguring webhooks on all devices ...")
        # v3.14: _configure_webhooks returns True when it actually ran —
        # the old `is not None` test counted a bare None return as 0 devices.
        count = sum(1 for dev in indigo.devices.iter("self")
                    if dev.enabled and dev.configured
                    and self._configure_webhooks(dev))
        log(f"Webhook reconfiguration complete ({count} device(s))")
        return True

    def menuDeviceHealthSummary(self, values_dict=None, type_id=""):
        # v3.15: serial network I/O off the menu callback thread
        threading.Thread(target=self._menu_health_summary_body, daemon=True).start()
        return True

    def _menu_health_summary_body(self, values_dict=None, type_id=""):
        """Log a formatted table showing status of every managed device."""
        log("-" * 100)
        log(
            f"{'Device':<30} {'IP':<18} {'Type':<18} {'Online':<8} {'Firmware':<12} {'Last Seen'}"
        )
        log("-" * 100)
        now    = time.time()
        seen_n = 0
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            if not dev.enabled:
                continue
            ip      = dev.pluginProps.get("ip_address", "").strip()
            online  = dev.states.get("deviceOnline", True)
            last    = self.last_seen.get(dev.id, 0)
            elapsed = int(now - last) if last else -1
            if elapsed < 0:
                age = "never"
            elif elapsed < 60:
                age = f"{elapsed}s ago"
            elif elapsed < 3600:
                age = f"{elapsed // 60}m ago"
            else:
                age = f"{elapsed // 3600}h ago"

            fw = "?"
            if ip:
                try:
                    r = self._rget(f"http://{ip}/rpc/Shelly.GetDeviceInfo", timeout=2)
                    if r.status_code == 200:
                        fw = r.json().get("ver", "?")
                except Exception:
                    fw = "unreachable"

            status = "Yes" if online else "OFFLINE"
            log(
                f"{dev.name:<30} {ip:<18} {dev.deviceTypeId:<18} {status:<8} {fw:<12} {age}"
            )
            seen_n += 1

        log("-" * 100)
        log(f"Total: {seen_n} device(s)")
        return True

    def menuExportEnergyHistory(self, values_dict=None, type_id=""):
        """Write 30-day rolling energy history to CSV in ~/Documents/Indigo/ShellyDirect/"""
        try:
            out_dir = os.path.expanduser("~/Documents/Indigo/ShellyDirect")
            os.makedirs(out_dir, exist_ok=True)
            filename  = f"energy_history_{date.today()}.csv"
            filepath  = os.path.join(out_dir, filename)
            row_count = 0

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Device", "kWh"])

                with self._energy_lock:
                    energy_snapshot = {k: dict(v) for k, v in self.energy_data.items()}
                energy_snapshot.pop("__meta__", None)
                for dev_id_str, entry in energy_snapshot.items():
                    try:
                        dev  = indigo.devices[int(dev_id_str)]
                        name = dev.name
                    except KeyError:
                        name = f"Device {dev_id_str}"

                    for record in entry.get("history", []):
                        writer.writerow([
                            record.get("date", ""),
                            name,
                            round(record.get("kwh", 0.0), 4),
                        ])
                        row_count += 1

            log(f"Energy history exported: {filepath} ({row_count} rows)")
        except Exception as exc:
            log(f"Energy history export failed: {exc}", level="ERROR")
        return True

    # ---------------------------------------------------------------------------
    # Webhook HTTP server
    # URL: http://<indigo_ip>:8178/shellyEvent?devId=<id>&type=<t>&...
    # ---------------------------------------------------------------------------

    @staticmethod
    def _qp(params, key, default=""):
        """First value of a parse_qs query param."""
        return params.get(key, [default])[0]

    @staticmethod
    def _qp_int(params, key, default=0):
        """Guarded int from a query param."""
        try:
            return int(Plugin._qp(params, key, str(default)))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _qp_float(params, key):
        """Guarded float from a query param (v3.13): blank values and
        unsubstituted '{tC}' / '${ev.x}' placeholder tokens return None so ONE
        bad field skips that field, not the whole request (an unguarded
        float() used to 500 the request and discard its other values)."""
        raw = Plugin._qp(params, key)
        if not raw or raw[0] in "{$":
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def _apply_webhook_event(self, target, params):
        """Apply a parsed /shellyEvent query to the target device's states.

        Extracted from the HTTP handler closure (v3.13) so the push path — the
        subject of three of the last four release fixes — is unit-testable.
        """
        ev_type  = self._qp(params, "type", "switch").lower()
        state    = self._qp(params, "state").lower()
        input_id = self._qp_int(params, "input", 0)
        dev_id   = target.id

        if ev_type == "switch" and state in ("on", "off"):
            target.updateStateOnServer("onOffState", state == "on")
            # v3.14: only NON-PM relays may defer their poll — a PM device's
            # poll also carries power/energy, and frequent toggling used to
            # defer it indefinitely.
            if not target.pluginProps.get("has_pm", True):
                self.last_polled[dev_id] = time.time()
            self.logger.debug(f'[webhook] "{target.name}" switch -> {state}')

        elif ev_type == "button":
            press = self._qp(params, "event", "single")
            inp   = self._qp_int(params, "input_id", 0)
            self.logger.info(f'[webhook] "{target.name}" input{inp} {press}_press')
            self._fire_trigger("inputButtonPress", dev_id, {
                "input_id":   str(inp),
                "press_type": press,
            })

        elif ev_type == "input" and state in ("on", "off"):
            # v3.13: the Uni declares input0/input1 custom states — its
            # sensorValue write was dead (relay-class device). Keep the
            # sensorValue special-case only for the i4 (deferred Supports* work).
            if target.deviceTypeId == "shellyUni":
                key = f"input{input_id}"
            else:
                key = "sensorValue" if input_id == 0 else f"input{input_id}"
            target.updateStateOnServer(key, state == "on")
            self.logger.info(f'[webhook] "{target.name}" input{input_id} -> {state}')

        elif ev_type == "cover_change":
            self.last_polled[dev_id] = 0   # trigger immediate poll
            self.logger.debug(f'[webhook] "{target.name}" cover change - poll queued')

        elif ev_type == "light" and state in ("on", "off"):
            target.updateStateOnServer("onOffState", state == "on")
            # v3.14: force a prompt poll — brightness isn't in the webhook, and
            # stamping last_polled here left it stale for a full interval.
            self.last_polled[dev_id] = 0
            self.logger.debug(f'[webhook] "{target.name}" light -> {state} - poll queued')

        elif ev_type == "ht":
            temp = self._qp_float(params, "tC")
            hum  = self._qp_float(params, "humidity")
            bat  = self._qp_float(params, "battery")
            kv, mirror = [], {}
            if temp is not None:
                kv.append({"key": "sensorValue", "value": temp,
                           "uiValue": f"{temp:.1f} C"})
                # v3.14: also the declared temperature state — sensorValue is
                # dead on sensor types until the Supports* completion lands.
                kv.append({"key": "temperature", "value": temp,
                           "uiValue": f"{temp:.1f} C"})
                mirror["temp_c"] = f"{temp:.1f}"
            if hum is not None:
                kv.append({"key": "humidity", "value": hum,
                           "uiValue": f"{hum:.1f} %"})
                mirror["humidity"] = f"{hum:.1f}"
            if bat is not None:
                kv.append({"key": "batteryPct", "value": int(bat),
                           "uiValue": f"{int(bat)}%"})
                mirror["battery"] = str(int(bat))
            if kv:
                target.updateStatesOnServer(kv)
                self._mirror_states(target, mirror)
            self.logger.info(
                f'[webhook] "{target.name}" HT: temp={temp}C  hum={hum}%  bat={bat}%')

        elif ev_type == "smoke":
            alarm = self._qp(params, "alarm", "false").lower() == "true"
            bat   = self._qp_float(params, "battery")
            kv    = [{"key": "sensorValue", "value": alarm}]
            if bat is not None:
                kv.append({"key": "batteryPct", "value": int(bat)})
            target.updateStatesOnServer(kv)
            self._mirror_states(target, {"alarm": str(alarm)})
            self.logger.info(
                f'[webhook] "{target.name}" smoke: alarm={alarm}  bat={bat}%')

        elif ev_type == "flood":
            flood = self._qp(params, "flood", "false").lower() == "true"
            temp  = self._qp_float(params, "tC")
            bat   = self._qp_float(params, "battery")
            kv    = [{"key": "sensorValue", "value": flood}]
            if temp is not None:
                kv.append({"key": "temperature", "value": temp,
                           "uiValue": f"{temp:.1f} C"})
            if bat is not None:
                kv.append({"key": "batteryPct", "value": int(bat)})
            target.updateStatesOnServer(kv)
            self._mirror_states(target, {"flood": str(flood)})
            self.logger.info(
                f'[webhook] "{target.name}" flood: flood={flood}  bat={bat}%')

    def _repair_stale_webhook(self, shelly_ip, stale_dev_id):
        """Rate-limited auto-repair for a webhook carrying a stale devId
        (v3.13): a chatty device used to spawn one repair THREAD PER REQUEST.
        One repair per source IP per 60s; repairs run in a worker thread."""
        now = time.time()
        last = self._webhook_repairs.get(shelly_ip, 0)
        if (now - last) < 60:
            return
        self._webhook_repairs[shelly_ip] = now
        current_dev = None
        for dev in indigo.devices.iter(PLUGIN_ID):
            if dev.pluginProps.get("ip_address", "").strip() == shelly_ip:
                current_dev = dev
                break
        if current_dev:
            self.logger.info(
                f"[webhook] Stale devId {stale_dev_id} from {shelly_ip} — "
                f"auto-reconfiguring webhooks for \"{current_dev.name}\"")
            threading.Thread(target=self._configure_webhooks,
                             args=(current_dev,), daemon=True).start()
        else:
            self.logger.warning(
                f"[webhook] Device {stale_dev_id} not found (source IP: {shelly_ip})")

    def _start_webhook_server(self):
        plugin = self

        class WebhookHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    parsed   = urllib.parse.urlparse(self.path)
                    params   = urllib.parse.parse_qs(parsed.query)
                    dev_id   = Plugin._qp_int(params, "devId", 0)

                    if not dev_id:
                        self.send_response(400); self.end_headers(); return

                    try:
                        target = indigo.devices[dev_id]
                    except KeyError:
                        # Stale webhook — old devId from before devices were
                        # deleted/recreated. Rate-limited auto-repair (v3.13).
                        plugin._repair_stale_webhook(self.client_address[0], dev_id)
                        self.send_response(404); self.end_headers(); return

                    plugin.last_seen[dev_id] = time.time()
                    if not target.states.get("deviceOnline", True):
                        target.updateStateOnServer("deviceOnline", True)
                        plugin.logger.info(f'[{target.name}] back online (webhook)')

                    # Event application lives in Plugin._apply_webhook_event
                    # (v3.13) — extracted from this closure for testability.
                    plugin._apply_webhook_event(target, params)

                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")

                except Exception as exc:
                    plugin.logger.error(f"[webhook] Handler error: {exc}")
                    try:
                        self.send_response(500); self.end_headers()
                    except Exception:
                        pass

            def do_POST(self):
                """Handle BLU button webhook POSTs from the Shelly BLE gateway.

                URL: /shellyBluEvent?devId=<id>
                Body (JSON): {"component":"bthomedevice:202","id":202,
                              "event":"single_push","idx":1,"ts":1731931521.19}
                """
                try:
                    parsed  = urllib.parse.urlparse(self.path)
                    params  = urllib.parse.parse_qs(parsed.query)
                    dev_id  = int(params.get("devId", ["0"])[0])

                    if not dev_id:
                        self.send_response(400); self.end_headers(); return

                    try:
                        length = int(self.headers.get("Content-Length", 0))
                    except (ValueError, TypeError):
                        length = 0
                    # BLU event payloads are tiny — cap the read so a malformed or
                    # hostile Content-Length on this unauthenticated LAN listener
                    # can't make us allocate an unbounded buffer.
                    if length < 0 or length > 65536:
                        self.send_response(413); self.end_headers(); return
                    body    = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(body)
                    except (json.JSONDecodeError, ValueError):
                        payload = {}

                    try:
                        target = indigo.devices[dev_id]
                    except KeyError:
                        # Stale devId — try to find device by gateway IP and auto-repair
                        gw_ip = self.client_address[0]
                        current_dev = None
                        for dev in indigo.devices.iter(PLUGIN_ID):
                            if (dev.deviceTypeId in BLU_TYPES and
                                    dev.pluginProps.get("ip_address", "").strip() == gw_ip):
                                current_dev = dev
                                break
                        if current_dev:
                            plugin.logger.info(
                                f"[blu webhook] Stale devId {dev_id} from gateway {gw_ip} — "
                                f"auto-reconfiguring for \"{current_dev.name}\""
                            )
                            threading.Thread(
                                target=plugin._configure_webhooks,
                                args=(current_dev,),
                                daemon=True,
                            ).start()
                        else:
                            plugin.logger.warning(
                                f"[blu webhook] Device {dev_id} not found (gateway IP: {gw_ip})"
                            )
                        self.send_response(404); self.end_headers(); return

                    plugin._process_blu_event(target, payload)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")

                except Exception as exc:
                    plugin.logger.error(f"[blu webhook] Handler error: {exc}")
                    try:
                        self.send_response(500); self.end_headers()
                    except Exception:
                        pass

            def log_message(self, format, *args):
                pass

        class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        try:
            self.webhook_server = ThreadedHTTPServer(("", self.webhook_port), WebhookHandler)
            threading.Thread(
                target=self.webhook_server.serve_forever, daemon=True
            ).start()
            log(f"Webhook listener started on port {self.webhook_port}")
        except Exception as exc:
            log(f"Could not start webhook listener on port {self.webhook_port}: {exc} — set a different port in Plugin Config and reload", level="ERROR")
            self.webhook_server = None

    # ---------------------------------------------------------------------------
    # Webhook configuration on Shelly devices
    # ---------------------------------------------------------------------------

    def _dup_ids_cached(self, max_age=60):
        """Duplicate-device ids with a short cache (v3.13) — cheap enough to
        consult on EVERY webhook-configure path, not just the 6-hourly health
        check (deviceStartComm and menuResetWebhooks used to let a duplicate
        record clobber the keeper's hooks between checks)."""
        now = time.time()
        cached = getattr(self, "_dup_cache", None)
        if cached and (now - cached[0]) < max_age:
            return cached[1]
        try:
            dup_ids, _collisions = self._duplicate_device_ids()
        except Exception:
            dup_ids = set()
        self._dup_cache = (now, dup_ids)
        return dup_ids

    def _configure_webhooks(self, dev):
        ip      = dev.pluginProps.get("ip_address", "").strip()
        type_id = dev.deviceTypeId
        if not ip:
            return False
        if not self.server_ip:
            # v3.13: without the Indigo server IP the URLs would be
            # 'http://:8178/...' — the device accepts them and then fires
            # webhooks at nothing. Skip until configured.
            log(f'[{dev.name}] Webhooks skipped - no Indigo server IP '
                f'configured (set it in IndigoSecrets.py or the plugin config)',
                level="WARNING")
            return False
        if dev.id in self._dup_ids_cached():
            self.logger.debug(f'[{dev.name}] webhook configure skipped — '
                              f'duplicate record (see health-check warning)')
            return False

        base = f"http://{self.server_ip}:{self.webhook_port}/shellyEvent?devId={dev.id}"
        chan = self._pref_int(dev.pluginProps, "channel_id", 0)

        if type_id == "shellyRelay":
            wanted = [
                ("switch.on",  f"{base}&type=switch&state=on",  chan),
                ("switch.off", f"{base}&type=switch&state=off", chan),
            ]
            # Register button webhooks on channel 0 device only (input is shared)
            if chan == 0:
                wanted += [
                    ("input.single_push", f"{base}&type=button&event=single&input_id=0", 0),
                    ("input.double_push", f"{base}&type=button&event=double&input_id=0", 0),
                    ("input.long_push",   f"{base}&type=button&event=long&input_id=0",   0),
                ]
            self._ensure_webhooks(ip, dev, wanted)

        elif type_id == "shellyUni":
            wanted = [
                ("switch.on",         f"{base}&type=switch&state=on",           0),
                ("switch.off",        f"{base}&type=switch&state=off",          0),
                ("input.on",          f"{base}&type=input&input=0&state=on",    0),
                ("input.off",         f"{base}&type=input&input=0&state=off",   0),
                ("input.on",          f"{base}&type=input&input=1&state=on",    1),
                ("input.off",         f"{base}&type=input&input=1&state=off",   1),
                ("input.single_push", f"{base}&type=button&event=single&input_id=0", 0),
                ("input.double_push", f"{base}&type=button&event=double&input_id=0", 0),
                ("input.long_push",   f"{base}&type=button&event=long&input_id=0",   0),
                ("input.single_push", f"{base}&type=button&event=single&input_id=1", 1),
                ("input.double_push", f"{base}&type=button&event=double&input_id=1", 1),
                ("input.long_push",   f"{base}&type=button&event=long&input_id=1",   1),
            ]
            self._ensure_webhooks(ip, dev, wanted)

        elif type_id == "shellyCover":
            wanted = [
                ("cover.open",    f"{base}&type=cover_change", 0),
                ("cover.close",   f"{base}&type=cover_change", 0),
                ("cover.stopped", f"{base}&type=cover_change", 0),
            ]
            self._ensure_webhooks(ip, dev, wanted)

        elif type_id in LIGHT_TYPES:
            wanted = [
                ("light.on",  f"{base}&type=light&state=on",  chan),
                ("light.off", f"{base}&type=light&state=off", chan),
            ]
            self._ensure_webhooks(ip, dev, wanted)

        elif type_id == "shellyI4":
            wanted = []
            for i in range(4):
                wanted += [
                    ("input.on",          f"{base}&type=input&input={i}&state=on",    i),
                    ("input.off",         f"{base}&type=input&input={i}&state=off",   i),
                    ("input.single_push", f"{base}&type=button&event=single&input_id={i}", i),
                    ("input.double_push", f"{base}&type=button&event=double&input_id={i}", i),
                    ("input.long_push",   f"{base}&type=button&event=long&input_id={i}",   i),
                ]
            self._ensure_webhooks(ip, dev, wanted)

        elif type_id == "shellyHT":
            # v3.13: real Gen2+ webhook macros are ${ev.*} — the old
            # {temperature}-style tokens were never substituted, so the handler
            # received literal '{temperature}' strings (and 'alarm.on' /
            # 'flood.detected' below were not real event names). Battery has no
            # event token; it arrives with the device's periodic wake report.
            # NB: per API docs — no battery sensor hardware in the fleet to
            # live-verify; the handler tolerates unsubstituted tokens either way.
            self._setup_sensor_webhook(ip, dev, f"{base}&type=ht&tC=${{ev.tC}}",
                                       "temperature.change")
            self._setup_sensor_webhook(ip, dev, f"{base}&type=ht&humidity=${{ev.rh}}",
                                       "humidity.change")

        elif type_id == "shellySmoke":
            self._setup_sensor_webhook(ip, dev, f"{base}&type=smoke&alarm=true",
                                       "smoke.alarm")
            self._setup_sensor_webhook(ip, dev, f"{base}&type=smoke&alarm=false",
                                       "smoke.alarm_off")

        elif type_id == "shellyFlood":
            self._setup_sensor_webhook(ip, dev, f"{base}&type=flood&flood=true",
                                       "flood.alarm")
            self._setup_sensor_webhook(ip, dev, f"{base}&type=flood&flood=false",
                                       "flood.alarm_off")

        elif type_id in BLU_TYPES:
            # BLU devices: webhooks registered on the BLE gateway device's IP.
            # Uses a separate handler path to avoid interfering with the gateway's
            # own relay/switch webhooks.
            self._configure_blu_webhooks(ip, dev)

        return True   # configuration dispatched (v3.14 — the menu counts on this)

    def _configure_blu_webhooks(self, ip, dev):
        """Register bthomedevice press-event webhooks on the BLE gateway for this BLU device.

        The gateway fires POST requests to /shellyBluEvent?devId=<id> for each press.
        We never delete the gateway's own relay webhooks — only manage BLU URLs that
        contain our own devId marker.
        """
        if not self.server_ip:
            log(f'[{dev.name}] BLU webhooks skipped - no Indigo server IP '
                f'configured', level="WARNING")
            return
        try:
            bthome_id   = self._pref_int(dev.pluginProps, "bthome_id", 0)
            blu_url     = f"http://{self.server_ip}:{self.webhook_port}/shellyBluEvent?devId={dev.id}"

            # RC4 supports triple_push; single-button BLU does not
            if dev.deviceTypeId == "shellyBluRC4":
                press_events = ["single_push", "double_push", "triple_push", "long_push"]
            else:
                press_events  = ["single_push", "double_push", "long_push"]

            resp = self._rget(f"http://{ip}/rpc/Webhook.List")
            resp.raise_for_status()
            hooks = resp.json().get("hooks", [])

            # Collect event names already registered for this specific BLU device URL
            have_events = set()
            for hook in hooks:
                for u in hook.get("urls", []):
                    if f"shellyBluEvent?devId={dev.id}" in u:
                        have_events.add(hook.get("event", ""))

            # Create any missing press-event webhooks
            created = 0
            for event_name in press_events:
                event_key = f"bthomedevice.{event_name}"
                if event_key not in have_events:
                    self._rget(
                        f"http://{ip}/rpc/Webhook.Create",
                        params={
                            "cid":    bthome_id,
                            "enable": "true",
                            "event":  event_key,
                            "urls":   json.dumps([blu_url]),
                        },
                    )
                    self.logger.debug(
                        f'[{dev.name}] Created {event_key} BLU webhook (cid={bthome_id})'
                    )
                    created += 1

            log(
                f'[{dev.name}] BLU webhooks OK on gateway {ip}'
                + (f' ({created} created)' if created else ' (all present)')
            )

        except requests.exceptions.ConnectionError:
            log(
                f'[{dev.name}] BLU webhook setup failed — no route to gateway {ip}', level="WARNING"
            )
        except requests.exceptions.Timeout:
            log(
                f'[{dev.name}] BLU webhook setup timed out (gateway {ip})', level="WARNING"
            )
        except Exception as exc:
            log(f'[{dev.name}] BLU webhook setup failed: {exc}', level="WARNING")

    def _ensure_webhooks(self, ip, dev, wanted):
        """Create missing webhooks and delete stale ones for this device.

        v3.12: the stale test is devId-AWARE. The old rule ("any shellyEvent
        URL not in this device's wanted set is stale") deleted SIBLING
        CHANNELS' hooks on multi-channel devices (Plus 2PM / Pro 4PM / 2-ch
        dimmers) — each channel's Indigo record carries its own devId in its
        URLs, so channel 0's repair wiped channel 1's hooks and vice versa,
        forever (the v3.11 back-off never engaged because each repair's own
        recheck passed). A shellyEvent URL is now stale only when its parsed
        devId belongs to NO live self-owned device — which still cleans up ids
        left behind by deleted/recreated devices. Deletion is per-HOOK and only
        when the hook carries no wanted URL, so a (hand-edited) multi-URL hook
        that still serves this device is never silently lost.
        """
        try:
            resp = self._rget(f"http://{ip}/rpc/Webhook.List")
            resp.raise_for_status()
            hooks = resp.json().get("hooks", [])

            wanted_urls = {url for _, url, _ in wanted}
            live_ids    = {d.id for d in indigo.devices.iter("self")}
            have_urls   = set()
            stale_ids   = []

            for hook in hooks:
                hook_wanted = False
                hook_stale  = False
                for u in hook.get("urls", []):
                    if u in wanted_urls:
                        have_urls.add(u)
                        hook_wanted = True
                    elif "shellyEvent" in u:
                        m = re.search(r"[?&]devId=(\d+)(?:&|$)", u)
                        if m is None or int(m.group(1)) not in live_ids:
                            hook_stale = True   # orphaned devId — safe to delete
                        # else: a LIVE sibling device's hook — leave it alone
                if hook_stale and not hook_wanted:
                    stale_ids.append(hook.get("id"))

            for hook_id in stale_ids:
                try:
                    self._rget(f"http://{ip}/rpc/Webhook.Delete", params={"id": hook_id})
                    log(f'[{dev.name}] Deleted stale webhook id={hook_id}')
                except Exception as exc:
                    log(f'[{dev.name}] Could not delete stale hook {hook_id}: {exc}', level="WARNING")

            failed = 0
            for event, url, cid in wanted:
                if url not in have_urls:
                    cresp = self._rget(
                        f"http://{ip}/rpc/Webhook.Create",
                        params={"cid": cid, "enable": "true",
                                "event": event, "urls": json.dumps([url])}
                    )
                    # v3.14: a failed create used to be invisible — 'Webhooks
                    # OK' was logged anyway. input.* rejections are EXPECTED on
                    # hardware without an input component (plugs) — those log
                    # at debug; failures on the device's primary events WARN.
                    if cresp.status_code != 200 or "code" in (cresp.json() or {}):
                        if event.startswith("input."):
                            self.logger.debug(
                                f'[{dev.name}] {event} webhook not supported '
                                f'(no input component on this hardware)')
                        else:
                            failed += 1
                            self.logger.warning(
                                f'[{dev.name}] Webhook.Create failed for {event} '
                                f'(hook cap reached?)')
                    else:
                        self.logger.debug(f'[{dev.name}] Created {event} webhook (cid={cid})')

            if failed:
                log(f'[{dev.name}] Webhooks partially configured — {failed} create(s) '
                    f'failed', level="WARNING")
            else:
                log(f'[{dev.name}] Webhooks OK')

        except requests.exceptions.ConnectionError:
            log(f'[{dev.name}] Webhook setup failed - no route to {ip} - poll-only', level="WARNING")
        except requests.exceptions.Timeout:
            log(f'[{dev.name}] Webhook setup timed out ({ip}) - poll-only', level="WARNING")
        except Exception as exc:
            log(f'[{dev.name}] Webhook setup failed: {exc} - poll-only', level="WARNING")

    def _setup_sensor_webhook(self, ip, dev, url_template, event):
        """Attempt to configure a webhook on a battery sensor; log manual URL on failure.

        v3.13: Webhook.List first — the old blind Create accumulated one
        duplicate hook per restart / menuResetWebhooks on any AWAKE sensor.
        List fails harmlessly on a sleeping sensor, preserving the fallback."""
        try:
            try:
                lresp = self._rget(f"http://{ip}/rpc/Webhook.List")
                if lresp.status_code == 200:
                    for hook in (lresp.json() or {}).get("hooks", []):
                        if hook.get("event") == event and any(
                                f"devId={dev.id}&" in u
                                for u in hook.get("urls", [])):
                            self.logger.debug(
                                f'[{dev.name}] {event} webhook already present')
                            return
            except Exception:
                pass   # sleeping sensor — fall through to the Create attempt
            resp = self._rget(
                f"http://{ip}/rpc/Webhook.Create",
                params={"cid": 0, "enable": "true",
                        "event": event, "urls": json.dumps([url_template])}
            )
            resp.raise_for_status()
            log(f'[{dev.name}] Sensor webhook configured for {event}')
        except Exception:
            log(
                f'[{dev.name}] Sensor webhook not configured (device likely asleep). '
                f'Manually configure the device to POST to: {url_template}'
            )

    def _duplicate_device_ids(self):
        """Detect self-owned device records that collide on the same physical Shelly.

        Two Indigo device records bound to one physical device (same MAC, or same
        IP when a MAC isn't stored, AND the same channel) fight over that device's
        webhooks: each health check sees only the other's hooks, deletes them as
        "stale" and reinstalls its own, ping-ponging forever. Discovery normally
        prevents this (existing-IP / existing-MAC checks), but a manual double-add
        or a blank-prop window can still slip a duplicate through.

        Returns (dup_ids, collisions):
          dup_ids    - set of device IDs to treat as duplicates (every member of a
                       colliding group except the canonical lowest-id keeper)
          collisions - list of (key, keeper, [losers]) for warning the user

        Multi-channel devices legitimately share a MAC across channels, so the
        bucket key includes channel_id. BLU devices legitimately share the BLE
        gateway IP, so they're excluded entirely.
        """
        candidates = []
        mac_by_ip  = {}
        for dev in indigo.devices.iter("self"):
            if not dev.enabled or not dev.configured:
                continue
            if dev.deviceTypeId in BLU_TYPES:
                continue
            mac     = dev.pluginProps.get("mac_address", "").strip().upper()
            ip      = dev.pluginProps.get("ip_address",  "").strip()
            channel = str(dev.pluginProps.get("channel_id", "0"))
            candidates.append((dev, mac, ip, channel))
            if mac and ip:
                mac_by_ip[ip] = mac

        buckets = {}
        for dev, mac, ip, channel in candidates:
            # v3.14: an IP-only record adopts the MAC another record stores for
            # the same IP — the mixed-identity duplicate (one record with MAC,
            # one without) used to land in different buckets and escape.
            ident = mac or mac_by_ip.get(ip) or ip
            if not ident:
                continue
            buckets.setdefault((ident, channel), []).append(dev)

        dup_ids    = set()
        collisions = []
        for (ident, _channel), devs in buckets.items():
            if len(devs) > 1:
                devs_sorted = sorted(devs, key=lambda d: d.id)
                keeper      = devs_sorted[0]
                losers      = devs_sorted[1:]
                dup_ids.update(d.id for d in losers)
                collisions.append((ident, keeper, losers))
        return dup_ids, collisions

    def _check_webhook_health(self):
        """Verify webhooks are still registered on all non-battery devices and repair if not."""
        if not self.server_ip:
            self.logger.debug("Webhook health check skipped — no Indigo server IP")
            return
        self.logger.debug("Webhook health check starting ...")
        repaired = 0

        # Skip duplicate records so two devices can't ping-pong each other's
        # webhooks. Warn once per colliding identity so the user can delete one.
        dup_ids, collisions = self._duplicate_device_ids()
        for ident, keeper, losers in collisions:
            loser_str = ", ".join(f"'{d.name}' (id={d.id})" for d in losers)
            if ident not in self._dup_warned:
                log(
                    f"Duplicate device records share {ident}: keeping '{keeper.name}' "
                    f"(id={keeper.id}); {loser_str} are duplicates and are being skipped "
                    f"for webhook repair. Delete the duplicate record(s) to silence this.",
                    level="WARNING",
                )
                self._dup_warned.add(ident)

        for dev in indigo.devices.iter("self"):
            if not dev.enabled or not dev.configured:
                continue
            if dev.id in dup_ids:
                continue   # duplicate record — never touch its webhooks
            if dev.deviceTypeId in PUSH_ONLY_TYPES:
                continue
            # BLU devices: health is checked via the BLU-specific URL pattern below
            if dev.deviceTypeId in BLU_TYPES:
                ip = dev.pluginProps.get("ip_address", "").strip()
                if not ip:
                    continue
                try:
                    resp     = self._rget(f"http://{ip}/rpc/Webhook.List", timeout=3)
                    hooks    = resp.json().get("hooks", []) if resp.status_code == 200 else []
                    all_urls = [u for h in hooks for u in h.get("urls", [])]
                    if not any(f"shellyBluEvent?devId={dev.id}" in u for u in all_urls):
                        log(f'[{dev.name}] BLU webhooks missing - repairing ...')
                        self._configure_blu_webhooks(ip, dev)
                        repaired += 1
                except Exception:
                    pass
                continue
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                continue
            try:
                resp = self._rget(f"http://{ip}/rpc/Webhook.List", timeout=3)
                if resp.status_code != 200:
                    continue
                hooks    = resp.json().get("hooks", [])
                all_urls = [u for h in hooks for u in h.get("urls", [])]
                # Check at least one webhook for this device exists
                if any(f"devId={dev.id}" in u for u in all_urls):
                    self.webhook_repair_fails.pop(dev.id, None)   # present -> all good
                    continue

                fails = self.webhook_repair_fails.get(dev.id, 0)
                if fails >= MAX_WEBHOOK_REPAIR_FAILS:
                    # Repair hasn't held after several attempts — stay quietly
                    # poll-only. _mark_online clears this on the next good poll.
                    self.logger.debug(
                        f'[{dev.name}] webhooks still missing (gave up after {fails} '
                        f'attempts) - poll-only'
                    )
                    continue

                log(f'[{dev.name}] Webhooks missing - repairing ...')
                self._configure_webhooks(dev)

                # Did the repair actually stick? (flaky link / duplicate clobber)
                stuck = False
                try:
                    recheck  = self._rget(f"http://{ip}/rpc/Webhook.List", timeout=3)
                    rhooks   = recheck.json().get("hooks", []) if recheck.status_code == 200 else []
                    stuck    = any(f"devId={dev.id}" in u
                                   for h in rhooks for u in h.get("urls", []))
                except Exception:
                    stuck = False

                if stuck:
                    self.webhook_repair_fails.pop(dev.id, None)
                    repaired += 1
                else:
                    self.webhook_repair_fails[dev.id] = fails + 1
                    if self.webhook_repair_fails[dev.id] >= MAX_WEBHOOK_REPAIR_FAILS:
                        log(
                            f'[{dev.name}] Webhook repair has not held after '
                            f'{MAX_WEBHOOK_REPAIR_FAILS} attempts - staying poll-only. '
                            f'Check device reachability or duplicate device records.',
                            level="WARNING",
                        )
            except Exception:
                pass   # Device unreachable - skip silently
        if repaired:
            log(f"Webhook health check complete: {repaired} device(s) repaired")
        else:
            self.logger.debug("Webhook health check complete: all OK")

    # ---------------------------------------------------------------------------
    # BLU Bluetooth button event processing
    # ---------------------------------------------------------------------------

    def _process_blu_event(self, dev, payload):
        """Update states and fire trigger for a BLU button press.

        payload example (POST body from gateway):
            {"component":"bthomedevice:202","id":202,
             "event":"single_push","idx":1,"ts":1731931521.19}

        event  : press type string  (single_push / double_push / triple_push / long_push)
        idx    : button number 1-4  (RC4 only; BLU Button always 1)
        batteryPct / rssi: optional — sent periodically by the gateway
        """
        event = payload.get("event", "")
        idx   = int(payload.get("idx", 1))    # button index 1-4 (RC4), 1 (BLU Button)

        self.last_seen[dev.id] = time.time()
        if not dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", True)
            log(f'[{dev.name}] back online (BLU webhook)')

        kv = [
            {"key": "sensorValue", "value": True},
            {"key": "lastAction",  "value": event},
            {"key": "pressCount",  "value": int(dev.states.get("pressCount", 0)) + 1},
        ]
        if dev.deviceTypeId == "shellyBluRC4":
            kv.append({"key": "lastButton", "value": idx})

        bat  = payload.get("batteryPct")
        rssi = payload.get("rssi")
        if bat  is not None:
            kv.append({"key": "batteryPct", "value": int(bat)})
        if rssi is not None:
            kv.append({"key": "rssi",        "value": int(rssi)})

        dev.updateStatesOnServer(kv)

        label = f"button {idx} " if dev.deviceTypeId == "shellyBluRC4" else ""
        log(f'[webhook] "{dev.name}" BLU {label}{event}')

        self._fire_trigger("bluButtonPress", dev.id, {
            "press_type": event,
            "button_idx": str(idx),
        })

    # ---------------------------------------------------------------------------
    # Firmware daily notification
    # ---------------------------------------------------------------------------

    def _firmware_daily_check(self):
        """Check all devices for firmware updates and send a consolidated log/notification."""
        updates = []
        for dev in indigo.devices.iter("self"):
            if not dev.enabled:
                continue
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                continue
            try:
                resp = self._rget(f"http://{ip}/rpc/Shelly.CheckForUpdate", timeout=3)
                if resp.status_code == 200:
                    stable = resp.json().get("stable", {})
                    if stable:
                        ver = stable.get("version", "?")
                        updates.append(f"{dev.name} ({ip}): v{ver} available")
            except Exception:
                pass

        if not updates:
            self.logger.debug("Firmware daily check: all devices up to date")
            return

        msg = f"Shelly firmware updates available ({len(updates)} device(s)):\n" + \
              "\n".join(f"  {u}" for u in updates)
        log(msg)

        # Send via Pushover if plugin is available
        try:
            po = indigo.server.getPlugin("io.thechad.indigoplugin.pushover")
            if po and po.isEnabled():
                po.executeAction("send", props={
                    "msgTitle":    "Shelly Firmware Updates",
                    "msgBody":     "\n".join(updates),
                    "msgPriority": "0",
                })
        except Exception:
            pass   # Pushover not available - log-only is fine

    # ---------------------------------------------------------------------------
    # Polling dispatch
    # ---------------------------------------------------------------------------

    def _poll_device(self, dev):
        dispatch = {
            "shellyRelay":  self._poll_relay,
            "shellyUni":    self._poll_uni,
            "shellyCover":  self._poll_cover,
            "shellyDimmer": self._poll_dimmer,
            "shellyI4":     self._poll_i4,
            "shellyEM":     self._poll_em,
            "shellyRGBW":   self._poll_rgbw,
        }
        fn = dispatch.get(dev.deviceTypeId)
        if fn:
            fn(dev)
        # Push-only types (shellyHT, shellySmoke, shellyFlood) are not polled

    def _poll_relay(self, dev):
        ip         = dev.pluginProps.get("ip_address", "").strip()
        has_pm     = dev.pluginProps.get("has_pm", True)
        addon_temp = dev.pluginProps.get("addon_temp", False)
        chan       = self._pref_int(dev.pluginProps, "channel_id", 0)
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id={chan}")
            resp.raise_for_status()
            data     = resp.json()
            on_state = bool(data.get("output", False))
            kv       = [{"key": "onOffState", "value": on_state}]
            mirror   = {"on": str(on_state)}

            if has_pm:
                # v3.14: instantaneous readings are written only when PRESENT —
                # a partial response used to fabricate 0 W / 0 V readings (the
                # non-energy edition of the v3.6 phantom-zero class).
                watts   = self._get_total_wh(data, "apower")
                voltage = self._get_total_wh(data, "voltage")
                current = self._get_total_wh(data, "current")
                temp_c  = self._get_total_wh(data.get("temperature") or {}, "tC")

                if watts is not None:
                    kv.append({"key": "powerWatts", "value": watts,
                               "uiValue": f"{watts:.1f} W"})
                    mirror["watts"] = f"{watts:.1f}"
                if voltage is not None:
                    kv.append({"key": "voltage", "value": voltage,
                               "uiValue": f"{voltage:.1f} V"})
                if current is not None:
                    kv.append({"key": "currentAmps", "value": current,
                               "uiValue": f"{current:.3f} A"})
                if temp_c is not None:
                    kv.append({"key": "deviceTempC", "value": temp_c,
                               "uiValue": f"{temp_c:.1f} C"})

                # Energy is cumulative — only update from a REAL reading. A missing
                # aenergy.total (partial response, mid-reboot) must not fabricate a 0,
                # which would zero the baseline and corrupt today/month kWh.
                total_wh = self._get_total_wh(data.get("aenergy") or {}, "total")
                if total_wh is not None:
                    today_kwh, month_kwh = self._calc_energy(dev.id, total_wh)
                    kv += [
                        {"key": "energyKwhToday",   "value": round(today_kwh, 4),
                         "uiValue": f"{today_kwh:.3f} kWh"},
                        {"key": "energyKwhMonth",   "value": round(month_kwh, 4),
                         "uiValue": f"{month_kwh:.3f} kWh"},
                    ]
                    mirror["kwh_today"] = f"{today_kwh:.4f}"
                else:
                    self.logger.debug(f'[{dev.name}] no aenergy.total this poll — energy preserved')

                self._check_power_alert(dev, watts)

            if addon_temp:
                try:
                    tr = self._rget(f"http://{ip}/rpc/Temperature.GetStatus?id=100")
                    if tr.status_code == 200:
                        probe_c = float((tr.json() or {}).get("tC", 0.0))
                        kv.append({"key": "addonTempC", "value": probe_c,
                                   "uiValue": f"{probe_c:.1f} C"})
                except Exception:
                    pass

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._capture_unhandled_fields(dev, data)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"poll error: {exc}")

    def _poll_uni(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        kv     = []
        mirror = {}
        switch_data = {}
        try:
            resp = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id=0")
            resp.raise_for_status()
            switch_data = resp.json() or {}
            on_state = bool(switch_data.get("output", False))
            kv.append({"key": "onOffState", "value": on_state})
            mirror["on"] = str(on_state)

            for i in (0, 1):
                resp = self._rget(f"http://{ip}/rpc/Input.GetStatus?id={i}")
                resp.raise_for_status()
                val = bool(resp.json().get("state", False))
                kv.append({"key": f"input{i}", "value": val})
                mirror[f"input{i}"] = str(val)

            for i in (0, 1):
                resp = self._rget(f"http://{ip}/rpc/Voltmeter.GetStatus?id={i}")
                resp.raise_for_status()
                v = float(resp.json().get("voltage", 0.0))
                kv.append({"key": f"voltage{i}", "value": v, "uiValue": f"{v:.3f} V"})
                mirror[f"v{i}"] = f"{v:.3f}"

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._capture_unhandled_fields(
                dev, switch_data,
                extra_handled={"input0", "input1", "voltage0", "voltage1"},
            )
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] Uni poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"Uni poll error: {exc}")

    def _poll_cover(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        try:
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            resp = self._rget(f"http://{ip}/rpc/Cover.GetStatus?id={chan}")
            resp.raise_for_status()
            data    = resp.json()
            state   = data.get("state", "stopped")

            def _as_int(val, default=-1):
                # present-but-null fields (calibrating cover) must not crash
                # the poll and drive the device offline (v3.12)
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return default

            cur_pos = _as_int(data.get("current_pos"))
            tgt_pos = _as_int(data.get("target_pos"))
            obst    = bool(data.get("obstructed") or False)
            # Gen2+ venetian tilt is ONE field, slat_pos (commanded via
            # Cover.GoToPosition slat_pos=) — the old current_tilt/target_tilt
            # keys never exist on Gen2+ (v3.12).
            cur_tilt = _as_int(data.get("slat_pos"))
            tgt_tilt = -1   # no target-slat field in the Gen2+ API

            on_state = (state in ("open", "opening"))

            kv = [
                {"key": "onOffState", "value": on_state},
                {"key": "coverState", "value": state},
                {"key": "obstructed", "value": obst},
            ]
            if cur_pos >= 0:
                kv.append({"key": "currentPosition", "value": cur_pos,
                           "uiValue": f"{cur_pos}%"})
            if tgt_pos >= 0:
                kv.append({"key": "targetPosition", "value": tgt_pos,
                           "uiValue": f"{tgt_pos}%"})
            if cur_tilt >= 0:
                kv.append({"key": "tiltCurrentPosition", "value": cur_tilt,
                           "uiValue": f"{cur_tilt}%"})
            if tgt_tilt >= 0:
                kv.append({"key": "tiltTargetPosition", "value": tgt_tilt,
                           "uiValue": f"{tgt_tilt}%"})

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, {
                "state":    state,
                "position": str(cur_pos) if cur_pos >= 0 else "",
            })
            self._capture_unhandled_fields(
                dev, data,
                extra_handled={"obstructed", "slat_pos"},
            )
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()
            self.logger.debug(f'[{dev.name}] cover: state={state} pos={cur_pos}%')

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] cover poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"cover poll error: {exc}")

    def _poll_dimmer(self, dev):
        ip     = dev.pluginProps.get("ip_address", "").strip()
        has_pm = dev.pluginProps.get("has_pm", True)
        chan   = self._pref_int(dev.pluginProps, "channel_id", 0)
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Light.GetStatus?id={chan}")
            resp.raise_for_status()
            data       = resp.json()
            on_state   = bool(data.get("output", False))
            brightness = int(data.get("brightness") or 0)

            kv = [
                {"key": "onOffState",      "value": on_state},
                {"key": "brightnessLevel", "value": brightness,
                 "uiValue": f"{brightness}%"},
            ]
            mirror = {"on": str(on_state), "brightness": str(brightness)}

            if has_pm:
                watts = float(data.get("apower") or 0.0)
                kv.append({"key": "powerWatts", "value": watts,
                           "uiValue": f"{watts:.1f} W"})
                mirror["watts"] = f"{watts:.1f}"

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._capture_unhandled_fields(dev, data)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] dimmer poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"dimmer poll error: {exc}")

    def _poll_i4(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        kv     = []
        mirror = {}
        try:
            for i in range(4):
                resp = self._rget(f"http://{ip}/rpc/Input.GetStatus?id={i}")
                if resp.status_code != 200:
                    # v3.14: component-classified input devices may expose
                    # fewer than 4 inputs — a missing id is fine, not an error.
                    if i == 0:
                        resp.raise_for_status()   # no inputs at all IS an error
                    break
                val = bool(resp.json().get("state") or False)
                key = "sensorValue" if i == 0 else f"input{i}"
                kv.append({"key": key, "value": val})
                mirror[f"input{i}"] = str(val)

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] i4 poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"i4 poll error: {exc}")

    def _poll_em(self, dev):
        """Poll an energy-meter device.

        v3.12: the RPC wiring is component-correct (verified against the Shelly
        Gen2+ API docs — NB no EM hardware in the dev fleet to live-test):
        - 3-phase (Pro 3EM, `em:0`): EM.GetStatus / EMData.GetStatus, whose
          cumulative field is `total_act` (the old code read `total_act_energy`,
          an EM1Data key that never exists here — EM energy was dead).
        - single-phase (Pro EM, `em1:N`): EM1.GetStatus / EM1Data.GetStatus
          with the device's channel id, where `total_act_energy` IS the field
          (the old code called EM.GetStatus, which EM1 hardware doesn't answer).
        """
        ip        = dev.pluginProps.get("ip_address", "").strip()
        is_3phase = dev.pluginProps.get("is_3phase", False)
        chan      = self._pref_int(dev.pluginProps, "channel_id", 0)
        if not ip:
            return
        try:
            if is_3phase:
                resp = self._rget(f"http://{ip}/rpc/EM.GetStatus?id=0")
                resp.raise_for_status()
                data = resp.json()
                va  = float(data.get("a_voltage")   or 0.0)
                ia  = float(data.get("a_current")   or 0.0)
                pa  = float(data.get("a_act_power") or 0.0)
                vb  = float(data.get("b_voltage")   or 0.0)
                ib  = float(data.get("b_current")   or 0.0)
                pb  = float(data.get("b_act_power") or 0.0)
                vc  = float(data.get("c_voltage")   or 0.0)
                ic  = float(data.get("c_current")   or 0.0)
                pc  = float(data.get("c_act_power") or 0.0)
                tot = float(data.get("total_act_power") or (pa + pb + pc))
            else:
                resp = self._rget(f"http://{ip}/rpc/EM1.GetStatus?id={chan}")
                resp.raise_for_status()
                data = resp.json()
                va  = float(data.get("voltage")   or 0.0)
                ia  = float(data.get("current")   or 0.0)
                pa  = float(data.get("act_power") or 0.0)
                vb  = ib = pb = vc = ic = pc = 0.0
                tot = pa

            emdata   = {}
            total_wh = None
            try:
                if is_3phase:
                    er = self._rget(f"http://{ip}/rpc/EMData.GetStatus?id=0")
                else:
                    er = self._rget(f"http://{ip}/rpc/EM1Data.GetStatus?id={chan}")
                if er.status_code == 200:
                    emdata = er.json() or {}
                    total_wh = (self._em_total_wh(emdata) if is_3phase
                                else self._get_total_wh(emdata, "total_act_energy"))
            except Exception:
                pass

            kv = [
                {"key": "sensorValue",       "value": round(tot, 1), "uiValue": f"{tot:.1f} W"},
                {"key": "voltageA",         "value": va,  "uiValue": f"{va:.1f} V"},
                {"key": "currentA",         "value": ia,  "uiValue": f"{ia:.3f} A"},
                {"key": "powerA",           "value": pa,  "uiValue": f"{pa:.1f} W"},
                {"key": "voltageB",         "value": vb,  "uiValue": f"{vb:.1f} V"},
                {"key": "currentB",         "value": ib,  "uiValue": f"{ib:.3f} A"},
                {"key": "powerB",           "value": pb,  "uiValue": f"{pb:.1f} W"},
                {"key": "voltageC",         "value": vc,  "uiValue": f"{vc:.1f} V"},
                {"key": "currentC",         "value": ic,  "uiValue": f"{ic:.3f} A"},
                {"key": "powerC",           "value": pc,  "uiValue": f"{pc:.1f} W"},
            ]
            mirror = {"watts": f"{tot:.1f}"}

            # Energy is cumulative — skip on a missing/failed EMData read rather than
            # fabricating a 0 that would zero the baseline (phantom kWh spike).
            if total_wh is not None:
                today_kwh, month_kwh = self._calc_energy(dev.id, total_wh)
                kv += [
                    {"key": "energyKwhToday",  "value": round(today_kwh, 4),
                     "uiValue": f"{today_kwh:.3f} kWh"},
                    {"key": "energyKwhMonth",  "value": round(month_kwh, 4),
                     "uiValue": f"{month_kwh:.3f} kWh"},
                ]
                mirror["kwh_today"] = f"{today_kwh:.4f}"
            else:
                self.logger.debug(f'[{dev.name}] no EMData/EM1Data total this poll — energy preserved')

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._capture_unhandled_fields(dev, data)
            if emdata:
                self._capture_unhandled_fields(
                    dev, emdata,
                    extra_handled={"total_act", "total_act_energy",
                                   "a_total_act_energy", "b_total_act_energy",
                                   "c_total_act_energy"},
                )
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] EM poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"EM poll error: {exc}")

    def _poll_rgbw(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        try:
            # v3.12: poll the profile's actual component — Gen2+ RGBW hardware
            # answers RGB.GetStatus / RGBW.GetStatus, not Light.GetStatus
            # (unless configured in the plain "light" profile).
            component = self._rgbw_set_component(dev, ip)
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            resp = self._rget(f"http://{ip}/rpc/{component}.GetStatus?id={chan}")
            resp.raise_for_status()
            data       = resp.json()
            on_state   = bool(data.get("output") or False)
            brightness = int(data.get("brightness") or 0)
            mode       = data.get("mode", component.lower())
            rgb        = data.get("rgb") or [0, 0, 0]
            white      = int(data.get("white") or 0)
            watts      = float(data.get("apower") or 0.0)

            r = int(rgb[0]) if len(rgb) > 0 else 0
            g = int(rgb[1]) if len(rgb) > 1 else 0
            b = int(rgb[2]) if len(rgb) > 2 else 0

            kv = [
                {"key": "onOffState",      "value": on_state},
                {"key": "brightnessLevel", "value": brightness,
                 "uiValue": f"{brightness}%"},
                {"key": "colorMode",       "value": mode},
                {"key": "redLevel",        "value": r},
                {"key": "greenLevel",      "value": g},
                {"key": "blueLevel",       "value": b},
                {"key": "whiteLevel",      "value": white},
                {"key": "powerWatts",     "value": watts,
                 "uiValue": f"{watts:.1f} W"},
            ]
            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, {"on": str(on_state), "brightness": str(brightness)})
            self._capture_unhandled_fields(dev, data)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            log(f'[{dev.name}] RGBW poll error: {exc}', level="WARNING")
            self._poll_failed(dev, f"RGBW poll error: {exc}")

    # ---------------------------------------------------------------------------
    # RPC helpers
    # ---------------------------------------------------------------------------

    def _rgbw_component(self, dev, ip):
        """Return the Gen2+ colour component family for a shellyRGBW device:
        'rgb', 'rgbw' or 'light' (v3.12 — verified against the Shelly API docs;
        NB no RGBW hardware in the dev fleet to live-test). Gen2+ RGBW devices
        expose rgb:0 / rgbw:0 components depending on their configured profile —
        the Gen1-era Light.Set colour params the old code sent do not exist on
        them. Cached on the device props after one Shelly.GetConfig probe."""
        prof = dev.pluginProps.get("rgbw_profile", "")
        if prof in ("rgb", "rgbw", "light"):
            return prof
        prof = "light"
        try:
            resp = self._rget(f"http://{ip}/rpc/Shelly.GetConfig")
            if resp.status_code != 200:
                return "light"   # probe inconclusive — don't persist a guess
            keys = set((resp.json() or {}).keys())
            if any(k.startswith("rgbw:") for k in keys):
                prof = "rgbw"
            elif any(k.startswith("rgb:") for k in keys):
                prof = "rgb"
        except Exception:
            return "light"       # probe failed — don't persist a guess
        try:
            props = dict(dev.pluginProps)
            props["rgbw_profile"] = prof
            dev.replacePluginPropsOnServer(props)
        except Exception:
            pass
        return prof

    def _rgbw_set_component(self, dev, ip):
        """RPC component name for Set/GetStatus calls on a shellyRGBW device."""
        return {"rgb": "RGB", "rgbw": "RGBW"}.get(
            self._rgbw_component(dev, ip), "Light")

    @staticmethod
    def _pref_int(prefs, key, default):
        """Coerce a pref/prop value to int, falling back (coerced) on blank/non-numeric.

        Config menu fields can't be blanked through the GUI, but a hand-edited
        .indiPref/.indiDev or a future field-type change can yield '' or a string;
        int('') raises ValueError on the hot path. Guard once, reuse everywhere.
        """
        try:
            return int(prefs.get(key, default))
        except (ValueError, TypeError):
            return int(default)

    @staticmethod
    def _em_total_wh(emdata):
        """Cumulative Wh from a 3-phase EMData.GetStatus payload. Prefers the
        documented `total_act`; falls back to summing the per-phase totals when
        ALL three are present (v3.12 — never fabricate a partial sum)."""
        total = Plugin._get_total_wh(emdata, "total_act")
        if total is not None:
            return total
        phases = [Plugin._get_total_wh(emdata, f"{p}_total_act_energy")
                  for p in ("a", "b", "c")]
        if all(v is not None for v in phases):
            return float(sum(phases))
        return None

    @staticmethod
    def _get_total_wh(container, key):
        """Return cumulative Wh from an RPC sub-object, or None if the field is absent.

        A None result means 'no reading this poll' — callers MUST NOT treat it as 0.
        A phantom 0 is below the running baseline and would trip _calc_energy's
        counter-reset rule, zeroing the baseline and corrupting today/month kWh.
        """
        if not isinstance(container, dict):
            return None
        raw = container.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def _rget(self, url, params=None, timeout=None):
        """Wrapper around requests.get() with optional digest auth support."""
        t    = timeout if timeout is not None else self.timeout
        auth = (HTTPDigestAuth(self.shelly_user, self.shelly_pass)
                if self.shelly_user and self.shelly_pass else None)
        return requests.get(url, params=params, timeout=t, auth=auth)

    def _set_output(self, dev, ip, on):
        """Dispatch on/off to the correct RPC component for this device type."""
        chan = self._pref_int(dev.pluginProps, "channel_id", 0)
        if dev.deviceTypeId in LIGHT_TYPES:
            component = ("Light" if dev.deviceTypeId != "shellyRGBW"
                         else self._rgbw_set_component(dev, ip))
            return self._light_set(ip, chan, on=on, component=component)
        return self._switch_set(ip, chan, on, dev.name)

    def _switch_set(self, ip, channel_id, on, dev_name=""):
        on_str = "true" if on else "false"
        try:
            resp = self._rget(f"http://{ip}/rpc/Switch.Set?id={channel_id}&on={on_str}")
            resp.raise_for_status()
            return True
        except requests.exceptions.ConnectionError:
            log(f'[{dev_name}] No route to {ip}', level="ERROR")
        except requests.exceptions.Timeout:
            log(f'[{dev_name}] Timed out ({ip})', level="ERROR")
        except Exception as exc:
            log(f'[{dev_name}] Command failed: {exc}', level="ERROR")
        return False

    def _light_set(self, ip, channel_id, on, brightness=None, component="Light"):
        """Set on/brightness via the device's RPC component. component is
        'Light' for dimmers, 'RGB'/'RGBW' for Gen2+ colour devices (v3.12 —
        those profiles don't answer Light.Set)."""
        try:
            params = {"id": channel_id, "on": "true" if on else "false"}
            if brightness is not None:
                params["brightness"] = brightness
            resp = self._rget(f"http://{ip}/rpc/{component}.Set", params=params)
            resp.raise_for_status()
            return True
        except Exception as exc:
            log(f'{component}.Set failed ({ip}): {exc}', level="ERROR")
            return False

    def _cover_cmd(self, dev_id, rpc_method):
        try:
            dev = indigo.devices[dev_id]
            ip  = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            # v3.12: honour the device's channel (multi-cover devices exist now
            # that per-channel creation covers every channel-addressable type).
            chan = self._pref_int(dev.pluginProps, "channel_id", 0)
            resp = self._rget(f"http://{ip}/rpc/{rpc_method}?id={chan}")
            resp.raise_for_status()
            log(f'[{dev.name}] {rpc_method}')
            self.last_polled[dev_id] = 0   # Trigger immediate poll on next tick
        except Exception as exc:
            log(f'[{dev_id}] {rpc_method} failed: {exc}', level="ERROR")

    def _cover_standard_action(self, action, dev):
        """Map standard relay actions to cover commands."""
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self._cover_cmd(dev.id, "Cover.Open")
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self._cover_cmd(dev.id, "Cover.Close")
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            state = dev.states.get("coverState", "stopped")
            if state in ("open", "opening"):
                self._cover_cmd(dev.id, "Cover.Close")
            else:
                self._cover_cmd(dev.id, "Cover.Open")
        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self._poll_cover(dev)

    # ---------------------------------------------------------------------------
    # Online / offline tracking
    # ---------------------------------------------------------------------------

    def _mark_online(self, dev):
        self.last_seen[dev.id]  = time.time()
        self.fail_count[dev.id] = 0          # reset consecutive failure counter
        # A successful poll proves the device is reachable, so allow the webhook
        # health check to attempt repair afresh next cycle (clears any back-off).
        self.webhook_repair_fails.pop(dev.id, None)
        if not dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", True)
            log(f'[{dev.name}] back online')

    # ---------------------------------------------------------------------------
    # Dynamic-state capture (Z2M v1.7.1 / Ecowitt v2.1 pattern)
    # ---------------------------------------------------------------------------

    def _is_valid_state_id(self, key):
        """Indigo XML state IDs must start with an ASCII letter and contain only
        ASCII letters and digits.  Underscores are NOT permitted despite XML
        allowing them — Indigo's serialiser rejects with LowLevelBadParameterError.
        """
        if not key or not key[0].isascii() or not key[0].isalpha():
            return False
        return all(c.isascii() and c.isalnum() for c in key)

    def _sanitise_state_key(self, key):
        """Convert an RPC field name (snake_case, possibly mixed) into an
        Indigo-safe camelCase ASCII state ID.  See _is_valid_state_id().
        """
        if not key:
            return ""
        parts, cur = [], []
        for c in key:
            if c.isascii() and c.isalnum():
                cur.append(c)
            else:
                if cur:
                    parts.append("".join(cur))
                    cur = []
        if cur:
            parts.append("".join(cur))
        if not parts:
            return ""
        sk = parts[0][0].lower() + parts[0][1:] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
        if not sk[0].isalpha():
            sk = "shelly" + sk[:1].upper() + sk[1:]
        if sk in _RESERVED_STATE_NAMES:
            sk = "shelly" + sk[:1].upper() + sk[1:]
        return sk

    def _capture_unhandled_fields(self, dev, raw_data, extra_handled=None):
        """Persist any RPC payload field not already written by the type-specific
        poll method as a dynamic Indigo state.  Three-phase ordering avoids
        first-encounter "state key not defined" errors:

          1. Identify pending writes + new keys (no I/O)
          2. If new keys, persist seenDynamicKeys + stateListOrDisplay first
          3. Then write all values

        `extra_handled` is a per-poll-method set of keys that the curated path
        already consumed (so we don't duplicate them).  Falsy / None values and
        complex containers (dicts, lists) are skipped at the leaf level — but
        nested numeric/string fields inside dicts (e.g. wifi.rssi) are flattened
        into camelCase keys (wifiRssi).
        """
        if not isinstance(raw_data, dict):
            return
        handled = set(_RPC_HANDLED_KEYS)
        if extra_handled:
            handled |= set(extra_handled)

        # Flatten one level deep for nested objects (Sys.GetStatus.wifi.rssi etc.)
        def _flatten(prefix, obj):
            for k, v in obj.items():
                if k in handled:
                    continue
                key = f"{prefix}_{k}" if prefix else k
                if isinstance(v, dict):
                    yield from _flatten(key, v)
                elif isinstance(v, list):
                    continue   # arrays not stateable
                elif v is None or v == "":
                    continue
                else:
                    yield key, v

        seen_csv = dev.pluginProps.get("seenDynamicKeys", "")
        seen = set(s for s in seen_csv.split(",") if s and self._is_valid_state_id(s))
        pending = []
        new_keys = []

        for raw_key, raw_val in _flatten("", raw_data):
            state_key = self._sanitise_state_key(raw_key)
            if not state_key or not self._is_valid_state_id(state_key):
                continue
            if isinstance(raw_val, bool):
                state_val = bool(raw_val)
            elif isinstance(raw_val, (int, float)):
                state_val = float(raw_val) if isinstance(raw_val, float) else int(raw_val)
            else:
                state_val = str(raw_val)[:512]
            pending.append((state_key, state_val))
            if state_key not in seen:
                seen.add(state_key)
                new_keys.append(state_key)

        if new_keys:
            try:
                with self._props_lock:   # atomic RMW vs the MAC backfill (v3.14)
                    new_props = dict(dev.pluginProps)
                    new_props["seenDynamicKeys"] = ",".join(sorted(seen))
                    dev.replacePluginPropsOnServer(new_props)
                indigo.devices[dev.id].stateListOrDisplayStateIdChanged()
                log(f'[{dev.name}] imported {len(new_keys)} new field(s): {new_keys}')
            except Exception as e:
                log(f'[{dev.name}] dynamic-state refresh failed; rolling back. err={e}; new_keys={new_keys}', level="ERROR")
                try:
                    rollback = dict(dev.pluginProps)
                    rollback["seenDynamicKeys"] = seen_csv
                    dev.replacePluginPropsOnServer(rollback)
                except Exception:
                    pass
                return

        for state_key, state_val in pending:
            try:
                dev.updateStateOnServer(state_key, state_val)
            except Exception as e:
                if self.debug:
                    log(f'[{dev.name}] dynamic state {state_key!r} write failed: {e}', level="WARNING")

    def getDeviceStateList(self, dev):
        """Override to advertise dynamic states alongside the static Devices.xml ones.
        IMPORTANT: parent returns a LIVE reference to the parser's cache —
        always work on a list() copy to avoid permanent corruption.
        """
        original = indigo.PluginBase.getDeviceStateList(self, dev)
        if original is None:
            return original
        state_list = list(original)
        seen_csv = dev.pluginProps.get("seenDynamicKeys", "")
        if not seen_csv:
            return state_list
        existing = set()
        try:
            for s in state_list:
                k = s.get("Key") if hasattr(s, "get") else s["Key"]
                if k:
                    existing.add(k)
        except Exception:
            existing = set()
        for key in seen_csv.split(","):
            key = key.strip()
            if not key or key in existing or not self._is_valid_state_id(key):
                continue
            label = key[:1].upper() + key[1:]
            current = dev.states.get(key) if hasattr(dev, "states") else None
            try:
                if isinstance(current, bool):
                    state_list.append(self.getDeviceStateDictForBoolTrueFalseType(key, label, label))
                elif isinstance(current, (int, float)):
                    state_list.append(self.getDeviceStateDictForNumberType(key, label, label))
                else:
                    state_list.append(self.getDeviceStateDictForStringType(key, label, label))
                existing.add(key)
            except Exception:
                continue
        return state_list

    def _poll_failed(self, dev, reason=""):
        """Increment consecutive failure counter; only mark offline after 3 failures.

        v3.13: a failed poll now stamps last_polled so the device retries at
        its own cadence (it used to retry on EVERY 10s tick), and the poll
        loop stretches the interval to >=300s once a device is 3+ fails deep —
        a persistently-dead device no longer adds its full timeout to every
        tick of the single poll thread. _mark_online resets the counter, so a
        recovered device returns to normal cadence immediately."""
        count = self.fail_count.get(dev.id, 0) + 1
        self.fail_count[dev.id] = count
        self.last_polled[dev.id] = time.time()
        if count >= 3:
            self._mark_offline(dev, reason)

    def _mark_offline(self, dev, reason=""):
        if dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", False)
            if not dev.pluginProps.get("suppress_offline_alerts", False):
                log(f'[{dev.name}] offline - {reason}', level="WARNING")
                self._fire_trigger("deviceWentOffline", dev.id)

    def _check_online(self, dev, now):
        last = self.last_seen.get(dev.id, now)
        if dev.deviceTypeId in PUSH_ONLY_TYPES:
            # v3.13: battery sensors legitimately report hourly (or only on
            # change) — the global stale_minutes (default 10m) made them
            # flap offline/online all day. Separate, much longer threshold.
            hours = self._pref_int(self.pluginPrefs, "battery_stale_hours", 12)
            limit, label = hours * 3600, f"{hours}h"
        else:
            limit, label = self.stale_minutes * 60, f"{self.stale_minutes}m"
        if (now - last) > limit:
            self._mark_offline(dev, f"no response for >{label}")

    # ---------------------------------------------------------------------------
    # Energy tracking
    # ---------------------------------------------------------------------------

    def _energy_data_path(self):
        base = indigo.server.getInstallFolderPath()
        path = os.path.join(base, "Preferences", "Plugins", PLUGIN_ID)
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, "energy_data.json")

    def _load_energy_data(self):
        try:
            path = self._energy_data_path()
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    self.energy_data = json.load(f)
                meta = self.energy_data.get("__meta__", {})
                if isinstance(meta, dict) and meta.get("last_date"):
                    self.last_date = meta["last_date"]
                self.logger.debug(f"Energy data loaded ({len(self.energy_data)} device(s))")
        except Exception as exc:
            log(f"Could not load energy data: {exc} - starting fresh", level="WARNING")
            self.energy_data = {}

    def _save_energy_data(self):
        try:
            with self._energy_lock:
                snapshot = json.dumps(self.energy_data, indent=2)
            with open(self._energy_data_path(), "w", encoding="utf-8") as f:
                f.write(snapshot)
        except Exception as exc:
            log(f"Could not save energy data: {exc}", level="WARNING")

    def _calc_energy(self, dev_id, total_wh):
        key       = str(dev_id)
        today_str = str(date.today())
        month_str = today_str[:7]
        with self._energy_lock:
            entry = self.energy_data.get(key, {})

            if "day_baseline_wh" not in entry or total_wh < entry.get("day_baseline_wh", 0):
                entry["day_baseline_wh"] = total_wh
                entry["day_date"]        = today_str
            elif entry.get("day_date") != today_str:
                # v3.12: this device MISSED its _midnight_reset (offline at the
                # boundary, or the plugin was down). The old code kept
                # accumulating onto the stale baseline — yesterday's usage
                # leaked into today's figure and the history row was lost.
                # Roll over in place: bank the elapsed period as one history
                # row against the recorded day_date (best effort — includes any
                # post-midnight usage up to now), then re-baseline.
                stale_kwh = max(0.0, (total_wh - entry.get("day_baseline_wh", total_wh)) / 1000.0)
                entry.setdefault("history", []).append({
                    "date": entry.get("day_date", ""),
                    "kwh":  round(stale_kwh, 4),
                })
                entry["history"] = entry["history"][-HISTORY_DAYS:]
                entry["day_baseline_wh"] = total_wh
                entry["day_date"]        = today_str

            if "month_baseline_wh" not in entry or total_wh < entry.get("month_baseline_wh", 0):
                entry["month_baseline_wh"] = total_wh
                entry["month_date"]        = month_str
            elif entry.get("month_date") != month_str:
                # Same in-place rollover for the month boundary (v3.12).
                entry["month_baseline_wh"] = total_wh
                entry["month_date"]        = month_str

            self.energy_data[key] = entry
            today_kwh = max(0.0, (total_wh - entry["day_baseline_wh"])   / 1000.0)
            month_kwh = max(0.0, (total_wh - entry["month_baseline_wh"]) / 1000.0)
        return today_kwh, month_kwh

    def _midnight_reset(self, today_str):
        month_str = today_str[:7]
        log(f"Date changed to {today_str} - resetting daily energy baselines")
        energy_types = {"shellyRelay", "shellyEM"}
        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId not in energy_types:
                continue
            if dev.deviceTypeId == "shellyRelay" and not dev.pluginProps.get("has_pm", True):
                continue
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                continue
            try:
                if dev.deviceTypeId == "shellyEM":
                    # v3.12: component-correct energy reads (see _poll_em).
                    if dev.pluginProps.get("is_3phase", False):
                        er = self._rget(f"http://{ip}/rpc/EMData.GetStatus?id=0")
                        total_wh = self._em_total_wh(er.json() or {}) \
                                   if er.status_code == 200 else None
                    else:
                        emchan = self._pref_int(dev.pluginProps, "channel_id", 0)
                        er = self._rget(f"http://{ip}/rpc/EM1Data.GetStatus?id={emchan}")
                        total_wh = self._get_total_wh(er.json() or {}, "total_act_energy") \
                                   if er.status_code == 200 else None
                else:
                    chan = self._pref_int(dev.pluginProps, "channel_id", 0)
                    sr   = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id={chan}")
                    total_wh = self._get_total_wh((sr.json() or {}).get("aenergy") or {}, "total") \
                               if sr.status_code == 200 else None

                # No real reading at the boundary (timeout, non-200, missing field)?
                # Leave the baseline untouched and skip — fabricating a 0 here would
                # append a bogus history row and zero the baseline (phantom spike).
                if total_wh is None:
                    log(f'[{dev.name}] Midnight: no energy reading — baseline left unchanged', level="WARNING")
                    continue

                key = str(dev.id)
                with self._energy_lock:
                    entry = self.energy_data.get(key, {})

                    # Append yesterday's total to rolling history before resetting
                    yesterday_kwh = max(0.0, (total_wh - entry.get("day_baseline_wh", total_wh)) / 1000.0)
                    if "history" not in entry:
                        entry["history"] = []
                    entry["history"].append({
                        "date": entry.get("day_date", ""),
                        "kwh":  round(yesterday_kwh, 4),
                    })
                    # Keep only the last HISTORY_DAYS entries
                    entry["history"] = entry["history"][-HISTORY_DAYS:]

                    entry["day_baseline_wh"] = total_wh
                    entry["day_date"]        = today_str
                    if entry.get("month_date") != month_str:
                        entry["month_baseline_wh"] = total_wh
                        entry["month_date"]        = month_str
                        log(f'[{dev.name}] Monthly baseline reset for {month_str}')
                    self.energy_data[key] = entry

            except Exception as exc:
                log(f'[{dev.name}] Midnight reset failed: {exc}', level="WARNING")

        self._save_energy_data()

    # ---------------------------------------------------------------------------
    # Variable mirroring  (ShellyDirect variable folder)
    # ---------------------------------------------------------------------------

    def _get_or_create_var_folder(self):
        """Return the ShellyDirect variable folder ID, creating it if needed."""
        if self.var_folder_id is not None:
            # Confirm it still exists
            for folder in indigo.variables.folders:
                if folder.id == self.var_folder_id:
                    return self.var_folder_id
        for folder in indigo.variables.folders:
            if folder.name == VAR_FOLDER:
                self.var_folder_id = folder.id
                return folder.id
        folder = indigo.variables.folder.create(VAR_FOLDER)
        log(f"Created variable folder: {VAR_FOLDER}")
        self.var_folder_id = folder.id
        return folder.id

    def _get_or_create_var(self, name, folder_id, value=""):
        """Update variable if it exists, create it in ShellyDirect folder if not."""
        # Variable names must not have spaces or special chars (CLAUDE.md rule)
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", name)
        try:
            indigo.variables[safe_name]   # existence check — KeyError means create
            indigo.variable.updateValue(safe_name, str(value))
        except KeyError:
            indigo.variable.create(safe_name, value=str(value), folder=folder_id)

    def _sanitise_var_name(self, s):
        """Convert a device name to a safe variable name component."""
        return re.sub(r"[^A-Za-z0-9]", "_", s).lower().strip("_")

    def _mirror_states(self, dev, states_to_mirror):
        """Write selected states to Indigo variables in the ShellyDirect folder."""
        if not dev.pluginProps.get("mirror_to_variable", False):
            return
        if not states_to_mirror:
            return
        try:
            folder_id = self._get_or_create_var_folder()
            prefix    = "shelly_" + self._sanitise_var_name(dev.name)[:30]
            for suffix, value in states_to_mirror.items():
                if value is None or value == "":
                    continue
                var_name = f"{prefix}_{suffix}"
                self._get_or_create_var(var_name, folder_id, str(value))
        except Exception as exc:
            log(f'[{dev.name}] Variable mirror failed: {exc}', level="WARNING")

    # ---------------------------------------------------------------------------
    # Power alert
    # ---------------------------------------------------------------------------

    def _check_power_alert(self, dev, watts):
        """Fire highPowerAlert trigger and log if watts exceeds per-device threshold."""
        if not dev.pluginProps.get("power_alert_enabled", False):
            return
        try:
            threshold = float(dev.pluginProps.get("power_alert_watts", "0"))
        except (ValueError, TypeError):
            return

        if threshold <= 0:
            return

        was_alerting = self.power_alert_active.get(dev.id, False)

        if watts > threshold and not was_alerting:
            self.power_alert_active[dev.id] = True
            log(
                f'[{dev.name}] High power alert: {watts:.1f} W exceeds {threshold:.0f} W threshold', level="WARNING"
            )
            self._fire_trigger("highPowerAlert", dev.id)

        elif watts <= threshold and was_alerting:
            self.power_alert_active[dev.id] = False
            log(f'[{dev.name}] Power back within threshold: {watts:.1f} W')

    # ---------------------------------------------------------------------------
    # Trigger helpers
    # ---------------------------------------------------------------------------

    def _fire_trigger(self, type_id, dev_id, event_props=None):
        """Execute any matching Indigo triggers for this event type and device."""
        for trigger in self.triggers:
            if trigger.pluginTypeId != type_id:
                continue
            # Check device filter — "any" or blank matches all
            t_dev = trigger.pluginProps.get("deviceId", "any")
            if t_dev and t_dev != "any" and str(dev_id) != t_dev:
                continue
            # For wired button press: apply optional input / press-type filters
            if type_id == "inputButtonPress" and event_props:
                t_input = trigger.pluginProps.get("inputId", "any")
                t_press = trigger.pluginProps.get("pressType", "any")
                if t_input != "any" and t_input != str(event_props.get("input_id", "0")):
                    continue
                if t_press != "any" and t_press != event_props.get("press_type", ""):
                    continue
            # For BLU button press: apply optional press-type / button-index filters
            if type_id == "bluButtonPress" and event_props:
                t_press = trigger.pluginProps.get("pressType", "any")
                t_idx   = trigger.pluginProps.get("buttonIdx", "any")
                if t_press != "any" and t_press != event_props.get("press_type", ""):
                    continue
                if t_idx != "any" and t_idx != str(event_props.get("button_idx", "1")):
                    continue
            try:
                indigo.trigger.execute(trigger)
            except Exception as exc:
                log(f'Trigger execute failed ({type_id}): {exc}', level="WARNING")

    def getAllShellyDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Dynamic list of all plugin devices for use in Events.xml selectors."""
        result = [("any", "Any Device")]
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            result.append((str(dev.id), dev.name))
        return result

    def getInputDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Dynamic list of devices that have physical button inputs."""
        result = [("any", "Any Device")]
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            if dev.deviceTypeId in INPUT_TYPES:
                result.append((str(dev.id), dev.name))
        return result

    def getBluDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Dynamic list of BLU Bluetooth button devices for Events.xml selectors."""
        result = [("any", "Any BLU Device")]
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            if dev.deviceTypeId in BLU_TYPES:
                result.append((str(dev.id), dev.name))
        return result

    def getPMDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Dynamic list of devices that can fire the High Power Alert.

        Only shellyRelay (with PM) evaluates the threshold — _check_power_alert is
        called solely from _poll_relay, and the power_alert_* config fields exist
        only on the relay device type. Offering dimmer/RGBW PM devices here would
        list options whose trigger can never fire.
        """
        result = [("any", "Any Device")]
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            if dev.deviceTypeId == "shellyRelay" and dev.pluginProps.get("has_pm", False):
                result.append((str(dev.id), dev.name))
        return result

    def getRGBWEffects(self, filter="", valuesDict=None, typeId="", targetId=0):
        """Dynamic list of RGBW built-in effects for Actions.xml."""
        return [(k, v) for k, v in sorted(RGBW_EFFECTS.items(), key=lambda x: int(x[0]))]

    # ---------------------------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------------------------

    def _get_or_create_device_folder(self):
        folder_name = "ShellyDirect"
        for folder in indigo.devices.folders:
            if folder.name == folder_name:
                return folder.id
        folder = indigo.devices.folder.create(folder_name)
        log(f"Created device folder: {folder_name}")
        return folder.id

    def _existing_device_ips(self):
        ips = set()
        for dev in indigo.devices.iter("self"):
            if dev.deviceTypeId in BLU_TYPES:
                # v3.13: BLU records store their GATEWAY's IP — counting it
                # here made the gateway Shelly itself undiscoverable.
                continue
            ip = dev.pluginProps.get("ip_address", "").strip()
            if ip:
                ips.add(ip)
        return ips

    def _existing_device_macs(self):
        """Return {MAC_UPPER: dev} for all plugin devices that have mac_address stored."""
        result = {}
        for dev in indigo.devices.iter("self"):
            mac = dev.pluginProps.get("mac_address", "").strip().upper()
            if mac:
                result[mac] = dev
        return result

    def _backfill_mac(self, dev):
        """Fetch and store MAC address for devices created before MAC storage was added."""
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Shelly.GetDeviceInfo", timeout=3)
            if resp.status_code == 200:
                mac = resp.json().get("mac", "").strip()
                if mac:
                    with self._props_lock:   # atomic RMW vs dynamic capture (v3.14)
                        new_props = dict(dev.pluginProps)
                        new_props["mac_address"] = mac
                        dev.replacePluginPropsOnServer(new_props)
                    self.logger.debug(f"[{dev.name}] MAC backfilled: {mac}")
        except Exception as exc:
            self.logger.debug(f"[{dev.name}] MAC backfill failed: {exc}")

    def _build_device_name(self, shelly_name, label, ip, suffix=""):
        last_oct = ip.split(".")[-1]
        base     = f"{label} {last_oct}{suffix}"
        # Use Shelly's own name if the user has set one (not a MAC-based default)
        if shelly_name and not re.fullmatch(r".+-[0-9A-Fa-f]{6}", shelly_name):
            base = f"{shelly_name}{suffix}"
        name = base
        n    = 2
        while name in indigo.devices:
            name = f"{base} ({n})"
            n   += 1
        return name

    def _is_cover_mode(self, ip):
        """Return True/False for a definitive answer, None when INCONCLUSIVE
        (v3.14 — a transient timeout on the flaky subnet used to read as
        'not cover mode' and permanently misclassify a 2PM as two relays;
        discovery now skips the device this run and retries next time)."""
        try:
            resp = self._rget(f"http://{ip}/rpc/Cover.GetStatus?id=0", timeout=2)
            if resp.status_code == 200:
                return "state" in resp.json()
            return False   # answered, not a cover profile
        except Exception:
            return None    # unreachable — don't guess

    def _create_device(self, ip, type_id, has_pm, name, folder_id, extra_props=None):
        props = {
            "ip_address":           ip,
            "has_pm":               has_pm,
            "poll_interval":        "30",
            "lock_off":             False,
            "channel_id":           "0",
            "addon_temp":           False,
            "mirror_to_variable":   False,
            "power_alert_enabled":  False,
            "power_alert_watts":    "2000",
        }
        if extra_props:
            props.update(extra_props)
        try:
            dev = indigo.device.create(
                protocol     = indigo.kProtocol.Plugin,
                name         = name,
                pluginId     = PLUGIN_ID,
                deviceTypeId = type_id,
                folder       = folder_id,
                props        = props,
            )
            return dev
        except Exception as exc:
            log(f"[Discovery] Could not create device for {ip}: {exc}", level="ERROR")
            return None

    def _discover_thread(self, subnet):
        found         = []
        created       = []
        skipped       = []
        existing_ips  = self._existing_device_ips()
        existing_macs = self._existing_device_macs()
        folder_id     = self._get_or_create_device_folder()

        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            if i % 64 == 0:
                # v3.15: progress feedback — a sparse subnet used to mean
                # minutes of total silence.
                log(f"[Discovery] {subnet}.x scan progress: {i}/254 "
                    f"({len(found)} Shelly device(s) so far)")
            try:
                resp = self._rget(f"http://{ip}/rpc/Shelly.GetDeviceInfo", timeout=1)
                if resp.status_code != 200:
                    continue

                data  = resp.json()
                app   = data.get("app",   "")
                model = data.get("model", app or "Unknown")
                name  = data.get("name",  "")
                mac   = data.get("mac",   "")
                gen   = data.get("gen",   "?")
                info  = APP_INFO.get(app)

                if info:
                    label, has_pm, base_type, num_ch = info
                else:
                    # App not in the curated APP_INFO table — classify from the
                    # device's live component set (Shelly.GetConfig) instead of
                    # blindly assuming a single relay. Without this, an unknown
                    # model that is really a dimmer/cover/RGBW/multi-channel was
                    # created as the wrong type (or lost channels). detect_shelly_
                    # devices returns one spec per channel; feed the first spec's
                    # type + the channel count into the existing creation logic
                    # below (which already handles num_ch channels + cover mode).
                    specs = []
                    try:
                        cfg = self._rget(f"http://{ip}/rpc/Shelly.GetConfig", timeout=1)
                        if cfg.status_code == 200:
                            specs = detect_shelly_devices(data, list(cfg.json().keys()))
                    except Exception:
                        specs = []
                    if specs:
                        base_type = specs[0]["device_type_id"]
                        has_pm    = bool(specs[0]["has_pm"])
                        num_ch    = len(specs)
                        label     = model
                        # v3.13: switch-classified unknowns get one PM probe —
                        # the component heuristic (pm1/em only) marked PM-capable
                        # relays as no-PM and their power data was then discarded.
                        if base_type == "shellyRelay" and not has_pm:
                            try:
                                sw = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id=0",
                                                timeout=1)
                                if sw.status_code == 200 and "apower" in (sw.json() or {}):
                                    has_pm = True
                            except Exception:
                                pass
                        log(f"[Discovery] {ip:<18} app={app or '(none)'} not in table "
                            f"-- classified from components as {base_type} x{num_ch}")
                    else:
                        # v3.13: honour the classifier's contract — an EMPTY spec
                        # list means no controllable components were found, so
                        # never persist a guessed relay. (A GetConfig FAILURE
                        # also lands here; the device is retried next run.)
                        log(f"[Discovery] {ip:<18} app={app or '(none)'} not in "
                            f"table and no controllable components identified "
                            f"-- skipped (will retry next discovery)")
                        skipped.append(ip)
                        continue

                found.append(ip)

                # MAC-based match: device moved to a new IP — update the existing
                # Indigo device rather than creating a duplicate.
                mac_upper = mac.upper()
                if mac_upper and mac_upper in existing_macs:
                    old_dev     = existing_macs[mac_upper]
                    old_ip      = old_dev.pluginProps.get("ip_address", "")
                    was_offline = not old_dev.states.get("deviceOnline", True)
                    if old_ip != ip:
                        new_props = dict(old_dev.pluginProps)
                        new_props["ip_address"] = ip
                        old_dev.replacePluginPropsOnServer(new_props)
                        # v3.13: keep the scan snapshots current — the freed
                        # old IP must be creatable for a NEW device later in
                        # this same run, and the new IP is now taken.
                        existing_ips.discard(old_ip)
                        existing_ips.add(ip)
                        log(
                            f"[Discovery] {old_dev.name:<30} IP updated {old_ip} -> {ip} -- reconfiguring webhooks"
                        )
                        fresh = indigo.devices[old_dev.id]
                        threading.Thread(
                            target=self._configure_webhooks, args=(fresh,), daemon=True
                        ).start()
                    elif was_offline:
                        log(
                            f"[Discovery] {old_dev.name:<30} {ip:<18} -- reachable but offline, repairing webhooks"
                        )
                        threading.Thread(
                            target=self._configure_webhooks, args=(old_dev,), daemon=True
                        ).start()
                    else:
                        log(
                            f"[Discovery] {old_dev.name:<30} {ip:<18} -- already configured"
                        )
                    skipped.append(ip)
                    continue

                if ip in existing_ips:
                    # v3.13: verify the LIVE MAC against the stored one — a
                    # replaced device at the same IP was silently misbound, and
                    # its stale stored MAC could later hijack this record.
                    ip_dev = next((d for d in indigo.devices.iter("self")
                                   if d.deviceTypeId not in BLU_TYPES
                                   and d.pluginProps.get("ip_address", "").strip() == ip),
                                  None)
                    if ip_dev is not None and mac_upper:
                        stored = ip_dev.pluginProps.get("mac_address", "").strip().upper()
                        if stored and stored != mac_upper:
                            log(f"[Discovery] {ip_dev.name:<30} {ip:<18} -- LIVE MAC "
                                f"{mac_upper} differs from stored {stored} (hardware "
                                f"replaced?) — updating the record's MAC",
                                level="WARNING")
                        if stored != mac_upper:
                            new_props = dict(ip_dev.pluginProps)
                            new_props["mac_address"] = mac_upper
                            ip_dev.replacePluginPropsOnServer(new_props)
                            existing_macs.pop(stored, None)
                            existing_macs[mac_upper] = ip_dev
                    log(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} -- already configured"
                    )
                    skipped.append(ip)
                    continue

                # EM special case: num_ch == 3 encodes the 3-PHASE profile
                # (Pro 3EM family) — that is ONE device, not three channels.
                em_3phase = (base_type == "shellyEM" and num_ch == 3)

                # Multi-channel: one Indigo device per channel for EVERY
                # channel-addressable type (v3.12 — the old gate applied only
                # to shellyRelay, so a Pro Dimmer 2PM or a multi-EM1 device
                # silently lost every channel but the first). Relay types
                # still get the cover-mode probe first: a multi-relay Shelly
                # in cover profile becomes ONE cover device.
                if num_ch > 1 and not em_3phase:
                    cover_mode = (self._is_cover_mode(ip)
                                  if base_type == "shellyRelay" else False)
                    if cover_mode is None:
                        log(f"[Discovery] {ip:<18} cover-mode probe inconclusive "
                            f"(device unreachable) -- skipped this run")
                        skipped.append(ip)
                        continue
                    if cover_mode:
                        dev_name = self._build_device_name(name, label + " Cover", ip)
                        new_dev  = self._create_device(
                            ip, "shellyCover", False, dev_name, folder_id,
                            {"poll_interval": "10", "mac_address": mac}
                        )
                        if new_dev:
                            created.append(new_dev.name)
                            log(
                                f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                                f"-- created '{new_dev.name}' (cover mode)"
                            )
                        continue

                    # Create N devices, one per channel
                    for ch in range(num_ch):
                        suffix   = f" Ch{ch + 1}"
                        dev_name = self._build_device_name(name, label, ip, suffix)
                        extra    = {"channel_id": str(ch), "mac_address": mac}
                        if base_type == "shellyEM":
                            extra["is_3phase"] = False   # multi-channel EM = EM1 components
                        if base_type == "shellyCover":
                            extra["poll_interval"] = "10"
                        new_dev  = self._create_device(
                            ip, base_type, has_pm, dev_name, folder_id, extra
                        )
                        if new_dev:
                            created.append(new_dev.name)
                    log(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                        f"-- created {num_ch} channel device(s)"
                    )
                    existing_ips.add(ip)                      # keep the scan
                    if mac_upper and new_dev:                 # snapshots current
                        existing_macs[mac_upper] = new_dev    # (v3.13)
                    continue

                # Single device
                dev_name = self._build_device_name(name, label, ip)
                extra    = {"mac_address": mac}
                if base_type == "shellyEM":
                    extra["is_3phase"] = em_3phase
                if base_type == "shellyCover":
                    extra["poll_interval"] = "10"

                new_dev = self._create_device(ip, base_type, has_pm, dev_name, folder_id, extra)
                if new_dev:
                    created.append(new_dev.name)
                    existing_ips.add(ip)
                    if mac_upper:
                        existing_macs[mac_upper] = new_dev
                    pm_str = "PM" if has_pm else "no PM"
                    log(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                        f"name={name or '(none)'}  mac={mac}  ({pm_str})  "
                        f"-- created '{new_dev.name}'"
                    )

            except Exception:
                pass

        # v3.15: say which configured devices on this subnet were NOT seen —
        # discovery used to report only what it found.
        unseen = []
        for dev in indigo.devices.iter("self"):
            if not dev.enabled or dev.deviceTypeId in BLU_TYPES:
                continue
            dip = dev.pluginProps.get("ip_address", "").strip()
            if dip.startswith(f"{subnet}.") and dip not in found and dip not in skipped:
                unseen.append(f"{dev.name} ({dip})")
        if unseen:
            log(f"[Discovery] {len(unseen)} configured device(s) on {subnet}.x did "
                f"NOT respond: " + ", ".join(sorted(set(unseen))), level="WARNING")

        total = len(found)
        if total == 0:
            log(f"Discovery complete: no Shelly devices found on {subnet}.0/24")
        else:
            log(
                f"Discovery complete: {total} found  |  "
                f"{len(created)} created  |  {len(skipped)} already configured"
            )
            for n in created:
                log(f"  [+] {n}")

    # ---------------------------------------------------------------------------
    # Menu handlers
    # ---------------------------------------------------------------------------

    def _banner_extras(self):
        """One source of truth for the diagnostic banner lines — used by both
        showPluginInfo and Test Shelly Connection (estate convention)."""
        devs    = [d for d in indigo.devices.iter("self")]
        online  = sum(1 for d in devs if d.states.get("deviceOnline", False))
        return [
            ("Webhook Port:",      str(self.webhook_port)),
            ("Webhook Listener:",  "running" if getattr(self, "webhook_server", None) else "NOT RUNNING"),
            ("Indigo Server IP:",  self.server_ip or "(not configured)"),
            ("Discovery Subnets:", self.subnets_raw or "(not configured)"),
            ("Devices:",           f"{len(devs)} ({online} online)"),
            ("Auth Enabled:",      "Yes" if self.shelly_user else "No"),
            ("Firmware Notify:",   "Yes" if self.firmware_notify else "No"),
            ("Timestamps in Log:", "ON" if self.timestamp_enabled else "OFF"),
        ]

    def showPluginInfo(self, valuesDict=None, typeId=None):
        extras = self._banner_extras()
        if log_startup_banner:
            log_startup_banner(self.pluginId, self.pluginDisplayName, self.pluginVersion, extras=extras)
        else:
            indigo.server.log(f"{self.pluginDisplayName} v{self.pluginVersion}")
            for label, value in extras:
                indigo.server.log(f"  {label} {value}")

    def menuTestConnection(self, values_dict=None, type_id=""):
        """Menu: full banner + live checks in one log dump (estate convention —
        exactly what a user pastes into a forum support post). v3.15."""
        self.showPluginInfo()

        def _run_checks():
            problems = []
            if not self.server_ip:
                problems.append("no Indigo server IP configured (webhooks cannot work)")
            if not getattr(self, "webhook_server", None):
                problems.append(f"webhook listener is NOT running on port "
                                f"{self.webhook_port} (port collision?)")
            if not self.subnets:
                problems.append("no discovery subnets configured")
            devs = [d for d in indigo.devices.iter("self")
                    if d.enabled and d.configured
                    and d.deviceTypeId not in BLU_TYPES
                    and d.deviceTypeId not in PUSH_ONLY_TYPES]
            unreachable = []
            for dev in devs:
                ip = dev.pluginProps.get("ip_address", "").strip()
                if not ip:
                    continue
                try:
                    r = self._rget(f"http://{ip}/rpc/Shelly.GetDeviceInfo", timeout=2)
                    if r.status_code != 200:
                        unreachable.append(f"{dev.name} ({ip}: HTTP {r.status_code})")
                except Exception:
                    unreachable.append(f"{dev.name} ({ip}: no route/timeout)")
            if unreachable:
                problems.append(f"{len(unreachable)} device(s) unreachable: "
                                + ", ".join(unreachable))
            if problems:
                for pr in problems:
                    self.logger.error(f"Connection test FAILED — {pr}")
            else:
                self.logger.info(f"Connection test PASSED — listener up, all "
                                 f"{len(devs)} pollable device(s) reachable")

        # Serial network I/O — run off the menu thread (estate rule).
        threading.Thread(target=_run_checks, daemon=True).start()
        return True

    def menuToggleTimestamps(self):
        self.timestamp_enabled = not self.timestamp_enabled
        self.pluginPrefs["timestampEnabled"] = self.timestamp_enabled
        if self._ts_filter:
            self._ts_filter.enabled = self.timestamp_enabled
        state = "ON" if self.timestamp_enabled else "OFF"
        indigo.server.log(f"[{self.pluginDisplayName}] Timestamps in Log -> {state}")
