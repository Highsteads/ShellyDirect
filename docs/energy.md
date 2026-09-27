---
title: Energy tracking
nav_order: 6
---

# Energy tracking

A Shelly Relay with **Has Power Monitoring (PM)** ticked, and every Shelly Energy Meter, shows how much energy has passed through it today and this month.

## How it is counted

Each Shelly keeps a running total of all the energy it has ever measured. At midnight the plugin notes that total, and **Energy Today** is how far it has gone up since. **Energy This Month** works the same way from the first of the month.

The plugin takes care of the awkward cases:

- **A power cut can set a Shelly's total back to zero.** When the total goes down, the plugin waits for a second reading before it believes it, because a single low reading is more often a glitch than a real reset. Meanwhile it keeps the last good figures. If the total later climbs back to where it was, the plugin decides the reset was a glitch after all, puts the old figures back, and says so in the Event Log.
- **A reading that arrives without its total** keeps the last good figures rather than counting it as zero.
- **A Shelly that is away at midnight**, such as a plug switched off at the wall, keeps its old figures until it answers again. The plugin then starts the new day from that reading, and adds the time it missed to the history as one day. If it was away for more than two days, that energy is left out of the history, rather than written down as one very large day.

## Thirty days of history

The plugin keeps one figure a day for each device for the last 30 days. **Plugins → Shelly Direct → Export Energy History to CSV** writes them to a spreadsheet file with three columns, **Date**, **Device** and **kWh**. The file goes in the **Documents/Indigo/ShellyDirect** folder in the home folder of the Mac user that runs Indigo, named after today's date, such as `energy_history_2026-09-27.csv`. The Event Log says where it went and how many rows it wrote.

## High Power Alert

A Shelly Relay can warn you when its load draws more than you expect — a heater left on, or an appliance with a fault.

1. Double-click the relay in Indigo, tick **High Power Alert**, and set **Alert Threshold (W)**. It is 2000 watts to start with.
2. Create a trigger of type **Shelly Direct → High Power Alert**, choose the relay or **Any Device**, and add whatever you want to happen.

When the power goes above the threshold, the Event Log has a warning and the trigger runs, once. When the power drops back to the threshold or below, the log notes it, and the next rise runs the trigger again.

## Keeping SQL Logger's history small

If you use SQL Logger to keep a history of your devices, the plugin asks it to skip three readings that change on nearly every check and that nobody charts: the Shelly's running on-time counter, how long since it last restarted, and its Wi-Fi signal. It adds them to each device's SQL Logger skip list and keeps anything you have put there yourself. Power, voltage, current, energy and temperature are logged as normal.

On the live connection, power and energy are written at most every 30 seconds, so SQL Logger gets no more rows than it did when the plugin only checked every 30 seconds.
