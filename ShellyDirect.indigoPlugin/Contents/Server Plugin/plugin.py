#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    plugin.py
# Description: Shelly Gen 2/3/4 direct-to-Indigo control plugin
#              Relay, Cover, Dimmer, RGBW, Energy Meter, Sensors
# Author:      CliveS & Claude Sonnet 4.6
# Date:        24-04-2026
# Version:     2.5

import csv
import http.server
import indigo
import json
import logging
import os
import platform
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

PLUGIN_ID    = "com.clives.indigoplugin.shellydirect"
WEBHOOK_PORT = 8178   # Plugin-owned HTTP listener
VAR_FOLDER   = "ShellyDirect"
HISTORY_DAYS = 30     # Rolling daily energy history retained per device

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
    "ProEM":         ("Pro EM",               False,  "shellyEM",     1),
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

        self.timeout         = int(prefs.get("timeout_secs",        3))
        self.server_ip       = prefs.get("indigo_server_ip",        "192.168.100.160")
        self.subnets_raw     = prefs.get("discovery_subnets",       "192.168.4")
        self.subnets         = [s.strip() for s in self.subnets_raw.split(",") if s.strip()]
        self.stale_minutes   = int(prefs.get("stale_minutes",       10))
        self.shelly_user     = prefs.get("shelly_username",         "").strip()
        self.shelly_pass     = prefs.get("shelly_password",         "").strip()
        self.firmware_notify = prefs.get("firmware_notify_enabled", False)

        self.last_polled          = {}   # {dev_id: float}
        self.last_seen            = {}   # {dev_id: float}
        self.fail_count           = {}   # {dev_id: int}  consecutive poll failures
        self.webhook_server       = None
        self.energy_data          = {}   # {str(dev_id): {...baselines + history...}}
        self.last_date            = str(date.today())
        self.power_alert_active   = {}   # {dev_id: bool}
        self.triggers             = []   # active Indigo trigger objects
        self.var_folder_id        = None # lazy-created ShellyDirect variable folder
        self.last_webhook_check   = 0.0  # timestamp of last webhook health check
        self.last_firmware_check  = 0.0  # timestamp of last firmware notify check

        log_level = int(prefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(log_level)
        self._load_energy_data()

        if log_startup_banner:
            log_startup_banner(plugin_id, display_name, version, extras=[
                ("Webhook Port:",      str(WEBHOOK_PORT)),
                ("Discovery Subnets:", self.subnets_raw),
                ("Auth Enabled:",      "Yes" if self.shelly_user else "No"),
                ("Firmware Notify:",   "Yes" if self.firmware_notify else "No"),
            ])
        else:
            indigo.server.log(f"{display_name} v{version} starting")

    def startup(self):
        self._start_webhook_server()

    def shutdown(self):
        self.logger.info("Shelly Direct plugin stopping")
        self._save_energy_data()
        if self.webhook_server:
            self.webhook_server.shutdown()

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
        # BLU devices are pure-event Bluetooth peripherals — nothing to poll directly
        if dev.deviceTypeId not in BLU_TYPES:
            self._poll_device(dev)
        self._configure_webhooks(dev)

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
            errors["discovery_subnets"] = "At least one subnet is required (e.g. 192.168.4)"
        else:
            for s in raw.split(","):
                s = s.strip()
                parts = s.split(".")
                if len(parts) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                    errors["discovery_subnets"] = (
                        f"Invalid subnet '{s}'. Use three octets only, e.g. 192.168.4"
                    )
                    break
        return (len(errors) == 0), values_dict, errors

    def closedPrefsConfigUi(self, values_dict, user_cancelled):
        if not user_cancelled:
            self.timeout         = int(values_dict.get("timeout_secs",        3))
            self.server_ip       = values_dict.get("indigo_server_ip",        "192.168.100.160")
            self.subnets_raw     = values_dict.get("discovery_subnets",       "192.168.4")
            self.subnets         = [s.strip() for s in self.subnets_raw.split(",") if s.strip()]
            self.stale_minutes   = int(values_dict.get("stale_minutes",       10))
            self.shelly_user     = values_dict.get("shelly_username",        "").strip()
            self.shelly_pass     = values_dict.get("shelly_password",        "").strip()
            self.firmware_notify = values_dict.get("firmware_notify_enabled", False)
            self.indigo_log_handler.setLevel(int(values_dict.get("logLevel", logging.INFO)))

    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):
        errors = indigo.Dict()
        ip = values_dict.get("ip_address", "").strip()
        if not ip:
            label = "Gateway IP address is required." if type_id in BLU_TYPES else "IP address is required."
            errors["ip_address"] = label
        else:
            parts = ip.split(".")
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                errors["ip_address"] = "Please enter a valid IPv4 address (e.g. 192.168.4.10)."
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

    # ---------------------------------------------------------------------------
    # Standard device actions  (relay, uni, cover on/off, dimmer on/off)
    # ---------------------------------------------------------------------------

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
                self.logger.error(f'[{dev.name}] No IP address configured')
                return

            if action.deviceAction == indigo.kDeviceAction.TurnOn:
                if self._set_output(dev, ip, True):
                    self.logger.info(f'sent "{dev.name}" on')
                    dev.updateStateOnServer("onOffState", True)
                else:
                    self.logger.error(f'failed to send on to "{dev.name}"')

            elif action.deviceAction == indigo.kDeviceAction.TurnOff:
                if dev.pluginProps.get("lock_off", False):
                    self.logger.warning(f'[{dev.name}] Turn Off blocked - device is locked')
                    return
                if self._set_output(dev, ip, False):
                    self.logger.info(f'sent "{dev.name}" off')
                    dev.updateStateOnServer("onOffState", False)
                else:
                    self.logger.error(f'failed to send off to "{dev.name}"')

            elif action.deviceAction == indigo.kDeviceAction.Toggle:
                new_state = not dev.onState
                if new_state is False and dev.pluginProps.get("lock_off", False):
                    self.logger.warning(f'[{dev.name}] Toggle to Off blocked - device is locked')
                    return
                if self._set_output(dev, ip, new_state):
                    label = "on" if new_state else "off"
                    self.logger.info(f'sent "{dev.name}" toggle -> {label}')
                    dev.updateStateOnServer("onOffState", new_state)
                else:
                    self.logger.error(f'failed to toggle "{dev.name}"')

            elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
                self._poll_device(dev)

        except Exception as exc:
            self.logger.error(f'actionControlDevice exception for "{dev.name}": {exc}')

    def actionControlDimmer(self, action, dev):
        """Handle brightness actions for shellyDimmer and shellyRGBW devices."""
        try:
            ip = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                self.logger.error(f'[{dev.name}] No IP address configured')
                return

            channel_id = int(dev.pluginProps.get("channel_id", 0))

            if action.deviceAction == indigo.kDimmerAction.TurnOn:
                if self._light_set(ip, channel_id, on=True):
                    dev.updateStateOnServer("onOffState", True)
                    self.logger.info(f'sent "{dev.name}" on')

            elif action.deviceAction == indigo.kDimmerAction.TurnOff:
                if self._light_set(ip, channel_id, on=False):
                    dev.updateStateOnServer("onOffState", False)
                    self.logger.info(f'sent "{dev.name}" off')

            elif action.deviceAction == indigo.kDimmerAction.Toggle:
                new_state = not dev.onState
                if self._light_set(ip, channel_id, on=new_state):
                    dev.updateStateOnServer("onOffState", new_state)
                    self.logger.info(f'sent "{dev.name}" toggle -> {"on" if new_state else "off"}')

            elif action.deviceAction == indigo.kDimmerAction.SetBrightness:
                brightness = max(0, min(100, int(action.actionValue)))
                if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", brightness > 0)
                    self.logger.info(f'sent "{dev.name}" brightness -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.BrightenBy:
                current    = dev.states.get("brightnessLevel", 0)
                brightness = min(100, current + int(action.actionValue))
                if self._light_set(ip, channel_id, on=True, brightness=brightness):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", True)
                    self.logger.info(f'sent "{dev.name}" brighten -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.DimBy:
                current    = dev.states.get("brightnessLevel", 100)
                brightness = max(0, current - int(action.actionValue))
                if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness):
                    dev.updateStateOnServer("brightnessLevel", brightness)
                    dev.updateStateOnServer("onOffState", brightness > 0)
                    self.logger.info(f'sent "{dev.name}" dim -> {brightness}%')

            elif action.deviceAction == indigo.kDimmerAction.RequestStatus:
                self._poll_device(dev)

        except Exception as exc:
            self.logger.error(f'actionControlDimmer exception for "{dev.name}": {exc}')

    # ---------------------------------------------------------------------------
    # Custom actions
    # ---------------------------------------------------------------------------

    def actionOnForSeconds(self, action):
        """Turn relay on for N seconds using Shelly's native toggle_after."""
        try:
            dev     = indigo.devices[action.deviceId]
            seconds = int(action.props.get("seconds", 1))
            ip      = dev.pluginProps.get("ip_address", "").strip()
            chan    = int(dev.pluginProps.get("channel_id", 0))
            if not ip:
                self.logger.error(f'[{dev.name}] No IP for on_for_seconds')
                return
            resp = self._rget(
                f"http://{ip}/rpc/Switch.Set?id={chan}&on=true&toggle_after={seconds}"
            )
            resp.raise_for_status()
            self.logger.info(f'[{dev.name}] on for {seconds}s')
            dev.updateStateOnServer("onOffState", True)
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] on_for_seconds failed: {exc}')

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
            resp = self._rget(f"http://{ip}/rpc/Cover.GoToPosition", params={"id": 0, "pos": pos})
            resp.raise_for_status()
            dev.updateStateOnServer("targetPosition", pos)
            self.logger.info(f'[{dev.name}] going to position {pos}%')
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] GoToPosition failed: {exc}')

    def actionCoverSetTilt(self, action):
        """Set venetian blind tilt angle (0=closed slats, 100=open slats)."""
        try:
            tilt = max(0, min(100, int(action.props.get("tilt", 50))))
            dev  = indigo.devices[action.deviceId]
            ip   = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            resp = self._rget(
                f"http://{ip}/rpc/Cover.GoToPosition",
                params={"id": 0, "tilt": tilt}
            )
            resp.raise_for_status()
            dev.updateStateOnServer("tiltTargetPosition", tilt)
            self.logger.info(f'[{dev.name}] tilt set to {tilt}%')
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] SetTilt failed: {exc}')

    def actionSetBrightness(self, action):
        try:
            dev        = indigo.devices[action.deviceId]
            brightness = max(0, min(100, int(action.props.get("brightness", 100))))
            ip         = dev.pluginProps.get("ip_address", "").strip()
            channel_id = int(dev.pluginProps.get("channel_id", 0))
            if not ip:
                return
            if self._light_set(ip, channel_id, on=(brightness > 0), brightness=brightness):
                dev.updateStateOnServer("brightnessLevel", brightness)
                dev.updateStateOnServer("onOffState", brightness > 0)
                self.logger.info(f'[{dev.name}] brightness set to {brightness}%')
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] SetBrightness failed: {exc}')

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
            resp = self._rget(
                f"http://{ip}/rpc/Light.Set",
                params={"id": 0, "on": "true", "mode": "color",
                        "red": r, "green": g, "blue": b, "white": w, "brightness": br}
            )
            resp.raise_for_status()
            dev.updateStateOnServer("onOffState",     True)
            dev.updateStateOnServer("brightnessLevel", br)
            dev.updateStateOnServer("redLevel",        r)
            dev.updateStateOnServer("greenLevel",      g)
            dev.updateStateOnServer("blueLevel",       b)
            dev.updateStateOnServer("whiteLevel",      w)
            dev.updateStateOnServer("colorMode",       "color")
            self.logger.info(f'[{dev.name}] color set R={r} G={g} B={b} W={w} @{br}%')
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] SetColor failed: {exc}')

    def actionSetEffect(self, action):
        """Trigger a built-in light effect on a Shelly RGBW device."""
        try:
            dev    = indigo.devices[action.deviceId]
            ip     = dev.pluginProps.get("ip_address", "").strip()
            effect = int(action.props.get("effect", 0))
            if not ip:
                return
            resp = self._rget(
                f"http://{ip}/rpc/Light.Set",
                params={"id": 0, "on": "true", "effect": effect}
            )
            resp.raise_for_status()
            label = RGBW_EFFECTS.get(str(effect), f"effect {effect}")
            self.logger.info(f'[{dev.name}] effect set: {label}')
        except Exception as exc:
            self.logger.error(f'[{action.deviceId}] SetEffect failed: {exc}')

    # ---------------------------------------------------------------------------
    # Polling thread
    # ---------------------------------------------------------------------------

    def runConcurrentThread(self):
        try:
            while True:
                today_str = str(date.today())
                if today_str != self.last_date:
                    self._midnight_reset(today_str)
                    self.last_date = today_str

                now = time.time()

                # Webhook health check every 6 hours
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

                    interval = int(dev.pluginProps.get("poll_interval", 30))
                    if (now - self.last_polled.get(dev.id, 0)) >= interval:
                        try:
                            self._poll_device(dev)
                        except Exception as exc:
                            self.logger.warning(f'poll exception "{dev.name}": {exc}')

                self.sleep(10)
        except self.StopThread:
            pass

    # ---------------------------------------------------------------------------
    # Menu actions
    # ---------------------------------------------------------------------------

    def menuDiscoverDevices(self, values_dict=None, type_id=""):
        for subnet in self.subnets:
            self.logger.info(f"Discovery started - scanning {subnet}.1 to {subnet}.254 ...")
            threading.Thread(
                target=self._discover_thread, args=(subnet,), daemon=True
            ).start()
        return True

    def menuCheckFirmware(self, values_dict=None, type_id=""):
        self.logger.info("Checking firmware versions ...")
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
                self.logger.info(f'[{dev.name}] ({ip}) firmware {msg}')
            except Exception as exc:
                self.logger.warning(f'[{dev.name}] ({ip}) firmware check failed: {exc}')
        return True

    def menuResetWebhooks(self, values_dict=None, type_id=""):
        self.logger.info("Reconfiguring webhooks on all devices ...")
        count = sum(1 for dev in indigo.devices.iter("self")
                    if dev.enabled and dev.configured
                    and self._configure_webhooks(dev) is not None)
        self.logger.info(f"Webhook reconfiguration complete ({count} device(s))")
        return True

    def menuDeviceHealthSummary(self, values_dict=None, type_id=""):
        """Log a formatted table showing status of every managed device."""
        self.logger.info("-" * 100)
        self.logger.info(
            f"{'Device':<30} {'IP':<18} {'Type':<18} {'Online':<8} {'Firmware':<12} {'Last Seen'}"
        )
        self.logger.info("-" * 100)
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
            self.logger.info(
                f"{dev.name:<30} {ip:<18} {dev.deviceTypeId:<18} {status:<8} {fw:<12} {age}"
            )
            seen_n += 1

        self.logger.info("-" * 100)
        self.logger.info(f"Total: {seen_n} device(s)")
        return True

    def menuExportEnergyHistory(self, values_dict=None, type_id=""):
        """Write 30-day rolling energy history to CSV in ~/Documents/Indigo/ShellyDirect/"""
        try:
            out_dir = os.path.expanduser("~/Documents/Indigo/ShellyDirect")
            os.makedirs(out_dir, exist_ok=True)
            filename  = f"energy_history_{date.today()}.csv"
            filepath  = os.path.join(out_dir, filename)
            row_count = 0

            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Device", "kWh"])

                for dev_id_str, entry in self.energy_data.items():
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

            self.logger.info(f"Energy history exported: {filepath} ({row_count} rows)")
        except Exception as exc:
            self.logger.error(f"Energy history export failed: {exc}")
        return True

    # ---------------------------------------------------------------------------
    # Webhook HTTP server
    # URL: http://<indigo_ip>:8178/shellyEvent?devId=<id>&type=<t>&...
    # ---------------------------------------------------------------------------

    def _start_webhook_server(self):
        plugin = self

        class WebhookHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    parsed   = urllib.parse.urlparse(self.path)
                    params   = urllib.parse.parse_qs(parsed.query)
                    dev_id   = int(params.get("devId",  ["0"])[0])
                    ev_type  = params.get("type",   ["switch"])[0].lower()
                    state    = params.get("state",  [""])[0].lower()
                    input_id = int(params.get("input", ["0"])[0])

                    if not dev_id:
                        self.send_response(400); self.end_headers(); return

                    try:
                        target = indigo.devices[dev_id]
                    except KeyError:
                        # Stale webhook — old devId from before devices were deleted/recreated.
                        # Use the source IP to find the current device and auto-fix its webhooks.
                        shelly_ip = self.client_address[0]
                        current_dev = None
                        for dev in indigo.devices.iter(PLUGIN_ID):
                            if dev.pluginProps.get("ip_address", "").strip() == shelly_ip:
                                current_dev = dev
                                break
                        if current_dev:
                            plugin.logger.info(
                                f"[webhook] Stale devId {dev_id} from {shelly_ip} — "
                                f"auto-reconfiguring webhooks for \"{current_dev.name}\""
                            )
                            threading.Thread(
                                target=plugin._configure_webhooks,
                                args=(current_dev,),
                                daemon=True
                            ).start()
                        else:
                            plugin.logger.warning(
                                f"[webhook] Device {dev_id} not found (source IP: {shelly_ip})"
                            )
                        self.send_response(404); self.end_headers(); return

                    plugin.last_seen[dev_id] = time.time()
                    if not target.states.get("deviceOnline", True):
                        target.updateStateOnServer("deviceOnline", True)
                        plugin.logger.info(f'[{target.name}] back online (webhook)')

                    if ev_type == "switch" and state in ("on", "off"):
                        on_state = (state == "on")
                        target.updateStateOnServer("onOffState", on_state)
                        plugin.last_polled[dev_id] = time.time()
                        plugin.logger.info(f'[webhook] "{target.name}" switch -> {state}')

                    elif ev_type == "button":
                        # Single, double or long press from any input
                        press   = params.get("event", ["single"])[0]   # single/double/long
                        inp     = int(params.get("input_id", ["0"])[0])
                        plugin.logger.info(
                            f'[webhook] "{target.name}" input{inp} {press}_press'
                        )
                        plugin._fire_trigger("inputButtonPress", dev_id, {
                            "input_id":   str(inp),
                            "press_type": press,
                        })

                    elif ev_type == "input" and state in ("on", "off"):
                        key = "sensorValue" if input_id == 0 else f"input{input_id}"
                        target.updateStateOnServer(key, state == "on")
                        plugin.logger.info(
                            f'[webhook] "{target.name}" input{input_id} -> {state}'
                        )

                    elif ev_type == "cover_change":
                        # Trigger immediate poll to get current position/state
                        plugin.last_polled[dev_id] = 0
                        plugin.logger.debug(f'[webhook] "{target.name}" cover change - poll queued')

                    elif ev_type == "light" and state in ("on", "off"):
                        on_state = (state == "on")
                        target.updateStateOnServer("onOffState", on_state)
                        plugin.last_polled[dev_id] = time.time()
                        plugin.logger.info(f'[webhook] "{target.name}" light -> {state}')

                    elif ev_type == "ht":
                        temp = params.get("tC",       [""])[0]
                        hum  = params.get("humidity", [""])[0]
                        bat  = params.get("battery",  [""])[0]
                        kv   = []
                        if temp:
                            kv.append({"key": "sensorValue", "value": float(temp),
                                       "uiValue": f"{float(temp):.1f} C"})
                        if hum:
                            kv.append({"key": "humidity", "value": float(hum),
                                       "uiValue": f"{float(hum):.1f} %"})
                        if bat:
                            kv.append({"key": "battery_pct", "value": int(float(bat)),
                                       "uiValue": f"{int(float(bat))}%"})
                        if kv:
                            target.updateStatesOnServer(kv)
                            mirror = {}
                            if temp: mirror["temp_c"]  = f"{float(temp):.1f}"
                            if hum:  mirror["humidity"] = f"{float(hum):.1f}"
                            if bat:  mirror["battery"]  = str(int(float(bat)))
                            plugin._mirror_states(target, mirror)
                        plugin.logger.info(
                            f'[webhook] "{target.name}" HT: temp={temp}C  hum={hum}%  bat={bat}%'
                        )

                    elif ev_type == "smoke":
                        alarm = params.get("alarm", ["false"])[0].lower() == "true"
                        bat   = params.get("battery", [""])[0]
                        kv    = [{"key": "sensorValue", "value": alarm}]
                        if bat:
                            kv.append({"key": "battery_pct", "value": int(float(bat))})
                        target.updateStatesOnServer(kv)
                        plugin._mirror_states(target, {"alarm": str(alarm)})
                        plugin.logger.info(
                            f'[webhook] "{target.name}" smoke: alarm={alarm}  bat={bat}%'
                        )

                    elif ev_type == "flood":
                        flood = params.get("flood",   ["false"])[0].lower() == "true"
                        temp  = params.get("tC",      [""])[0]
                        bat   = params.get("battery", [""])[0]
                        kv    = [{"key": "sensorValue", "value": flood}]
                        if temp:
                            kv.append({"key": "temperature", "value": float(temp),
                                       "uiValue": f"{float(temp):.1f} C"})
                        if bat:
                            kv.append({"key": "battery_pct", "value": int(float(bat))})
                        target.updateStatesOnServer(kv)
                        plugin._mirror_states(target, {"flood": str(flood)})
                        plugin.logger.info(
                            f'[webhook] "{target.name}" flood: flood={flood}  bat={bat}%'
                        )

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

                    length  = int(self.headers.get("Content-Length", 0))
                    body    = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError:
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
            self.webhook_server = ThreadedHTTPServer(("", WEBHOOK_PORT), WebhookHandler)
            threading.Thread(
                target=self.webhook_server.serve_forever, daemon=True
            ).start()
            self.logger.info(f"Webhook listener started on port {WEBHOOK_PORT}")
        except Exception as exc:
            self.logger.error(f"Could not start webhook listener on port {WEBHOOK_PORT}: {exc}")
            self.webhook_server = None

    # ---------------------------------------------------------------------------
    # Webhook configuration on Shelly devices
    # ---------------------------------------------------------------------------

    def _configure_webhooks(self, dev):
        ip      = dev.pluginProps.get("ip_address", "").strip()
        type_id = dev.deviceTypeId
        if not ip:
            return

        base = f"http://{self.server_ip}:{WEBHOOK_PORT}/shellyEvent?devId={dev.id}"
        chan = int(dev.pluginProps.get("channel_id", 0))

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
            sensor_url = f"{base}&type=ht&tC={{temperature}}&humidity={{humidity}}&battery={{battery}}"
            self._setup_sensor_webhook(ip, dev, sensor_url, "temperature.change")

        elif type_id == "shellySmoke":
            sensor_url = f"{base}&type=smoke&alarm={{alarm}}&battery={{battery}}"
            self._setup_sensor_webhook(ip, dev, sensor_url, "alarm.on")

        elif type_id == "shellyFlood":
            sensor_url = f"{base}&type=flood&flood={{flood}}&tC={{temperature}}&battery={{battery}}"
            self._setup_sensor_webhook(ip, dev, sensor_url, "flood.detected")

        elif type_id in BLU_TYPES:
            # BLU devices: webhooks registered on the BLE gateway device's IP.
            # Uses a separate handler path to avoid interfering with the gateway's
            # own relay/switch webhooks.
            self._configure_blu_webhooks(ip, dev)

    def _configure_blu_webhooks(self, ip, dev):
        """Register bthomedevice press-event webhooks on the BLE gateway for this BLU device.

        The gateway fires POST requests to /shellyBluEvent?devId=<id> for each press.
        We never delete the gateway's own relay webhooks — only manage BLU URLs that
        contain our own devId marker.
        """
        try:
            bthome_id   = int(dev.pluginProps.get("bthome_id", 0))
            blu_url     = f"http://{self.server_ip}:{WEBHOOK_PORT}/shellyBluEvent?devId={dev.id}"

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

            self.logger.info(
                f'[{dev.name}] BLU webhooks OK on gateway {ip}'
                + (f' ({created} created)' if created else ' (all present)')
            )

        except requests.exceptions.ConnectionError:
            self.logger.warning(
                f'[{dev.name}] BLU webhook setup failed — no route to gateway {ip}'
            )
        except requests.exceptions.Timeout:
            self.logger.warning(
                f'[{dev.name}] BLU webhook setup timed out (gateway {ip})'
            )
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] BLU webhook setup failed: {exc}')

    def _ensure_webhooks(self, ip, dev, wanted):
        """Create missing webhooks and delete stale ones for this device."""
        try:
            resp = self._rget(f"http://{ip}/rpc/Webhook.List")
            resp.raise_for_status()
            hooks = resp.json().get("hooks", [])

            wanted_urls = {url for _, url, _ in wanted}
            have_urls   = set()
            stale_ids   = []

            for hook in hooks:
                for u in hook.get("urls", []):
                    if u in wanted_urls:
                        have_urls.add(u)
                    elif "shellyEvent" in u:
                        # Any shellyEvent URL not in wanted is stale — catches old
                        # device IDs left behind after devices are deleted/recreated.
                        stale_ids.append(hook.get("id"))

            for hook_id in stale_ids:
                try:
                    self._rget(f"http://{ip}/rpc/Webhook.Delete", params={"id": hook_id})
                    self.logger.info(f'[{dev.name}] Deleted stale webhook id={hook_id}')
                except Exception as exc:
                    self.logger.warning(f'[{dev.name}] Could not delete stale hook {hook_id}: {exc}')

            for event, url, cid in wanted:
                if url not in have_urls:
                    self._rget(
                        f"http://{ip}/rpc/Webhook.Create",
                        params={"cid": cid, "enable": "true",
                                "event": event, "urls": json.dumps([url])}
                    )
                    self.logger.debug(f'[{dev.name}] Created {event} webhook (cid={cid})')

            self.logger.info(f'[{dev.name}] Webhooks OK')

        except requests.exceptions.ConnectionError:
            self.logger.warning(f'[{dev.name}] Webhook setup failed - no route to {ip} - poll-only')
        except requests.exceptions.Timeout:
            self.logger.warning(f'[{dev.name}] Webhook setup timed out ({ip}) - poll-only')
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] Webhook setup failed: {exc} - poll-only')

    def _setup_sensor_webhook(self, ip, dev, url_template, event):
        """Attempt to configure a webhook on a battery sensor; log manual URL on failure."""
        try:
            resp = self._rget(
                f"http://{ip}/rpc/Webhook.Create",
                params={"cid": 0, "enable": "true",
                        "event": event, "urls": json.dumps([url_template])}
            )
            resp.raise_for_status()
            self.logger.info(f'[{dev.name}] Sensor webhook configured for {event}')
        except Exception:
            self.logger.info(
                f'[{dev.name}] Sensor webhook not configured (device likely asleep). '
                f'Manually configure the device to POST to: {url_template}'
            )

    def _check_webhook_health(self):
        """Verify webhooks are still registered on all non-battery devices and repair if not."""
        self.logger.debug("Webhook health check starting ...")
        repaired = 0
        for dev in indigo.devices.iter("self"):
            if not dev.enabled or not dev.configured:
                continue
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
                        self.logger.info(f'[{dev.name}] BLU webhooks missing - repairing ...')
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
                base     = f"http://{self.server_ip}:{WEBHOOK_PORT}/shellyEvent?devId={dev.id}"
                # Check at least one webhook for this device exists
                if not any(f"devId={dev.id}" in u for u in all_urls):
                    self.logger.info(f'[{dev.name}] Webhooks missing - repairing ...')
                    self._configure_webhooks(dev)
                    repaired += 1
            except Exception:
                pass   # Device unreachable - skip silently
        if repaired:
            self.logger.info(f"Webhook health check complete: {repaired} device(s) repaired")
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
        battery_pct / rssi: optional — sent periodically by the gateway
        """
        event = payload.get("event", "")
        idx   = int(payload.get("idx", 1))    # button index 1-4 (RC4), 1 (BLU Button)

        self.last_seen[dev.id] = time.time()
        if not dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", True)
            self.logger.info(f'[{dev.name}] back online (BLU webhook)')

        kv = [
            {"key": "sensorValue", "value": True},
            {"key": "lastAction",  "value": event},
            {"key": "pressCount",  "value": int(dev.states.get("pressCount", 0)) + 1},
        ]
        if dev.deviceTypeId == "shellyBluRC4":
            kv.append({"key": "lastButton", "value": idx})

        bat  = payload.get("battery_pct")
        rssi = payload.get("rssi")
        if bat  is not None:
            kv.append({"key": "battery_pct", "value": int(bat)})
        if rssi is not None:
            kv.append({"key": "rssi",        "value": int(rssi)})

        dev.updateStatesOnServer(kv)

        label = f"button {idx} " if dev.deviceTypeId == "shellyBluRC4" else ""
        self.logger.info(f'[webhook] "{dev.name}" BLU {label}{event}')

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
        self.logger.info(msg)

        # Send via Pushover if plugin is available
        try:
            po = indigo.server.getPlugin("io.thechad.indigoplugin.pushover")
            if po.isEnabled():
                po.executeAction("sendPushover", props={
                    "title":   "Shelly Firmware Updates",
                    "message": "\n".join(updates),
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
        chan       = int(dev.pluginProps.get("channel_id", 0))
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
                watts    = float(data.get("apower",  0.0))
                voltage  = float(data.get("voltage", 0.0))
                current  = float(data.get("current", 0.0))
                temp_c   = float((data.get("temperature") or {}).get("tC", 0.0))
                total_wh = float((data.get("aenergy")     or {}).get("total", 0.0))

                today_kwh, month_kwh        = self._calc_energy(dev.id, total_wh)

                kv += [
                    {"key": "power_watts",        "value": watts,
                     "uiValue": f"{watts:.1f} W"},
                    {"key": "voltage",            "value": voltage,
                     "uiValue": f"{voltage:.1f} V"},
                    {"key": "current_amps",       "value": current,
                     "uiValue": f"{current:.3f} A"},
                    {"key": "device_temp_c",      "value": temp_c,
                     "uiValue": f"{temp_c:.1f} C"},
                    {"key": "energy_kwh_today",   "value": round(today_kwh, 4),
                     "uiValue": f"{today_kwh:.3f} kWh"},
                    {"key": "energy_kwh_month",   "value": round(month_kwh, 4),
                     "uiValue": f"{month_kwh:.3f} kWh"},
                ]
                mirror.update({
                    "watts":     f"{watts:.1f}",
                    "kwh_today": f"{today_kwh:.4f}",
                })
                self._check_power_alert(dev, watts)

            if addon_temp:
                try:
                    tr = self._rget(f"http://{ip}/rpc/Temperature.GetStatus?id=100")
                    if tr.status_code == 200:
                        probe_c = float((tr.json() or {}).get("tC", 0.0))
                        kv.append({"key": "addon_temp_c", "value": probe_c,
                                   "uiValue": f"{probe_c:.1f} C"})
                except Exception:
                    pass

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] poll error: {exc}')

    def _poll_uni(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        kv     = []
        mirror = {}
        try:
            resp = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id=0")
            resp.raise_for_status()
            on_state = bool(resp.json().get("output", False))
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
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] Uni poll error: {exc}')

    def _poll_cover(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Cover.GetStatus?id=0")
            resp.raise_for_status()
            data    = resp.json()
            state   = data.get("state", "stopped")
            cur_pos = int(data.get("current_pos", -1))
            tgt_pos = int(data.get("target_pos",  -1))
            obst    = bool(data.get("obstructed",  False))
            cur_tilt = int(data.get("current_tilt", -1))
            tgt_tilt = int(data.get("target_tilt",  -1))

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
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()
            self.logger.debug(f'[{dev.name}] cover: state={state} pos={cur_pos}%')

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] cover poll error: {exc}')

    def _poll_dimmer(self, dev):
        ip     = dev.pluginProps.get("ip_address", "").strip()
        has_pm = dev.pluginProps.get("has_pm", True)
        chan   = int(dev.pluginProps.get("channel_id", 0))
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Light.GetStatus?id={chan}")
            resp.raise_for_status()
            data       = resp.json()
            on_state   = bool(data.get("output", False))
            brightness = int(data.get("brightness", 0))

            kv = [
                {"key": "onOffState",      "value": on_state},
                {"key": "brightnessLevel", "value": brightness,
                 "uiValue": f"{brightness}%"},
            ]
            mirror = {"on": str(on_state), "brightness": str(brightness)}

            if has_pm:
                watts = float(data.get("apower", 0.0))
                kv.append({"key": "power_watts", "value": watts,
                           "uiValue": f"{watts:.1f} W"})
                mirror["watts"] = f"{watts:.1f}"

            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, mirror)
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] dimmer poll error: {exc}')

    def _poll_i4(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        kv     = []
        mirror = {}
        try:
            for i in range(4):
                resp = self._rget(f"http://{ip}/rpc/Input.GetStatus?id={i}")
                resp.raise_for_status()
                val = bool(resp.json().get("state", False))
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
            self.logger.warning(f'[{dev.name}] i4 poll error: {exc}')

    def _poll_em(self, dev):
        ip        = dev.pluginProps.get("ip_address", "").strip()
        is_3phase = dev.pluginProps.get("is_3phase", False)
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/EM.GetStatus?id=0")
            resp.raise_for_status()
            data = resp.json()

            if is_3phase:
                va  = float(data.get("a_voltage",   0.0))
                ia  = float(data.get("a_current",   0.0))
                pa  = float(data.get("a_act_power", 0.0))
                vb  = float(data.get("b_voltage",   0.0))
                ib  = float(data.get("b_current",   0.0))
                pb  = float(data.get("b_act_power", 0.0))
                vc  = float(data.get("c_voltage",   0.0))
                ic  = float(data.get("c_current",   0.0))
                pc  = float(data.get("c_act_power", 0.0))
                tot = float(data.get("total_act_power", pa + pb + pc))
            else:
                va  = float(data.get("voltage",   0.0))
                ia  = float(data.get("current",   0.0))
                pa  = float(data.get("act_power", 0.0))
                vb  = ib = pb = vc = ic = pc = 0.0
                tot = pa

            total_wh = 0.0
            try:
                er = self._rget(f"http://{ip}/rpc/EMData.GetStatus?id=0")
                if er.status_code == 200:
                    total_wh = float((er.json() or {}).get("total_act_energy", 0.0))
            except Exception:
                pass

            today_kwh, month_kwh       = self._calc_energy(dev.id, total_wh)

            kv = [
                {"key": "sensorValue",       "value": round(tot, 1), "uiValue": f"{tot:.1f} W"},
                {"key": "voltage_a",         "value": va,  "uiValue": f"{va:.1f} V"},
                {"key": "current_a",         "value": ia,  "uiValue": f"{ia:.3f} A"},
                {"key": "power_a",           "value": pa,  "uiValue": f"{pa:.1f} W"},
                {"key": "voltage_b",         "value": vb,  "uiValue": f"{vb:.1f} V"},
                {"key": "current_b",         "value": ib,  "uiValue": f"{ib:.3f} A"},
                {"key": "power_b",           "value": pb,  "uiValue": f"{pb:.1f} W"},
                {"key": "voltage_c",         "value": vc,  "uiValue": f"{vc:.1f} V"},
                {"key": "current_c",         "value": ic,  "uiValue": f"{ic:.3f} A"},
                {"key": "power_c",           "value": pc,  "uiValue": f"{pc:.1f} W"},
                {"key": "energy_kwh_today",  "value": round(today_kwh, 4),
                 "uiValue": f"{today_kwh:.3f} kWh"},
                {"key": "energy_kwh_month",  "value": round(month_kwh, 4),
                 "uiValue": f"{month_kwh:.3f} kWh"},
            ]
            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, {
                "watts":     f"{tot:.1f}",
                "kwh_today": f"{today_kwh:.4f}",
            })
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] EM poll error: {exc}')

    def _poll_rgbw(self, dev):
        ip = dev.pluginProps.get("ip_address", "").strip()
        if not ip:
            return
        try:
            resp = self._rget(f"http://{ip}/rpc/Light.GetStatus?id=0")
            resp.raise_for_status()
            data       = resp.json()
            on_state   = bool(data.get("output", False))
            brightness = int(data.get("brightness", 0))
            mode       = data.get("mode", "color")
            rgb        = data.get("rgb",  [0, 0, 0])
            white      = int(data.get("white",  0))
            watts      = float(data.get("apower", 0.0))

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
                {"key": "power_watts",     "value": watts,
                 "uiValue": f"{watts:.1f} W"},
            ]
            dev.updateStatesOnServer(kv)
            self._mirror_states(dev, {"on": str(on_state), "brightness": str(brightness)})
            self._mark_online(dev)
            self.last_polled[dev.id] = time.time()

        except requests.exceptions.ConnectionError:
            self._poll_failed(dev, f"no route to {ip}")
        except requests.exceptions.Timeout:
            self._poll_failed(dev, f"timed out ({ip})")
        except Exception as exc:
            self.logger.warning(f'[{dev.name}] RGBW poll error: {exc}')

    # ---------------------------------------------------------------------------
    # RPC helpers
    # ---------------------------------------------------------------------------

    def _rget(self, url, params=None, timeout=None):
        """Wrapper around requests.get() with optional digest auth support."""
        t    = timeout if timeout is not None else self.timeout
        auth = (HTTPDigestAuth(self.shelly_user, self.shelly_pass)
                if self.shelly_user and self.shelly_pass else None)
        return requests.get(url, params=params, timeout=t, auth=auth)

    def _set_output(self, dev, ip, on):
        """Dispatch on/off to the correct RPC component for this device type."""
        chan = int(dev.pluginProps.get("channel_id", 0))
        if dev.deviceTypeId in LIGHT_TYPES:
            return self._light_set(ip, chan, on=on)
        return self._switch_set(ip, chan, on, dev.name)

    def _switch_set(self, ip, channel_id, on, dev_name=""):
        on_str = "true" if on else "false"
        try:
            resp = self._rget(f"http://{ip}/rpc/Switch.Set?id={channel_id}&on={on_str}")
            resp.raise_for_status()
            return True
        except requests.exceptions.ConnectionError:
            self.logger.error(f'[{dev_name}] No route to {ip}')
        except requests.exceptions.Timeout:
            self.logger.error(f'[{dev_name}] Timed out ({ip})')
        except Exception as exc:
            self.logger.error(f'[{dev_name}] Command failed: {exc}')
        return False

    def _light_set(self, ip, channel_id, on, brightness=None):
        try:
            params = {"id": channel_id, "on": "true" if on else "false"}
            if brightness is not None:
                params["brightness"] = brightness
            resp = self._rget(f"http://{ip}/rpc/Light.Set", params=params)
            resp.raise_for_status()
            return True
        except Exception as exc:
            self.logger.error(f'Light.Set failed ({ip}): {exc}')
            return False

    def _cover_cmd(self, dev_id, rpc_method):
        try:
            dev = indigo.devices[dev_id]
            ip  = dev.pluginProps.get("ip_address", "").strip()
            if not ip:
                return
            resp = self._rget(f"http://{ip}/rpc/{rpc_method}?id=0")
            resp.raise_for_status()
            self.logger.info(f'[{dev.name}] {rpc_method}')
            self.last_polled[dev_id] = 0   # Trigger immediate poll on next tick
        except Exception as exc:
            self.logger.error(f'[{dev_id}] {rpc_method} failed: {exc}')

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
        if not dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", True)
            self.logger.info(f'[{dev.name}] back online')

    def _poll_failed(self, dev, reason=""):
        """Increment consecutive failure counter; only mark offline after 3 failures."""
        count = self.fail_count.get(dev.id, 0) + 1
        self.fail_count[dev.id] = count
        if count >= 3:
            self._mark_offline(dev, reason)

    def _mark_offline(self, dev, reason=""):
        if dev.states.get("deviceOnline", True):
            dev.updateStateOnServer("deviceOnline", False)
            self.logger.warning(f'[{dev.name}] offline - {reason}')
            self._fire_trigger("deviceWentOffline", dev.id)

    def _check_online(self, dev, now):
        last = self.last_seen.get(dev.id, now)
        if (now - last) > (self.stale_minutes * 60):
            self._mark_offline(dev, f"no response for >{self.stale_minutes}m")

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
                with open(path) as f:
                    self.energy_data = json.load(f)
                self.logger.debug(f"Energy data loaded ({len(self.energy_data)} device(s))")
        except Exception as exc:
            self.logger.warning(f"Could not load energy data: {exc} - starting fresh")
            self.energy_data = {}

    def _save_energy_data(self):
        try:
            with open(self._energy_data_path(), "w") as f:
                json.dump(self.energy_data, f, indent=2)
        except Exception as exc:
            self.logger.warning(f"Could not save energy data: {exc}")

    def _calc_energy(self, dev_id, total_wh):
        key       = str(dev_id)
        today_str = str(date.today())
        month_str = today_str[:7]
        entry     = self.energy_data.get(key, {})

        if "day_baseline_wh" not in entry or total_wh < entry.get("day_baseline_wh", 0):
            entry["day_baseline_wh"] = total_wh
            entry["day_date"]        = today_str

        if "month_baseline_wh" not in entry or total_wh < entry.get("month_baseline_wh", 0):
            entry["month_baseline_wh"] = total_wh
            entry["month_date"]        = month_str

        self.energy_data[key] = entry
        today_kwh = max(0.0, (total_wh - entry["day_baseline_wh"])   / 1000.0)
        month_kwh = max(0.0, (total_wh - entry["month_baseline_wh"]) / 1000.0)
        return today_kwh, month_kwh

    def _midnight_reset(self, today_str):
        month_str = today_str[:7]
        self.logger.info(f"Date changed to {today_str} - resetting daily energy baselines")
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
                    er = self._rget(f"http://{ip}/rpc/EMData.GetStatus?id=0")
                    total_wh = float((er.json() or {}).get("total_act_energy", 0.0)) \
                               if er.status_code == 200 else 0.0
                else:
                    chan = int(dev.pluginProps.get("channel_id", 0))
                    sr   = self._rget(f"http://{ip}/rpc/Switch.GetStatus?id={chan}")
                    total_wh = float((sr.json().get("aenergy") or {}).get("total", 0.0)) \
                               if sr.status_code == 200 else 0.0

                key   = str(dev.id)
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
                    self.logger.info(f'[{dev.name}] Monthly baseline reset for {month_str}')
                self.energy_data[key] = entry

            except Exception as exc:
                self.logger.warning(f'[{dev.name}] Midnight reset failed: {exc}')

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
        self.logger.info(f"Created variable folder: {VAR_FOLDER}")
        self.var_folder_id = folder.id
        return folder.id

    def _get_or_create_var(self, name, folder_id, value=""):
        """Update variable if it exists, create it in ShellyDirect folder if not."""
        # Variable names must not have spaces or special chars (CLAUDE.md rule)
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", name)
        try:
            var = indigo.variables[safe_name]
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
            self.logger.warning(f'[{dev.name}] Variable mirror failed: {exc}')

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
            self.logger.warning(
                f'[{dev.name}] High power alert: {watts:.1f} W exceeds {threshold:.0f} W threshold'
            )
            self._fire_trigger("highPowerAlert", dev.id)

        elif watts <= threshold and was_alerting:
            self.power_alert_active[dev.id] = False
            self.logger.info(f'[{dev.name}] Power back within threshold: {watts:.1f} W')

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
                self.logger.warning(f'Trigger execute failed ({type_id}): {exc}')

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
        """Dynamic list of devices with power monitoring."""
        result = [("any", "Any Device")]
        for dev in sorted(indigo.devices.iter("self"), key=lambda d: d.name):
            if dev.pluginProps.get("has_pm", False):
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
        self.logger.info(f"Created device folder: {folder_name}")
        return folder.id

    def _existing_device_ips(self):
        ips = set()
        for dev in indigo.devices.iter("self"):
            ip = dev.pluginProps.get("ip_address", "").strip()
            if ip:
                ips.add(ip)
        return ips

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
        """Return True if this device is configured in cover mode."""
        try:
            resp = self._rget(f"http://{ip}/rpc/Cover.GetStatus?id=0", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                return "state" in data
        except Exception:
            pass
        return False

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
            self.logger.error(f"[Discovery] Could not create device for {ip}: {exc}")
            return None

    def _discover_thread(self, subnet):
        found        = []
        created      = []
        skipped      = []
        existing_ips = self._existing_device_ips()
        folder_id    = self._get_or_create_device_folder()

        for i in range(1, 255):
            ip = f"{subnet}.{i}"
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
                    label, has_pm, base_type, num_ch = model, False, "shellyRelay", 1

                found.append(ip)

                if ip in existing_ips:
                    self.logger.info(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} -- already configured"
                    )
                    skipped.append(ip)
                    continue

                # Multi-channel: check for cover mode first
                if num_ch > 1 and base_type == "shellyRelay":
                    if self._is_cover_mode(ip):
                        dev_name = self._build_device_name(name, label + " Cover", ip)
                        new_dev  = self._create_device(
                            ip, "shellyCover", False, dev_name, folder_id,
                            {"poll_interval": "10"}
                        )
                        if new_dev:
                            created.append(new_dev.name)
                            self.logger.info(
                                f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                                f"-- created '{new_dev.name}' (cover mode)"
                            )
                        continue

                    # Create N relay devices, one per channel
                    for ch in range(num_ch):
                        suffix   = f" Ch{ch + 1}"
                        dev_name = self._build_device_name(name, label, ip, suffix)
                        new_dev  = self._create_device(
                            ip, base_type, has_pm, dev_name, folder_id,
                            {"channel_id": str(ch)}
                        )
                        if new_dev:
                            created.append(new_dev.name)
                    self.logger.info(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                        f"-- created {num_ch} channel device(s)"
                    )
                    continue

                # Single device
                dev_name = self._build_device_name(name, label, ip)
                extra    = {}
                if base_type == "shellyEM":
                    extra["is_3phase"] = (num_ch == 3)
                if base_type == "shellyCover":
                    extra["poll_interval"] = "10"

                new_dev = self._create_device(ip, base_type, has_pm, dev_name, folder_id, extra)
                if new_dev:
                    created.append(new_dev.name)
                    pm_str = "PM" if has_pm else "no PM"
                    self.logger.info(
                        f"[Discovery] {ip:<18} gen={gen}  {label:<22} "
                        f"name={name or '(none)'}  mac={mac}  ({pm_str})  "
                        f"-- created '{new_dev.name}'"
                    )

            except Exception:
                pass

        total = len(found)
        if total == 0:
            self.logger.info(f"Discovery complete: no Shelly devices found on {subnet}.0/24")
        else:
            self.logger.info(
                f"Discovery complete: {total} found  |  "
                f"{len(created)} created  |  {len(skipped)} already configured"
            )
            for n in created:
                self.logger.info(f"  [+] {n}")

    # ---------------------------------------------------------------------------
    # Menu handlers
    # ---------------------------------------------------------------------------

    def showPluginInfo(self, valuesDict=None, typeId=None):
        if log_startup_banner:
            log_startup_banner(self.pluginId, self.pluginDisplayName, self.pluginVersion, extras=[
                ("Webhook Port:",      str(WEBHOOK_PORT)),
                ("Discovery Subnets:", self.subnets_raw),
                ("Auth Enabled:",      "Yes" if self.shelly_user else "No"),
                ("Firmware Notify:",   "Yes" if self.firmware_notify else "No"),
            ])
        else:
            indigo.server.log(f"{self.pluginDisplayName} v{self.pluginVersion}")
