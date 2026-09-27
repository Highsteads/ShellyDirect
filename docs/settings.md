---
title: Settings
nav_order: 12
---

# Settings

## The plugin's settings

Open these with **Plugins → Shelly Direct → Configure**. They apply to every Shelly.

| Setting | What it does |
|---|---|
| **Indigo Server IP** | The network address of the Mac that runs Indigo, such as `192.168.1.5`. Your Shellys use it to send changes to Indigo. Without it the plugin does not set up any webhooks, and says so in the log. |
| **Discovery Subnets** | The first three numbers of your Shellys' addresses, such as `192.168.1`. Separate more than one with commas. Discovery tries every address from `.1` to `.254` in each. The dialog will not save without one, unless it is in the shared file described below. |
| **HTTP Request Timeout** | How long to wait for a Shelly to answer: 2, 3, 5 or 10 seconds. 3 seconds to start with. |
| **Shelly Username** and **Shelly Password** | Only needed if you have set a password on your Shellys. All of them must share the same one. While these are set, the live connection is not used. |
| **Webhook Listener Port** | The port number on the Indigo Mac that your Shellys call, 8178 to start with. Only change it if something else on the Mac already uses 8178. After changing it, restart the plugin with **Plugins → Shelly Direct → Reload**, and your Shellys are pointed at the new number by themselves. My Shelly Gen 1 plugin uses 8179, so the two can run together. |
| **Live Connection to Each Shelly** | Ticked, the plugin keeps a connection open to each Shelly and every change arrives the moment it happens, with checks slowed to every five minutes. Unticked, it uses checks and webhooks only. It is ticked to start with. See [The live connection](live-connection.md). |
| **Check Webhook Sender** | Ticked, a webhook is only accepted from the Shelly it names. Untick it only if a router between Indigo and your Shellys changes their addresses on the way. It is ticked to start with. |
| **Battery Sensor Stale Threshold (hours)** | How long a battery sensor — an H&T, Smoke, Flood or BLU sensor — can stay quiet before it is marked offline. 12 hours to start with. |
| **Identity Re-check Interval (minutes)** | How often each Shelly is asked for its MAC address, to make sure the plugin is talking to the right one. 60 minutes to start with, and 1 at least. The [How it works](how-it-works.md) page explains why. |
| **Daily Firmware Update Notifications** | Once a day, check every Shelly for new firmware and say which have an update waiting, in the Event Log and through the Pushover plugin if you have it. Unticked to start with. See [Firmware updates](firmware.md). |
| **Show Electricity Price on Plug LED Rings** | Colours the ring on your plugs by the price of electricity. When ticked, five more fields appear: **Today's Rates (variable)**, **Tomorrow's Rates (variable)**, **Current Price (variable)**, **Cheap Below (p/kWh)**, 20 to start with, and **Peak Above (p/kWh)**, 30 to start with. See [The price light](price-light.md). |
| **Offline Detection Threshold** | How long a mains Shelly can go without being heard from before it is marked offline: 5, 10, 15, 30 or 60 minutes. 10 minutes to start with. |
| **Show Device Activity in the Indigo Event Log** | Every on, off, dim and colour command, each button press and sensor report, and the midnight energy reset, always go to the plugin's own log file. Tick this to see them in the Indigo Event Log as well. Warnings, errors and blinds moving always appear there whatever this is set to. |
| **Log Level** | How much the plugin writes to the log: **Detailed Debugging**, **Debugging**, **Informational**, **Warnings Only** or **Errors Only**. Informational to start with. Only turn debugging on when chasing a problem, as it adds a lot of lines. |

### Keeping settings in one file

If you run several of my plugins, you can keep the settings they share in one file instead of typing them into each plugin. The file is called `IndigoSecrets.py` and lives in `/Library/Application Support/Perceptive Automation/`.

A blank copy, `IndigoSecrets_example.py`, comes inside the plugin. To use it:

