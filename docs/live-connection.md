---
title: The live connection
nav_order: 5
---

# The live connection

From version 4.0, the plugin keeps a connection open to every mains Shelly, one for each Shelly however many outputs it has, and the Shelly tells Indigo about every change the moment it happens: a switch turning on or off, a button press, a change in power.

It is on to start with. There is nothing to set up.

## What it changes

- **A switch shows at once.** When a plug or relay turns on or off, however it was switched, Indigo shows it straight away.
- **A button press runs its trigger at once.** A press on a button wired to a relay, a Uni or an i4 runs the **Button Input Pressed** trigger as soon as the Shelly reports it.
- **Power readings stay at the old pace.** A plug on a live load reports a new power figure about once a second. The plugin writes power and energy at most every 30 seconds, the same pace as the checks it used before, so SQL Logger gets no more history than it did.
- **Other devices are read again when something changes.** For a blind, a dimmer, a colour light, a Uni, an i4 or an energy meter, a change reported down the connection makes the plugin read the device again straight away, and no more often than every 30 seconds.
- **Checking slows to every five minutes** while the connection is up, as a backstop.

## Keeping it honest

- **Every minute** the plugin asks each Shelly for its full state down the connection, which keeps a quiet Shelly showing as online.
- **If nothing is heard for two and a half minutes**, the connection is treated as down, and the Shelly is checked at its normal pace again.
- **If the connection drops**, the plugin reconnects by itself, waiting five seconds at first and longer each time, up to two minutes. Checking and webhooks carry on meanwhile.
- **Every message carries the Shelly's MAC address**, and nothing is recorded from a Shelly that is not the one the plugin expects at that address. If that happens, the Event Log says so once.
- **Webhooks stay in place.** While the connection is up, a webhook for a switch or a button is ignored, so nothing happens twice. When it is down, webhooks take over.

## Which Shellys use it

Every mains Shelly in the plugin uses it: relays and plugs, the Uni, covers, dimmers, the RGBW, the i4 and energy meters. The battery sensors sleep, so they do not, and nor do BLU buttons and sensors, which reach Indigo through another Shelly.

The connection is **not used when Shelly Username and Password are set** in the plugin's settings. Those installs are checked and use webhooks exactly as before version 4.0.

## Turning it off

Untick **Live Connection to Each Shelly** in **Plugins → Shelly Direct → Configure**. The connections close within a minute, and the plugin goes back to checking and webhooks alone.

## Checking it is working

**Plugins → Shelly Direct → Show Plugin Info** writes a **Live Connections** line to the Event Log, such as `18 of 18 Shellys`.

The connection needs a small extra that Indigo installs along with the plugin. If it is missing, the Event Log says so once and the plugin carries on checking as before. Restarting the plugin once Indigo has finished installing it brings the connection up.
