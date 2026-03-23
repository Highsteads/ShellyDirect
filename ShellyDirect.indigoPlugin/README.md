# ShellyDirect — Indigo Plugin

**Version:** 2.2
**Platform:** Indigo 2025.1 (macOS, Python 3.11)
**Author:** CliveS & Claude Sonnet 4.6
**Shelly compatibility:** Gen 2, Gen 3, Gen 4 (RPC HTTP API)

Direct local-network control of Shelly smart home devices from [Indigo](https://www.indigodomo.com/) — no cloud, no MQTT, no middleman. Uses each device's built-in RPC HTTP API over your LAN.

---

## Supported Device Types

| Indigo Device Type | Shelly Models |
|--------------------|---------------|
| **Shelly Relay** | Plus Plug UK/S/IT/US, Plug UK Gen 4, Plug S Gen 3, 1/1PM/Mini Gen 3/4, Pro 1/1PM Gen 3, Plus 2PM (2×), Pro 4PM (4×) |
| **Shelly Cover** | Plus 2PM in cover mode, Pro 2PM in cover mode |
| **Shelly Dimmer** | Plus Dimmer 0/1-10V, Wall Dimmer, Pro Dimmer 1PM/2PM |
| **Shelly RGBW** | Plus RGBW PM |
| **Shelly Energy Meter** | Pro EM, Pro 3EM, Pro 3EM-400, 3EM Gen 3 |
| **Shelly Uni** | Plus Uni |
| **Shelly i4** | Plus i4, Plus i4 DC |
| **Shelly H&T** | Plus H&T, Plus H&T Gen 3 |
| **Shelly Smoke** | Plus Smoke |
| **Shelly Flood** | Plus Flood |

---

## Features

### Control
- Standard Indigo on/off/toggle for relays, dimmers, covers, and RGBW lights
- **Relay:** turn on/off, toggle, "Turn On For N Seconds" (timed relay — ideal for garage door triggers)
- **Cover:** open, close, stop, go to position (0–100%), set tilt angle (venetian blinds)
- **Dimmer:** full brightness control via Indigo dim/brighten actions
- **RGBW:** set individual R/G/B/W channels + brightness; built-in animated effects (meteor shower, gradual change, flash, etc.)
- Lock-Off mode: prevents relay being turned off via Indigo (useful for always-on devices)

### State Monitoring
- Real-time polling at configurable intervals (10 / 30 / 60 / 120 seconds per device)
- **Webhook push updates** — state changes from physical button presses or the Shelly app reach Indigo in under 1 second; polling continues as fallback
- **Auto-heal webhooks** — if devices are deleted and recreated (new Indigo IDs), stale webhooks are detected and replaced automatically on next event
- Online / offline tracking with configurable stale timeout (5–60 minutes)
- Temperature add-on support (DS18B20 probe on Plus Add-on)

### Energy Monitoring (PM devices)
- Real-time watts, daily kWh, monthly kWh
- Configurable energy rate with flexible currency display:
  - **Disabled** — kWh states only
  - **Fixed rate** — enter your rate per kWh
  - **Indigo variable** — reads a live variable (e.g. `elec_unit_rate_p` from OctopusAccountReader for dynamic Tracker/Agile tariffs)
  - Currency display: prefix (`$`, `EUR`) or suffix (`p`, `c`) — configurable independently
- 30-day rolling energy history (exported to CSV via menu)

### Discovery
- **Discover Shelly Devices** menu — scans one or more subnets (e.g. `192.168.4`) and creates Indigo devices automatically
- Multi-subnet support: comma-separated (e.g. `192.168.4, 10.0.1`)

### Triggers (Custom Events)
| Event | Description |
|-------|-------------|
| **Button Input Pressed** | Fires on physical button press — filter by device, input 0–3, and press type (single / double / long) |
| **Device Went Offline** | Fires when a device stops responding — filter by device or match all |
| **High Power Alert** | Fires when a PM device exceeds a per-device wattage threshold |

### Variable Mirroring
- Per-device option to mirror key states to Indigo variables in the `ShellyDirect` folder
- Variable names are auto-generated from device name (safe characters only)

### Other
- Optional Digest Auth: single username/password applied to all devices
- Daily firmware update notifications via Indigo event log (and Pushover if installed)
- Device Health Summary menu: one-line status table with firmware version, last-seen age, online status
- Webhook Health Check: automatic 6-hourly verification that webhooks are registered on all devices

---

## Requirements

- Indigo 2025.1 or later
- Python 3.11 (bundled with Indigo)
- `requests` library (included with Indigo's Python)
- Shelly Gen 2 / Gen 3 / Gen 4 devices with firmware ≥ 1.0
- Devices must be on a subnet reachable from the Indigo Mac

---

## Installation

1. Download the latest release zip from the [Releases](https://github.com/Highsteads/ShellyDirect/releases) page
2. Unzip — you should see `ShellyDirect.indigoPlugin` alongside `README.md`
3. Double-click `ShellyDirect.indigoPlugin` to install into Indigo
4. Configure the plugin: **Plugins → Shelly Direct → Configure**
   - Set **Indigo Server IP** (the IP Shelly devices use to reach Indigo — usually your Mac's LAN IP)
   - Set **Discovery Subnets** (the subnet(s) your Shelly devices are on)
5. Discover devices: **Plugins → Shelly Direct → Discover Shelly Devices**

---

## Device Setup

Each device stores its own IP address in its config. To create a device manually:

1. **Devices → New Device → Type: Plugin → Shelly Direct**
2. Select the device type matching your hardware
3. Enter the Shelly's local IP address and (for multi-channel devices) the channel number
4. Save — the plugin polls the device immediately and registers webhooks

For the Plus 2PM and Pro 4PM, create one Indigo device per channel (select Channel 0 for Ch 1, Channel 1 for Ch 2, etc.).

---

## Energy Cost Configuration

Open **Plugins → Shelly Direct → Configure** and scroll to **Energy Rate Source**:

| Setting | Use case |
|---------|----------|
| Disabled | Track kWh only, no cost calculation |
| Fixed Rate | Enter a fixed rate (e.g. `24.5` with suffix `p` for UK pence) |
| Indigo Variable | Point to any variable holding the current rate per kWh |

**Currency display examples:**
- UK pence: prefix blank, suffix `p` → displays as `12.3p`
- US dollars: prefix `$`, suffix blank → displays as `$0.12`
- Euros: prefix `EUR`, suffix blank → displays as `EUR0.28`

**OctopusAccountReader integration:** If you have the OctopusAccountReader plugin installed, set Rate Source to **Indigo Variable** and leave the variable name as `elec_unit_rate_p`. OctopusAccountReader updates this variable daily with the current Octopus Tracker rate, giving you automatic dynamic pricing.

---

## Webhook Port

The plugin uses its own HTTP listener on port **8178**. This avoids Digest Authentication issues with Indigo's built-in IWS server. Make sure port 8178 is not blocked by any firewall between your Shelly devices and the Indigo Mac.

---

## Garage Door Usage

For a Shelly device controlling a garage door momentary switch:

1. Create a **Shelly Relay** device for the Shelly controlling the door
2. In an Action Group, add **Shelly Direct → Advanced → Turn On For N Seconds**
3. Set seconds to `1` — the relay closes for 1 second then opens automatically (handled on-device)

---

## File Structure

```
ShellyDirect.indigoPlugin/
    README.md
    Contents/
        Info.plist
        Server Plugin/
            plugin.py          # Main plugin
            Devices.xml        # 10 device type definitions
            Actions.xml        # Custom actions (timed on, cover, dimmer, RGBW)
            Events.xml         # 3 custom trigger events
            MenuItems.xml      # Discovery, health, firmware, webhooks, CSV export
            PluginConfig.xml   # Plugin preferences
            test_plugin.py     # 74 unit tests (run without Indigo)
```

---

## Running Tests

```bash
cd "ShellyDirect.indigoPlugin/Contents/Server Plugin"
python3 test_plugin.py
```

74 tests covering: constants, subnet/IP validation, energy cost calculations, energy baseline arithmetic, trigger filtering, stale webhook detection, variable name sanitisation, and multi-subnet parsing.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 2026 | Initial release: relay, cover, dimmer, RGBW, EM, webhooks, discovery |
| 2.0 | Mar 2026 | International currency support, Digest Auth, multi-subnet discovery, cover tilt, RGBW effects, power alerts, variable mirroring, firmware notify, trigger events, 30-day energy history, device health summary, CSV export |
| 2.1 | Mar 2026 | Fixed Actions.xml deviceFilter (dot notation); fixed stale state migration on reload |
| 2.2 | Mar 2026 | Fixed stale webhook detection (path-only match catches any old device ID); auto-reconfigure webhooks on stale devId; stale deletion logged at INFO level |

---

## Licence

MIT — free to use, modify, and distribute. Attribution appreciated.
