---
title: Version history
nav_order: 15
---

# Version history

The newest version is at the top.

## 4.3.3 — 5 October 2026

**Shelly Dimmer and RGBW lights work from Indigo again.** Turn On, Turn Off, Toggle, Set Brightness, Brighten By and Dim By on a Shelly Dimmer or a Shelly RGBW failed every time. The Event Log showed "actionControlDimmer exception" and the light did nothing. The plugin was asking Indigo for a list of dimmer actions that does not exist, instead of the list Indigo really has. Relays, covers and the rest were never affected. The **Set RGBW Color** action was not affected either, because it takes its own route.

## 4.3.2 — 29 September 2026

Fewer false alarms at midnight. Just after midnight five or six plugs a night logged "cumulative energy went backwards" when their first reading came in a fraction of a watt-hour below the new day's starting point, because that reading was slightly older than the one taken at midnight. A drop that small now simply means no energy used yet. A real counter reset, which falls much further, is still checked twice before it is believed, as before. The energy figures themselves were never affected.

## 4.3.1 — 28 September 2026

No change to how the plugin works. Two notes in the code now explain why the relay list for the Switched Outside Indigo trigger, and discovery, include disabled devices.

## 4.3.0 — 27 September 2026

Writing the guide turned up a few things that did not work as they should, and this version puts them right.

- **The smoke and flood alarms show in Indigo.** The alarm now turns the device on while it is going off and off once it has stopped, so the device list shows it and a trigger can watch it. Before this the alarm only reached the Event Log and the mirrored variable.
- **The i4's first input shows in Indigo**, as the device's own on or off, alongside the other three inputs.
- **The energy meter shows its total power**, in the device list and for a trigger to watch.
- **The H&T, Smoke and Flood report their battery.** It comes with every reading, alarm and all-clear. A sensor set up before this version needs waking with its button and a **Reconfigure Webhooks (All Devices)** to start sending it.
- **The Flood Sensor no longer has a temperature reading.** Shelly's flood sensors have no thermometer, so it was always blank.
- **Accept Replaced Shellys**, a new menu item, lets a device take on a Shelly you have swapped for a new one at the same address, keeping its name, triggers and control pages. The log used to tell you to clear the old Shelly's number in the device dialog, which has no such box, so the only way out was to delete the device and start again.
- **BLU buttons no longer write a reading that went nowhere.** Each press used to set a value the button does not have. The press is still shown in **Last Action** and **Press Count**, and still runs the **BLU Button Pressed** trigger.
- **High Power Alert no longer trips over a missing reading.** When a plug's answer came without a power figure, its regular check failed and the log reported a problem with the plug. Now the alert just waits for the next reading.

## 4.2.0 — 26 September 2026

A new **Set Firmware Hold** action ticks or unticks **Hold Firmware** on a device, so it can be changed from a schedule or a script as well as the device dialog.

## 4.1.0 — 26 September 2026

- **Two new menu items**, **Show Electricity Price on All Plugs** and **Stop Showing Electricity Price on Plugs**, set the price light on every plug with an LED ring at once, instead of one dialog per plug. A plug that cannot be reached is ticked anyway and shows the price when it is back.
- **The LED ring, colour and switch-settings commands work.** The way their settings were written into the request made the Shelly refuse them, so none of them had worked before.
- **"- none -" in the price menus means none.** It used to fall back to the first variable in the list.

## 4.0.0 — 26 September 2026

**A live connection to every Shelly.** The plugin keeps a connection open to each Shelly, and the Shelly tells Indigo about every change the moment it happens — a switch turning on or off, a button press, a change in power.

- Checking drops to every five minutes as a backstop while the connection is up, and goes back to its normal pace the moment it is not.
- Power readings are written at most every 30 seconds, the same pace as before, so SQL Logger gets no more history than it did.
- Webhooks stay in place as a fallback. One arriving while the connection is up is ignored, so nothing happens twice.
- The connection is not used while Shelly Username and Password are set. Those installs work exactly as before.
- A tick box in the plugin's settings turns it off.

## 3.20.0 — 26 September 2026

