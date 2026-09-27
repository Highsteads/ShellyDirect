---
title: How it works
nav_order: 4
---

# How it works

You do not need to know any of this to use the plugin. It is here for anyone who likes to know what is going on.

## Three ways of hearing from a Shelly

The plugin keeps up to date in three ways, each a backstop for the others.

1. **The live connection.** The plugin keeps a connection open to every mains Shelly, and the Shelly reports each change down it the moment it happens. The [live connection](live-connection.md) page covers it.
2. **Webhooks.** A webhook is a web address a Shelly calls when something happens to it. The plugin gives each Shelly its own address to call when it switches, when a button is pressed or when a blind moves, and listens for those calls on port 8178 of the Indigo Mac. While the live connection is up, a webhook for a switch or a button is ignored, because the connection has already delivered it.
3. **Checking.** The plugin asks each Shelly how it is at the pace set by the device's **Poll Interval** — every 30 seconds for most, every 10 seconds for a blind or an i4. While the live connection is up, that slows to every five minutes.

The battery sensors, the H&T, Smoke and Flood, sleep between readings, so the plugin never asks them anything. They only use webhooks.

## Setting up the webhooks

When a Shelly is added, and whenever its address changes, the plugin sets up its webhooks on the Shelly for you.

- **Webhooks you set up yourself are left alone.** The plugin only ever touches the ones it made.
- **They are checked every six hours.** Any that have gone missing are put back. Any of the plugin's own that no longer belong on that Shelly are removed — one for a device you have deleted, one for a device that now lives on another Shelly, one pointing at an old address or port of the Indigo Mac, or a second copy of one already there.
- **A Shelly that cannot be reached** when its webhooks are due is simply checked instead, and tried again later. It is only mentioned in the log after three failed tries in a row.
- **Only the right Shelly is believed.** A webhook is only accepted from the Shelly it names. One arriving from any other address is ignored, reported once in the log, and removed from the Shelly that sent it. If a router between Indigo and your Shellys changes their addresses on the way, untick **Check Webhook Sender** in the plugin's settings.

**Plugins → Shelly Direct → Reconfigure Webhooks (All Devices)** sets them all up again at once, which helps after a change to your network.

A battery sensor is usually asleep when the plugin tries to set up its webhooks. If it cannot, the Event Log gives the web address to put into the sensor by hand, or you can press the sensor's button to wake it and choose **Reconfigure Webhooks** again.

## Knowing which Shelly is which

Your router hands out network addresses, and now and then it hands a Shelly a different one — after a power cut, say. If Indigo simply trusted the address, it could end up reading one plug's power into another plug's device.

So the plugin knows each Shelly by its **MAC address** — a number every network device is made with and never changes, a bit like a serial number.

- **Once an hour** (the **Identity Re-check Interval** setting), the plugin asks the Shelly at each address for its MAC address before it accepts its readings.
- **If a different Shelly answers**, nothing from it is recorded, the Event Log says once which Shelly it found and where, and the plugin looks for the right one.
- **Shellys announce themselves on the network** (this is known as mDNS or Bonjour), and the plugin listens. When the right Shelly turns up at a new address, the plugin checks it there, updates the device's address itself and says so in one line.
- **A Shelly that stops answering** is looked for the same way, quietly, no more than once every ten minutes, in case it has moved.
- **The device dialog refuses an address** that another of your Shelly devices already uses on the same output, because two devices on one Shelly would mix up each other's readings.
- **Discovery never makes a second device** for a Shelly it already knows. If one has moved, discovery updates its address instead.

**Plugins → Shelly Direct → Show mDNS Discovered Shellys** lists every Shelly announcing itself, its MAC address and current address, and the Indigo device it matches, and points out any device whose stored address is out of date.

Commands you send — on, off, brightness, a blind position — go to the stored address straight away, without waiting for this check, so a garage door or a light is never left uncontrollable.

## Shellys that insist on a secure connection

A Shelly that leaves the factory on firmware 2.0 or later only accepts secure (HTTPS) connections. The plugin notices the first time a Shelly asks for this, says so in the log, and uses a secure connection to it from then on. Shelly signs these connections itself, so the plugin does not check the certificate.

## A command that does not arrive

If the plugin cannot reach a Shelly when it sends a command, it tries once more a second later before it reports the command as failed. Every command is of the "set it on" or "set it off" kind, so sending it twice does no harm.

## When a Shelly stops answering

A mains Shelly is marked offline, with **Device Online** false, when it misses three checks in a row, or when nothing at all has been heard from it for the **Offline Detection Threshold**, ten minutes to start with. It then runs the **Device Went Offline** trigger.

A Shelly that is offline is checked every five minutes rather than at its usual pace, so a plug that is switched off at the wall does not hold up the others. As soon as it answers, it is back to normal.

The Event Log line waits three minutes before it is written:

- **If three or more Shellys stop answering within three minutes of each other**, the log has one line naming them all, pointing at the Wi-Fi or the router, and the **Several Devices Offline Together** trigger runs.
- **If a Shelly comes back within those three minutes**, there is no warning at all, just a note in the plugin's own log that it stopped answering for a minute or two.
- **Otherwise**, each one has its own line.

Coming back works the same way, with one line for several Shellys.

Tick **Suppress Offline Alerts** on a plug that is switched off at the wall between uses, such as one on a washing machine, and it goes offline without a log line or a trigger.

## What goes in the log

The Indigo Event Log only shows things you might need to act on: warnings and errors, a Shelly going offline or coming back, a blind being moved, a smoke or flood alarm, and a change the plugin makes to a Shelly's own settings. Routine activity — every on, off, dim and colour command, button presses and sensor reports — goes to the plugin's own log file instead. The [Settings](settings.md) page shows how to have it in the Event Log as well.
