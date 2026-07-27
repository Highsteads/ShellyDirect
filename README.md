# ShellyDirect — Indigo Plugin

Direct local-network control of Shelly Gen 2/3/4 smart home devices from [Indigo](https://www.indigodomo.com/). No cloud, no MQTT — the plugin talks to each Shelly straight over your LAN, and the Shellys push their state changes back to Indigo over a small built-in webhook listener.

**Version:** 3.16.0 | **Author:** CliveS & Claude | **Platform:** Indigo 2022.1 or later

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*

---

## Contents

- [Recent changes](#recent-changes)
- [What it does](#what-it-does)
- [Supported devices](#supported-devices)
- [Installation](#installation)
- [First-time setup](#first-time-setup)
- [Adding your Shelly devices](#adding-your-shelly-devices)
- [How it works — webhooks and polling](#how-it-works--webhooks-and-polling)
- [Device actions](#device-actions)
- [Triggers (events)](#triggers-events)
- [Energy tracking](#energy-tracking)
- [BLU Bluetooth buttons](#blu-bluetooth-buttons)
- [Plugin menu](#plugin-menu)
- [Device states reference](#device-states-reference)
- [Credentials — `IndigoSecrets.py`](#credentials--indigosecretspy)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)
- [Licence](#licence)

---

## Recent changes

- **v3.16.2** — closes a second way a day's energy reading could jump to an impossible number. Version 3.16.0 fixed one cause of that, where two Indigo devices ended up polling the same physical plug. This is a different route to the same result, and it was still open. A Shelly reports the energy it has used since it was made, and the plugin works out today's figure by subtracting what the meter read at midnight. If the reading ever comes back lower than that, the plugin assumed the device had been reset and started counting afresh from the new number — sensible, until a device reports zero for a single poll by mistake. The plugin believed it, started counting from nothing, and the next reading a few seconds later became the device's entire lifetime total presented as one day's use. It now waits for a second low reading before believing it: a device that has genuinely been reset stays low, a momentary glitch does not, and in the meantime the last good figure is kept rather than a made-up zero. A related fix: a device that has been off the network for weeks no longer files all the energy it accumulated while away as though it happened in a single day. Tests: 232 to 237.
- **v3.16.0** — a device is now identified by its MAC address, not by its IP. Until now the plugin used the stored address for two different jobs: how to reach a device, and which device it is. That works right up to the day an address gets handed to something else — and when it happened here, two Indigo devices ended up polling the same physical plug and one of them recorded 3,446 kWh for a single day. Every device now proves who it is before anything is written to it: the plugin asks for its MAC address and compares it with the one on record. If they disagree it records nothing at all, tells you once which MAC it found and where, and goes looking for the real device over mDNS — both the service Gen2 and later devices announce themselves on and the one older Gen1 devices use, since many houses have a mix. When it finds the device at a new address it updates the record itself and says so in one line. Devices that are simply switched off, like a washing-machine plug at the wall, stay as quiet as they always were and are picked up again the moment they come back, with no restart. Devices set up before MAC addresses were stored carry on working and learn theirs on the next successful check. Two smaller things came along with it: the device dialog now refuses an address that another device already uses, and the energy history file is tidied of entries belonging to devices deleted long ago. Tests: 199 to 226.
- **v3.12–v3.15** — a full review pass with fixes shipped in four sweeps, followed by some quality-of-life additions. The big ones first. Multi-channel Shellys (a Plus 2PM, a Pro 4PM) no longer have their channels quietly fighting each other — each channel used to tear down the other's webhooks in an endless loop that also defeated the v3.11 repair back-off, and discovery now creates every channel of a multi-channel dimmer or meter rather than just the first. Energy figures survive a device being unreachable at midnight instead of corrupting the whole day, energy meters use the correct API calls for their hardware family, and RGBW colour commands use the current Shelly API rather than a form the devices no longer accept. Partial replies from a busy device no longer produce phantom zero readings, battery sensors stop flapping offline between their hourly reports, a failed webhook registration is reported honestly instead of hiding behind *Webhooks OK*, and a settings save no longer forgets credentials kept in IndigoSecrets. New in v3.15: a **Test Shelly Connection** menu item that produces one log dump made for support posts, a configurable webhook port for anyone with a clash on 8178, discovery progress feedback plus a report of configured devices that did not answer, and a much lighter install — the plugin no longer bundles its own copy of a library Indigo already provides. The test suite grew from 185 to 199 with the phantom tests it uncovered removed.
- **v3.11** — fixes a Shelly that kept logging *Webhooks missing — repairing* every few hours. The cause turned out to be two Indigo device records that had ended up pointing at the same physical plug, each one quietly tearing down the other's webhooks and putting its own back, round and round forever. The plugin now notices when two records share a MAC address (or IP), keeps the original, leaves the duplicate well alone, and tells you in the log which one to delete. It also stops hammering away at a webhook it cannot get to land — after a few failed attempts on an unreachable device it settles into poll-only and goes quiet until that device next answers, instead of repeating the same noisy repair every cycle.
- **v3.10** — a quieter startup. Several of the sensor device types were declaring a state that Indigo already provides for them natively, so Indigo logged a harmless complaint about it every time the plugin loaded. That declaration has been removed, which clears the startup noise. Nothing about how the devices behave has changed.
- **v3.9** — smarter auto-discovery for unfamiliar models. Previously, any Shelly whose model name the plugin did not recognise was created as a plain single relay, which got the device type wrong for anything that was really a dimmer, roller cover, RGBW light or multi-channel unit. Discovery now inspects what the device actually reports it can do and creates the right Indigo device type and the right number of channels, so newer Shelly models work properly even before they have been added to the known-models list. Devices already set up, and models that were always recognised, are unaffected.
- **v3.8** — internal tidy-up only. Added automated code linting and a continuous-integration test gate so regressions are caught before release. No change to how the plugin behaves.
- **v3.7** — energy accounting is now thread-safe, the nightly baseline reset survives a restart that happens to straddle midnight, and the webhook listener has a sensible cap on the request body it will read. The High Power Alert trigger only offers devices that can actually raise it.
- **v3.6** — a more robust energy meter. If a Shelly returns a poll that is missing its cumulative energy reading (which can happen mid-reboot or under load), the plugin now keeps the last good figure rather than briefly reading it as zero, so the day's and month's kWh totals no longer get a phantom spike. The polling loop has also been hardened so a single misbehaving device can no longer stall it, and a device that keeps returning rubbish is marked offline rather than left looking healthy.
- **v3.5** — sensor devices (H&T, Smoke, Flood, i4, EM, BLU buttons) now respond to a Send Status Request action.

---

## What it does

ShellyDirect gives Indigo native devices for your Shelly hardware without any cloud account or MQTT broker in the middle. Each device is reached directly over the LAN using Shelly's local RPC interface, so control is fast and works even if your internet is down.

Headline features:

- **Relays, dimmers, RGBW lights, roller covers, energy meters, sensors and Bluetooth buttons** — all as proper Indigo device types with the right on/off, brightness, colour and status behaviour.
- **Auto-discovery** — scan your subnet and the plugin creates a device for everything it finds, picking the right type from the Shelly's own model name.
- **Webhook push** — Shellys push state changes to the plugin the instant they happen, so a switch flipped at the wall updates Indigo immediately rather than waiting for the next poll.
- **Identity by MAC address** — a device is known by its MAC, never by its IP. Before anything is written the plugin checks that the box answering on that address really is that device, and if the address has changed it finds the device again over mDNS and updates the record itself. Nothing is recorded against a device the plugin cannot positively identify.
- **Energy monitoring** — for power-metering devices, today/month kWh plus a rolling 30-day history and an optional high-power alert.
- **Digest Auth support** — for Shellys that have a password set.
- **Variable mirroring** — optionally mirror key states into Indigo variables for control pages and scripts.

---

## Supported devices

Discovery recognises a Shelly by the `app` name it reports and creates the matching Indigo device type. Anything not in the list below is still created as a basic relay so you are not stuck.

| Indigo device type | Shelly models (Gen 2/3/4) |
|--------------------|----------------------------|
| **Relay** (`shellyRelay`) | Plus Plug (UK/S/IT/US), Plug UK Gen 4, Plug S Gen 3, Plus 1 / 1PM, Pro 1 / 1PM, Pro 1 Gen 3 / 1PM Gen 3, 1 Mini Gen 3 / 1PM Mini Gen 3 (incl. DC), Shelly 1 Gen 4 / 1PM Gen 4 |
| **Relay, multi-channel** | Plus 2PM, Pro 2 / 2PM (2 channels), Pro 4PM (4 channels) — discovery creates one device per channel and probes for cover mode |
| **Cover / roller** (`shellyCover`) | Any 2-channel relay configured in cover mode (detected automatically) |
| **Dimmer** (`shellyDimmer`) | Plus Dimmer 0/1-10V, Wall Dimmer, Pro Dimmer 1PM / 2PM |
| **RGBW** (`shellyRGBW`) | Plus RGBW PM |
| **Energy meter** (`shellyEM`) | Pro EM, Pro 3EM, Pro 3EM-400, 3EM Gen 3 |
| **Universal** (`shellyUni`) | Plus Uni (two inputs, two voltmeters, one switch) |
| **Input** (`shellyI4`) | Plus i4, Plus i4 DC (four inputs) |
| **Temperature / Humidity** (`shellyHT`) | Plus H&T, Plus H&T Gen 3 |
| **Smoke** (`shellySmoke`) | Plus Smoke |
| **Flood** (`shellyFlood`) | Plus Flood |
| **BLU Button** (`shellyBluButton`) | Shelly BLU Button (via a Shelly Plus/Pro BLE gateway) |
| **BLU RC Button 4** (`shellyBluRC4`) | Shelly BLU RC Button 4 (via a BLE gateway) |

The H&T, Smoke and Flood sensors are battery devices that sleep between events, so they are push-only — they report when something changes rather than being polled.

---

## Installation

1. Go to the [Releases](https://github.com/Highsteads/ShellyDirect/releases) page and download `ShellyDirect.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `ShellyDirect.indigoPlugin`
3. Double-click `ShellyDirect.indigoPlugin` — Indigo will install it automatically

---

## First-time setup

Open **Plugins → Shelly Direct → Configure** and fill in:

| Setting | What it is for |
|---------|----------------|
| **Indigo Server IP** | The IP your Shelly devices use to reach Indigo for webhook callbacks. This is the address of the Mac running Indigo. |
| **Discovery Subnets** | The first three octets of each LAN to scan, comma-separated for more than one — for example `192.168.1` or `192.168.1, 10.0.1`. There is no built-in default, so set one here or device discovery is skipped. |
| **HTTP Request Timeout** | How long to wait for a Shelly to answer (2, 3, 5 or 10 seconds). 3 is a good default. |
| **Shelly Username / Password** | Optional. Only needed if your Shellys have authentication switched on. If set, Digest Auth is used on every request, and all devices must share the same credentials. |
| **Daily Firmware Update Notifications** | Check all devices once a day for available firmware and report them in the log (and via Pushover if you run the Pushover plugin). |
| **Offline Detection Threshold** | Mark a device offline if nothing is heard from it (poll or webhook) within this window. |
| **Log Level** | How chatty the log is, from Detailed Debugging down to Errors Only. |

Indigo Server IP and the Shelly credentials can also be read from a shared `IndigoSecrets.py` file — see [Credentials](#credentials--indigosecretspy) below.

---

## Adding your Shelly devices

**The easy way — discovery.** With your subnet(s) set in the config, choose **Plugins → Shelly Direct → Discover Shelly Devices**. The plugin scans every address from `.1` to `.254` on each subnet, identifies each Shelly from its model, and creates the right Indigo device in a "ShellyDirect" device folder. A multi-channel unit becomes one device per channel, and a 2-channel relay in cover mode becomes a cover device. If a device already exists (matched by MAC), discovery updates its IP rather than making a duplicate.

**The manual way.** Create a new device, pick Shelly Direct as the plugin, choose the device type, and enter the device's IP address. The per-device settings you may see, depending on type, are:

| Setting | Applies to | What it does |
|---------|-----------|--------------|
| **IP Address** | all | The Shelly's address on the LAN (or the BLE gateway's address for BLU devices). |
| **Channel** | relay, dimmer | Which output channel this device controls on a multi-channel unit. |
| **Has power metering** | relay, dimmer | Whether to read power/energy from this device. |
| **Add-on temperature probe** | relay | Read an external temperature probe on the relay's add-on. |
| **Lock off** | relay | Refuse Turn Off / Toggle-to-off commands (handy for things that must stay on). |
| **High Power Alert** | relay | Raise the High Power Alert trigger and log a warning when power crosses a wattage you set. |
| **Mirror to variable** | most | Copy this device's key states into Indigo variables in the "ShellyDirect" folder. |
| **Poll interval** | most | How often to poll, in seconds (covers and i4 default to a brisk 10s, others to 30s). |
| **Suppress offline alerts** | relay | Stop the offline warning and trigger for a device you know comes and goes. |
| **3-phase** | energy meter | Treat this EM as a three-phase meter and report all three phases. |
| **BTHome Device ID** | BLU button / RC4 | The bthome component id the BLE gateway uses for this button (an integer such as 200). |

---

## How it works — webhooks and polling

**Webhooks (push).** On startup, and whenever a device's IP changes, the plugin registers webhooks on each Shelly so the device pushes its state changes to Indigo. The plugin runs its own small HTTP listener for this on **port 8178** — that port must be reachable from your Shellys to the Indigo Mac. Using a dedicated port keeps the plugin clear of Indigo's own web server and its authentication.

If a Shelly is unreachable when the plugin tries to register its webhooks (for example a sleepy battery sensor, or a flaky link), it carries on in poll-only mode and tells you so in the log. A webhook health check runs every six hours and quietly repairs any that have gone missing, and if a stale webhook arrives from a device that has been deleted and recreated, the plugin matches it by source IP and re-registers it automatically.

**Polling (pull).** Alongside the push model, every non-battery device is polled on its configured interval as a backstop, so state stays correct even if a webhook is missed. If a device fails to answer three polls in a row it is marked offline and the Device Went Offline trigger fires (unless you have suppressed alerts for it).

**MAC-based identity.** Each device stores its MAC address. If your router hands it a new DHCP address, discovery spots the same MAC at the new IP and just updates the existing device — no duplicate, and webhooks are re-pointed automatically.

---

## Device actions

As well as the standard Indigo On / Off / Toggle / Set Brightness / Set Color actions (available straight from the device controls), the plugin adds these under the action's Advanced group:

| Action | Device type | What it does |
|--------|-------------|--------------|
| **Turn On For N Seconds** | relay | Turn on and switch off after N seconds, handled on the Shelly itself. Use 1 second for a garage-door style momentary pulse. |
| **Open Cover / Close Cover / Stop Cover** | cover | Drive a roller blind or shutter. |
| **Go To Position** | cover | Move to a position from 0 (closed) to 100 (open). |
| **Set Tilt Angle** | cover | Set venetian-blind slat angle, 0 (closed) to 100 (open). |
| **Set Brightness** | dimmer | Set brightness 0-100. |
| **Set RGBW Color** | RGBW | Set red, green, blue, white (0-255 each) and brightness (0-100). |
| **Set Light Effect** | RGBW | Run a built-in effect (Meteor shower, Gradual change, Flash, and so on), or Static to cancel one. |

---

## Triggers (events)

| Trigger | Fires when | Filters |
|---------|-----------|---------|
| **Button Input Pressed** | A wired button on a relay (input 0), Uni (inputs 0-1) or i4 (inputs 0-3) is pressed | Device, input number, and press type (single / double / long) |
| **BLU Button Pressed** | A Shelly BLU Button or BLU RC Button 4 is pressed | Device, press type (single / double / triple / long), and button 1-4 (RC4 only) |
| **Device Went Offline** | A device stops responding to polls or webhooks | Device |
| **High Power Alert** | A power-metering relay crosses its configured wattage (rising edge only, resets when power drops back) | Device |

---

## Energy tracking

Power-metering relays and energy meters report **power (W)** and accumulate **today's** and **this month's kWh**. The plugin works these out from the Shelly's own lifetime counter, handles a counter reset after a power cut, and rolls a **30-day per-day history** that you can export.

- **Export Energy History to CSV** (plugin menu) writes a dated file to `~/Documents/Indigo/ShellyDirect/` with one row per device per day.
- **High Power Alert** — set a wattage threshold per relay and the plugin logs a warning and fires the trigger when power crosses it, then resets when power falls back below.

A note on accuracy (v3.6): if a poll comes back without its cumulative energy figure — which Shellys occasionally do mid-reboot or under load — the plugin keeps the last good reading rather than treating the gap as a zero, so your daily and monthly totals do not get a false spike.

---

## BLU Bluetooth buttons

Shelly BLU buttons have no IP of their own — they reach Indigo through a mains-powered Shelly Plus or Pro acting as a Bluetooth gateway. To add one:

1. In the Shelly app, pair the BLU button with a Plus/Pro device so that device becomes its BLE gateway, and note the bthome component id it is given (an integer such as 200, 201, 202).
2. In Indigo, create a BLU Button or BLU RC Button 4 device, set its **IP Address** to the **gateway's** address, and set **BTHome Device ID** to that component id.

The plugin registers press-event webhooks on the gateway, and presses arrive as the BLU Button Pressed trigger. The RC Button 4 reports which of its four buttons was pressed and also supports triple-press.

---

## Plugin menu

**Plugins → Shelly Direct →**

| Menu item | What it does |
|-----------|--------------|
| **Discover Shelly Devices** | Scan the configured subnet(s) and create any new devices found. |
| **Show mDNS Discovered Shellys** | List every Shelly announcing itself on the network, its MAC and current address, and the Indigo device it matches — the quickest way to spot a device whose stored address has gone stale. |
| **Device Health Summary** | Log a table of every device — IP, type, online state, firmware, and when it was last heard from. |
| **Check Firmware Versions** | Ask every device whether a firmware update is available and log the result. |
| **Reconfigure Webhooks (All Devices)** | Re-register webhooks on every device — useful after network changes. |
| **Export Energy History to CSV** | Write the 30-day energy history to a CSV file. |
| **Toggle Timestamps in Log (on/off)** | Turn the millisecond log prefix on or off. |
| **Show Plugin Info** | Log the full plugin/environment banner for support. |

---

## Device states reference

Useful states for triggers, control pages and scripts (states vary by device type):

- **All devices** — `deviceOnline`
- **Relay / dimmer / RGBW** — `onOffState`, `brightnessLevel` (dimmer/RGBW), `powerWatts`, `voltage`, `currentAmps`, `deviceTempC`, `energyKwhToday`, `energyKwhMonth`, and `addonTempC` if an add-on probe is fitted
- **RGBW** — `colorMode`, `redLevel`, `greenLevel`, `blueLevel`, `whiteLevel`
- **Cover** — `coverState`, `currentPosition`, `targetPosition`, `tiltCurrentPosition`, `tiltTargetPosition`, `obstructed`
- **Energy meter** — `sensorValue` (total W), plus per-phase `voltageA/B/C`, `currentA/B/C`, `powerA/B/C`, and `energyKwhToday` / `energyKwhMonth`
- **H&T** — `sensorValue` (temperature), `humidity`, `battery`
- **Smoke / Flood** — `sensorValue` (alarm/flood true-false), `battery`
- **Uni / i4** — `input0`-`input3`, and Uni adds `voltage0` / `voltage1`
- **BLU buttons** — `lastAction`, `pressCount`, `lastButton` (RC4), `battery`, `rssi`

Any extra field a Shelly returns that the plugin does not have a dedicated state for (power factor, frequency, Wi-Fi signal, uptime, and so on) is captured automatically as a dynamic state, so it is available without a plugin update.

---

## Credentials — `IndigoSecrets.py`

This plugin, like every CliveS Indigo plugin, can read sensitive values from one shared master file:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you don't have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` out of the plugin bundle into `/Library/Application Support/Perceptive Automation/`, rename it to `IndigoSecrets.py`, and fill in your values. Or skip the file altogether and type everything into the plugin's Configure dialog — where both are set, `IndigoSecrets.py` wins. If neither source supplies a value the plugin needs, it logs an ERROR naming the key to add or the field to fill in.

**Keys read by ShellyDirect**:

```python
INDIGO_SERVER_IP         = "192.168.x.x"   # IP Shelly devices use for webhook callbacks
SHELLY_USERNAME          = ""              # optional — only if your Shellys have auth set
SHELLY_PASSWORD          = ""              # optional — paired with SHELLY_USERNAME
SHELLY_DISCOVERY_SUBNETS = "192.168.x"     # first three octets, comma-separate for multi-subnet
```

All four are read from `IndigoSecrets.py` first, then from the plugin config as a fallback. There is no built-in default discovery subnet, so set one in either source or discovery is skipped (the rest of the plugin keeps working).

---

## Logging

Every log line carries a millisecond timestamp `[HH:MM:SS.mmm]`, so you can line events up precisely against the other CliveS plugins — Device Activity Monitor uses the same format.

To turn the prefix off, or back on, at any time:

**Plugins → Shelly Direct → Toggle Timestamps in Log (on/off)**

The plugin stores the setting in `pluginPrefs` (`timestampEnabled`) and it survives a restart. It defaults to ON.

---

## Troubleshooting

- **A device shows as offline but is on the network** — check the Indigo Mac can reach it (`ping` the IP), and that nothing else is holding port 8178. Run **Reconfigure Webhooks** and then **Device Health Summary** to see what the plugin is hearing.
- **A switch flipped at the wall is slow to update** — that is the webhook not arriving. Confirm port 8178 is reachable from the Shelly to the Indigo Mac, that the Indigo Server IP in the config is correct, and run Reconfigure Webhooks.
- **Discovery finds nothing** — make sure Discovery Subnets is set to the first three octets only (for example `192.168.1`, not `192.168.1.0`), and that the Shellys are on that subnet.
- **A battery sensor (H&T/Smoke/Flood) will not configure its webhook** — it is asleep. Wake it (press its button) and run Reconfigure Webhooks, or follow the manual URL the plugin logs.
- **Energy figures look wrong after a power cut** — the plugin re-baselines automatically on the next good reading. A single missing reading no longer causes a spike (v3.6).
- **For a support post**, run **Show Plugin Info** and paste the banner along with the relevant log lines.

## Authors & licence

Vibed into existence by **CliveS**, who knew what he wanted, argued until he got it, and tested it on a real house. Typed at inhuman speed by **Claude** (Anthropic), who mostly did as it was told.

© 2026 CliveS · [MIT licence](LICENSE) — copy it, fork it, bend it, break it, fix it, ship it. If it breaks, you get to keep both pieces.