- **The electricity price on your plugs' LED rings** — green at the cheap rate, amber at the standard rate, red at the peak rate, bright while the plug is on and dim while it is off. The price comes from a variable holding the day's rates in Octopus's format, or one holding the price now. Untick it and the ring goes back to how it was.
- **Safety settings held on the plug itself** — turn off after so many minutes, cut the power above a wattage or current, and what to do after a power cut. The Shelly enforces them, so they keep working when Indigo is down, and the plugin puts them back if something else changes them.
- **Firmware updates from Indigo** — an **Update Firmware** action and an **Update Firmware on All Devices** menu item, which update one Shelly at a time, wait for each to come back, and switch a relay back if the restart changed it. **Hold Firmware** keeps a device out of it. The daily firmware notice reads as a sentence.
- **One line when the network drops.** When three or more Shellys stop answering within three minutes of each other, the log says so in one line and a new **Several Devices Offline Together** trigger runs. A Shelly that drops for a minute and comes straight back gets one quiet note.
- **Who switched it.** Each relay has a **Last Switched By** state, and a new **Switched Outside Indigo** trigger runs when anything other than Indigo switches it.
- **A lost command is sent again**, once, a second later, before it is reported as failed.
- **BLU sensors without scripts.** A new **Shelly BLU Sensor** device reads a BLU H&T, Door/Window, Motion or Distance sensor through a Gen 3, Gen 4 or Pro Shelly's own Bluetooth support, and a new **Show BLU Devices on Gateways** menu item lists what is paired with each gateway. I built this from Shelly's documentation and a Gen 4 gateway, with no BLU sensor to test against.

## 3.19.0 — 26 September 2026

Fixes from a full review of the plugin.

- **A plug could report as another device.** When two devices had once shared an address, a plug could keep the other device's webhooks for ever, and switching it wrote its on and off into the other device. The plugin now removes any webhook that belongs to a device on a different Shelly, points at an old Indigo address or port, or is there twice, and ignores a webhook that did not come from the Shelly it names. A new **Check Webhook Sender** tick box turns that check off for networks where a router changes the addresses.
- **Button and input webhooks work.** The plugin had been asking for them under names Shelly does not use, so no i4, Uni or relay input had ever sent a press to Indigo.
- **Webhooks are set up one at a time per device.** Two could overlap after a settings change, and some plugs ended up with every webhook twice. A device no longer restarts when the plugin saves something it has learned about it, such as its MAC address.
- **The midnight energy reset is checked like every other reading.** It confirms the Shelly's identity, ignores a reading below the day's starting figure, and does not write a second history row for a day already counted. A counter reset that turns out to be a glitch is undone when the real figure comes back.
- **New readings keep their type**, so SQL Logger no longer gets a second column for one reading.
- **Shellys bought new work.** A Shelly that leaves the factory on firmware 2.0 or later only accepts secure connections, and the plugin now uses one for any Shelly that asks.
- **The model list covers the Gen 3 and Gen 4 range**, including the Zigbee versions and Pro Shellys with the add-on fitted.

## 3.18.4 — 23 September 2026

Your plugs no longer fill SQL Logger's history with counters. Every Shelly reports a running on-time counter, how long since it restarted and its Wi-Fi signal, and they change on nearly every check. The plugin now tells SQL Logger to skip those three, and keeps anything you had already told it to skip. Power, voltage, current, energy and temperature are logged as before.

## 3.18.3 — 21 September 2026

No change to what the plugin does. Some comments in the plugin, and the tests, used real network hardware addresses from my own plugs as examples. They are now made-up example values.

## 3.18.2 — 20 September 2026

A BLU button shares its gateway's address, so when the plugin repaired an out-of-date webhook it could pick the button instead of the gateway. It now always picks the right one.

## 3.18.1 — 8 September 2026

A plug that vanishes in the moment between being found and having its webhooks set up is no longer reported as a warning straight away. It only warns after three failed tries in a row, the same as the six-hourly webhook check.

## 3.18.0 — 6 September 2026

Every on and off command now goes to the plugin's own log instead of the Indigo Event Log, with a new **Show Device Activity in the Indigo Event Log** tick box to put them back. Blinds moving, failed commands, Shellys going offline, and smoke and flood alarms still always reach the Event Log.

## 3.17.0 — 29 August 2026

A new **Detail Sweep**, every five minutes to start with and adjustable per device, reads what each Shelly knows about itself — its own Wi-Fi signal, which access point it is on, how long since it restarted, and its cloud connection.

## 3.16.4 — 15 August 2026

A plug switched off at the wall is unreachable at midnight, when the plugin resets its daily energy count. That is now an ordinary note rather than a warning. A midnight failure for any other reason is still a warning.

## 3.16.3 — 9 August 2026

The midnight energy reset skips a Shelly already known to be offline, rather than warning about it every night. A plug switched off at the wall between uses had produced a warning a night, and one that had genuinely died looked just the same.

## 3.16.2 — 27 July 2026

A second way for a day's energy to jump to an impossible figure is closed. A Shelly that reported zero for a single reading made the plugin start counting from nothing, and the next reading became its whole lifetime total. The plugin now waits for a second low reading before it believes one. A Shelly that has been away for weeks no longer has all that energy written down as a single day.

## 3.16.1 — 21 July 2026

Housekeeping on the small file of shared code every one of my plugins carries. Turning log timestamps on and off twice no longer gives every line two timestamps, and a setting saved as the word "false" is read as off.

