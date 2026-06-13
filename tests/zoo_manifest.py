#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Filename:    zoo_manifest.py
# Description: The Shelly "device zoo" — a declarative contract table mapping a
#              Shelly's self-description (Shelly.GetDeviceInfo + GetConfig
#              component keys) to the Indigo device(s) the classifier
#              `detect_shelly_devices` must produce, ONE PER CHANNEL. Driven by
#              test_zoo.py (per-case contract + cross-cutting invariants).
#
#              This is the testable core of a future "Discover & Create Shelly
#              Devices" menu: a Shelly Gen2+ device self-describes over RPC every
#              bit as richly as a zigbee2mqtt device does via `exposes`, so the
#              user need never tell Indigo what type it is.
#
#              REAL captures (real=True) come from CliveS's live fleet via
#              `curl http://<ip>/rpc/Shelly.GetDeviceInfo` + `.../Shelly.GetConfig`
#              (stored in tests/zoo_real/). The estate is all relays, so the
#              non-relay classes (dimmer/RGBW/cover/EM/i4/H&T) are SYNTHETIC,
#              modelled on the documented Shelly app names + component shapes.
# Author:      CliveS & Claude Opus 4.8
# Date:        13-06-2026
# Version:     1.0

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShellyCase:
    """One zoo animal: a Shelly self-description and the Indigo devices it must
    map to. ``expect`` is a list of (device_type_id, channel) — one per channel,
    in order — the COMPLETE set the classifier must emit (exact match)."""
    name:         str
    device_info:  dict
    config_keys:  list
    expect:       list                      # [(device_type_id, channel), ...]
    real:         bool = False
    note:         str = ""


_REAL_DIR = os.path.join(os.path.dirname(__file__), "zoo_real")


def _real(stem, expect, note=""):
    with open(os.path.join(_REAL_DIR, f"{stem}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return ShellyCase(f"real_{stem}", d["device_info"], d["config_keys"],
                      expect, real=True, note=note)


def _syn(name, app, keys, expect, note=""):
    return ShellyCase(name, {"app": app}, keys, expect, note=note)


CASES: list[ShellyCase] = [
    # ── Real captures from the live fleet ────────────────────────────────────
    _real("relay_plug_pluspluguk", [("shellyRelay", 0)],
          note="Shelly Plus Plug UK — app in APP_INFO (primary path)"),
    _real("relay_garage_mini1g4", [("shellyRelay", 0)],
          note="Shelly 1 Mini Gen 4 — app NOT in APP_INFO, classified from "
               "switch:0 via the fallback (the valuable real case)"),

    # ── Synthetic: app-table hits (primary path coverage) ────────────────────
    _syn("syn_dimmer", "PlusDimmerUL", ["light:0", "sys"],
         [("shellyDimmer", 0)], note="dimmer via APP_INFO"),
    _syn("syn_rgbw", "PlusRGBWPM", ["rgb:0", "sys"],
         [("shellyRGBW", 0)], note="RGBW via APP_INFO"),
    _syn("syn_2pm", "Plus2PM", ["switch:0", "switch:1", "sys"],
         [("shellyRelay", 0), ("shellyRelay", 1)],
         note="2-channel relay -> two Indigo devices (one per channel)"),
    _syn("syn_pro4pm", "Pro4PM", ["switch:0", "switch:1", "switch:2", "switch:3"],
         [("shellyRelay", 0), ("shellyRelay", 1), ("shellyRelay", 2), ("shellyRelay", 3)],
         note="4-channel relay -> four devices"),
    _syn("syn_3em", "Pro3EM", ["em:0", "sys"],
         [("shellyEM", 0), ("shellyEM", 1), ("shellyEM", 2)],
         note="3-phase EM: APP_INFO says 3 channels"),
    _syn("syn_i4", "PlusI4", ["input:0", "input:1", "input:2", "input:3"],
         [("shellyI4", 0)], note="i4 input device via APP_INFO"),
    _syn("syn_ht", "PlusHT", ["temperature:0", "humidity:0"],
         [("shellyHT", 0)], note="battery H&T sensor via APP_INFO"),

    # ── Synthetic: fallback (unknown app, classify from components) ───────────
    _syn("fb_cover", "NewRollerX", ["cover:0", "sys"],
         [("shellyCover", 0)], note="unknown app, cover:0 -> cover"),
    _syn("fb_dimmer", "NewDimmerX", ["light:0"],
         [("shellyDimmer", 0)], note="unknown app, light:0 -> dimmer"),
    _syn("fb_rgb", "NewRGBX", ["rgb:0"],
         [("shellyRGBW", 0)], note="unknown app, rgb:0 -> RGBW"),
    _syn("fb_2switch", "NewDual", ["switch:0", "switch:1"],
         [("shellyRelay", 0), ("shellyRelay", 1)],
         note="unknown app, two switches -> two relays"),
    _syn("fb_priority", "NewCoverPM", ["cover:0", "switch:0", "pm1:0"],
         [("shellyCover", 0)],
         note="cover wins over the underlying switch (priority)"),
    _syn("fb_nothing", "NewSensorOnly", ["sys", "ble", "cloud"],
         [], note="no controllable component -> empty (discovery skips)"),
]