1. In the Finder, right-click `ShellyDirect.indigoPlugin` and choose **Show Package Contents**, then open **Contents → Server Plugin**.
2. Copy `IndigoSecrets_example.py` to `/Library/Application Support/Perceptive Automation/` and rename it `IndigoSecrets.py`. If you already have an `IndigoSecrets.py` from another of my plugins, add the lines below to it instead.
3. Fill in the lines this plugin reads:

```python
INDIGO_SERVER_IP         = "192.168.1.5"   # the Mac that runs Indigo
SHELLY_DISCOVERY_SUBNETS = "192.168.1"     # comma-separate more than one
SHELLY_USERNAME          = ""              # only if your Shellys have a password
SHELLY_PASSWORD          = ""
```

Whatever the file holds is used, whatever the Configure dialog says. Anything the file leaves blank is taken from the dialog. The plugin reads the file when it starts, so restart the plugin after you change it.

## Each device's settings

Open these by double-clicking a Shelly device in Indigo. Which of them you see depends on the kind of device.

| Setting | On | What it does |
|---|---|---|
| **IP Address** | Every mains Shelly | The Shelly's network address. It must be a real address, and no other Shelly device can use it for the same output. |
| **Gateway IP Address** | BLU devices | The address of the mains Shelly the BLU device is paired with. See [BLU buttons and sensors](blu-devices.md). |
| **BTHome Device ID** | BLU devices | The number the gateway knows the BLU device by, such as 200. |
| **Channel** | Relay, dimmer | Which output of the Shelly this device controls. Use 0 for a Shelly with only one. |
| **Has Power Monitoring (PM)** | Relay, dimmer | Tick it for a Shelly that measures power, such as a plug or a 1PM. Untick it for one that does not, such as a Shelly 1. |
| **Has Temperature Add-on** | Relay | Tick it if a Shelly Plus Add-on with a temperature probe is fitted, and the probe's reading appears on the device. |
| **Lock Off (power monitor only)** | Relay | Refuses any command to turn it off. Turn On still works. |
| **High Power Alert** and **Alert Threshold (W)** | Relay | Warns you and runs the High Power Alert trigger when the power goes above the threshold. See [Energy tracking](energy.md). |
| **3-Phase Meter** | Energy meter | Tick it for a Pro 3EM or 3EM Gen 3. Leave it unticked for a single-phase Pro EM. |
| **Mirror States to Variables** | Most devices | Copies the device's main readings into Indigo variables in the **ShellyDirect** folder. |
| **Poll Interval** | Every mains Shelly | How often the plugin checks the Shelly when the live connection is not up: every 30 seconds for most, every 10 seconds for a cover or an i4, to start with. |
| **Detail Sweep** | Every mains Shelly | How often to read the slower extra readings — the Shelly's own Wi-Fi signal, which access point it is on, how long since it restarted, and whether it is connected to Shelly's cloud. Every 5 minutes to start with, or **Off**. |
| **Suppress Offline Alerts** | Relay | For a plug that is switched off at the wall between uses. It still shows as offline, but without a warning in the log or the Device Went Offline trigger. |
| **Show Electricity Price on LED Ring** | Relay | For a plug with an LED ring. See [The price light](price-light.md). |
| **Manage Switch Settings from Indigo** | Relay | Keeps a turn-off timer, power limits and what to do after a power cut on the Shelly itself. See [Switch settings on the Shelly](switch-settings.md). |
| **Hold Firmware** | Every mains Shelly | Firmware updates from Indigo leave this Shelly alone. See [Firmware updates](firmware.md). |
| **Show in Device List** | BLU sensor | **A reading** for a temperature, light or distance sensor, or **Open/closed or motion** for a door, window or motion sensor. |
| **Check Every** | BLU sensor | How often to read the sensor from its gateway: 30 seconds, a minute or 5 minutes. A minute to start with. |