## 3.16.0 — 21 July 2026

**Each Shelly is known by its MAC address, not its network address.** When a router gave one plug's address to another, two Indigo devices ended up reading the same plug, and one recorded 3,446 kWh in a day. Now every Shelly proves who it is before anything is recorded. If a different Shelly answers, nothing is written, and the plugin looks for the right one by the announcements Shellys make on the network, updating the address itself when it finds it. The device dialog refuses an address another device already uses, and a new **Show mDNS Discovered Shellys** menu item lists what is on the network.

## 3.15.1 — 21 July 2026

Warnings and errors appear in the Event Log as warnings and errors. Before, they all appeared as ordinary lines.

## 3.15 — 17 July 2026

- A new **Test Shelly Connection** menu item checks the whole set-up and writes one summary to the log, made for a support post.
- The **Webhook Listener Port** can be changed, for anyone with something else on 8178.
- Discovery reports its progress, and names the devices you already have that did not answer.
- The plugin no longer installs its own copy of a library Indigo already provides, which makes the install much smaller.

## 3.14 — 17 July 2026

Fixes from the same review: a busy Shelly that sends back part of a reading no longer gives false zero readings, a failed webhook set-up is reported rather than hidden, the plugin starts without waiting on Shellys that are away, and the H&T has its own temperature state.

## 3.13 — 16 July 2026

More fixes from the same review. The Uni's inputs update, battery sensors use the right settings and stop showing offline between their reports, a Shelly that is away is checked less often, the settings in the shared settings file are no longer forgotten when you save the dialog, and discovery handles replaced and unknown Shellys more carefully.

## 3.12 — 16 July 2026

Fixes from a thorough review of the plugin.

- Shellys with several outputs no longer have their outputs remove each other's webhooks, and discovery makes a device for every output of a multi-output dimmer or meter.
- A Shelly that is away at midnight no longer spoils the next day's energy figures.
- Energy meters and RGBW colour commands use the right commands for these Shellys.
- **Set Light Effect** says in the log that these Shellys have no effects, rather than doing nothing silently.

## 3.11 — 19 June 2026

Stops a Shelly repeatedly logging that its webhooks were missing. Two Indigo devices pointed at the same plug had been removing each other's webhooks. The plugin now spots two devices on one Shelly, says in the log which to delete, and stops retrying a repair that does not hold.

## 3.10 — 13 June 2026

A quieter start. Several sensor device types declared a state Indigo already provides, and Indigo complained about it each time the plugin loaded.

## 3.9 — 13 June 2026

Discovery handles models it does not know. Instead of assuming a plain relay, it asks the Shelly what it has and creates the right kind of device with the right number of outputs.

## 3.8 — 10 June 2026

No change to what the plugin does. The code is now checked automatically each time it changes.

## 3.7 — 6 June 2026

The midnight energy reset still happens when a restart spans midnight, energy figures are safe when two readings arrive at once, and the **High Power Alert** trigger only offers devices that can raise it.

## 3.6 — 6 June 2026

A reading that arrives without its energy total keeps the last good figure, rather than counting as zero and giving a false spike. One misbehaving Shelly can no longer stop the plugin checking the others.

## 3.5 — 5 June 2026

The sensor devices answer **Send Status Request**, and the daily firmware notice reaches Pushover.

## 3.4 — 23 May 2026

Every log line starts with the time to the thousandth of a second, with a menu item to turn that off.

## 3.3 — 23 May 2026

The Shelly username, password and discovery ranges can be kept in the shared settings file, like the Indigo server's address.

## 3.2 — 16 May 2026

Log lines have a consistent form.

## 3.1 — 15 May 2026

A switch changed at the wall is logged once, not twice.

## 3.0 — 13 May 2026

The names of the device states changed to the form Indigo expects, such as **powerWatts** in place of **power_watts**. Triggers and control pages that used the old names needed updating. The Indigo server's address can be kept in the shared settings file.

## 2.7 — 10 May 2026

Every reading a Shelly reports that has no state of its own — power factor, frequency, Wi-Fi signal and so on — is added to the device as an extra state.

## 2.6 — 26 April 2026

Discovery recognises a Shelly that has moved to a new address by its MAC address, and updates its device rather than making a second one.

## 2.5 — 24 April 2026

Support for the Shelly BLU Button and BLU RC Button 4, through a mains Shelly acting as a Bluetooth gateway, with a new **BLU Button Pressed** trigger.

## 2.3 — 12 April 2026

Energy is counted in kWh only. The cost figures, and the settings for rates and currency, are gone.

## 2.2 — 23 March 2026

First public release: relays, covers, dimmers, RGBW, energy meters, the Uni, the i4, the H&T, Smoke and Flood, with webhooks, discovery, energy tracking, variable copies, triggers and firmware notices.
