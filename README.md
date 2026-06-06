# ShellyDirect — Indigo Plugin

Direct local-network control of Shelly Gen 2/3/4 smart home devices from [Indigo](https://www.indigodomo.com/). No cloud, no MQTT.

**Version:** 3.7 | **Author:** CliveS & Claude Opus 4.8 | **Platform:** Indigo 2022.1 or later

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*

## Recent changes

- **v3.7** — energy accounting is now thread-safe, the nightly baseline reset survives a restart that happens to straddle midnight, and the webhook listener has a sensible cap on the request body it will read. The High Power Alert trigger only offers devices that can actually raise it.
- **v3.6** — a more robust energy meter. If a Shelly returns a poll that is missing its cumulative energy reading (which can happen mid-reboot or under load), the plugin now keeps the last good figure rather than briefly reading it as zero, so the day's and month's kWh totals no longer get a phantom spike. The polling loop has also been hardened so a single misbehaving device can no longer stall it, and a device that keeps returning rubbish is marked offline rather than left looking healthy.
- **v3.5** — sensor devices (H&T, Smoke, Flood, i4, EM, BLU buttons) now respond to a Send Status Request action.

## Installation

1. Go to the [Releases](https://github.com/Highsteads/ShellyDirect/releases) page and download `ShellyDirect.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `ShellyDirect.indigoPlugin`
3. Double-click `ShellyDirect.indigoPlugin` — Indigo will install it automatically

## Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`

This plugin (along with all CliveS Indigo plugins) reads sensitive values from
a shared master credentials file at:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you do not have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` from
the plugin bundle to that location and fill in your values. Or skip
`IndigoSecrets.py` entirely and enter values via the plugin's configuration
dialog — `IndigoSecrets.py` wins over the dialog when both are set.

If a required value is set in NEITHER source the plugin logs an ERROR
pointing the user to either fill in the matching field or add the key to
`IndigoSecrets.py`.

**Note for this plugin specifically**: Shelly Direct talks to devices on the
local network with no cloud auth — the only credentials it might use are
optional Digest Auth username/password for Shelly devices that have a
password set. These can be entered via **Plugins → Shelly Direct →
Configure** or added to `IndigoSecrets.py` if you prefer.

**Keys read by ShellyDirect** *(v3.3+)*:

```python
INDIGO_SERVER_IP         = "192.168.x.x"   # IP Shelly devices use for webhook callbacks
SHELLY_USERNAME          = ""              # optional — only if your Shellies have auth set
SHELLY_PASSWORD          = ""              # optional — paired with SHELLY_USERNAME
SHELLY_DISCOVERY_SUBNETS = "192.168.x"     # first three octets, comma-separate for multi-subnet
```

All four are read from `IndigoSecrets.py` first, then PluginConfig as a
fallback. The plugin has **no built-in default discovery subnet** — set
one in either source or device discovery is skipped (the rest of the
plugin keeps working).

## Logging

Every log line is prefixed with a millisecond timestamp `[HH:MM:SS.mmm]` so
events can be correlated tightly with other CliveS plugins (Device Activity
Monitor uses the same convention).

To turn the prefix off (or back on) at any time:

**Plugins → Shelly Direct → Toggle Timestamps in Log (on/off)**

The setting is stored in `pluginPrefs` (`timestampEnabled`) and persists across
restarts. Defaults to ON.
