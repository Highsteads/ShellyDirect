---
title: Firmware updates
nav_order: 9
---

# Firmware updates

Shelly releases new firmware for its devices now and then. The plugin can tell you when an update is waiting and install it for you, one Shelly at a time.

## Finding out what is waiting

- **Plugins → Shelly Direct → Check Firmware Versions** asks every Shelly whether an update is waiting and writes the answer for each to the Event Log.
- **Daily Firmware Update Notifications**, in the plugin's settings, does the same once a day by itself. When something is waiting, the Event Log has one short message, such as "New Shelly firmware for four devices. Firmware 2.0.1 is ready for ...", saying which Shellys and how to install it. If you have the Pushover plugin installed and enabled, the same message goes to your phone. When everything is up to date it says nothing.

## Installing updates

- **Plugins → Shelly Direct → Update Firmware on All Devices** updates every Shelly in turn.
- The **Update Firmware** action updates one device, so you can do it from an action group or a schedule — at three in the morning, say.

For each Shelly, the plugin:

1. installs the latest stable firmware, if there is one waiting,
2. waits for the Shelly to restart and come back on the new version, for up to five minutes,
3. checks each relay output is still on or off as it was before, and switches it back if the restart changed it, with a warning in the Event Log.

A Shelly with several outputs is only updated once. When the menu item has finished, the Event Log has one line listing what happened to each Shelly — updated, already up to date, held, or not reachable.

Only one update runs at a time. If you start a second while the first is running, the Event Log says so and nothing else happens.

The battery sensors and BLU devices cannot be updated from here.

## Holding a Shelly back

Tick **Hold Firmware** on any Shelly that must never restart without you there — the plug feeding the Mac that runs Indigo, say, or a fridge. The update action and menu item leave it alone, and say so.

The **Set Firmware Hold** action ticks or unticks it, so you can change it from a schedule or a script as well as the device dialog.
