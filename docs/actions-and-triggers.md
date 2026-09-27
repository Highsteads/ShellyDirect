---
title: Actions and triggers
nav_order: 11
---

# Actions and triggers

## Switching and dimming

Every Shelly device that switches or dims answers Indigo's standard actions, wherever you use them — a control page, a schedule, a trigger or an action group:

- **Turn On**, **Turn Off** and **Toggle** on a relay, a Uni, a dimmer or an RGBW. On a cover, Turn On opens it and Turn Off closes it.
- **Set Brightness**, **Brighten By** and **Dim By** on a dimmer or an RGBW.
- **Send Status Request** on any device that can be asked, which reads it there and then rather than waiting for the next check.

If the plugin cannot reach the Shelly, it tries once more a second later, and if that fails too, the Event Log says the command was not delivered.

If **Lock Off** is ticked on a relay, Turn Off and a Toggle that would turn it off are refused, with a warning in the Event Log. Turn On still works. It is meant for anything that must stay on.

## The plugin's own actions

These are under **Device Actions → Advanced** when you add an action.

| Action | For | What it does |
|---|---|---|
| **Turn On For N Seconds** | Relay | Turns the relay on and off again after the number of **Seconds** you set, 1 to start with. The Shelly does the timing, so it turns off on time even if Indigo is busy. One second suits most garage door openers. |
| **Open Cover**, **Close Cover**, **Stop Cover** | Cover | Drive the blind or shutter. |
| **Go To Position** | Cover | Moves it to a **Position** from 0 (fully closed) to 100 (fully open). |
| **Set Tilt Angle** | Cover | Sets the slats of a venetian blind, from 0 (closed) to 100 (open). |
| **Set Brightness** | Dimmer | Sets the brightness, from 0 to 100. |
| **Set RGBW Color** | RGBW | Sets **Red**, **Green**, **Blue** and **White**, each from 0 to 255, and **Brightness** from 0 to 100, and turns the light on. If the RGBW is set up in the Shelly app to drive plain white lights, it has no colour to set, and the Event Log says so. |
| **Set Light Effect** | RGBW | Does nothing, and says so in the Event Log, because these Shellys have no equivalent of the effects on the older models. It is kept so older actions do not break. |
| **Update Firmware** | Any mains Shelly | Installs the latest firmware — see [Firmware updates](firmware.md). |
| **Set Firmware Hold** | Any Shelly | Ticks or unticks **Hold Firmware** on the device. |

Every blind or shutter movement goes in the Event Log, because it is something done to the house.

## Triggers

Create a new trigger and set its type to one of these under **Shelly Direct**.

| Trigger | Runs when | You can choose |
|---|---|---|
| **Button Input Pressed** | A button wired to a relay, a Uni or an i4 is pressed | The device or **Any Device**, the input (0 to 3, or any), and the kind of press — single, double or long, or any |
| **BLU Button Pressed** | A BLU Button or BLU RC Button 4 is pressed | The device or **Any BLU Device**, the kind of press — single, double, triple or long, or any — and on the RC Button 4, which button |
| **Switched Outside Indigo** | A relay switches and Indigo did not switch it — its button, the Shelly app, its own timer, or coming back after a power cut | The relay or **Any Relay** |
| **Device Went Offline** | A Shelly stops answering | The device or **Any Device** |
| **High Power Alert** | A relay's power goes above its **Alert Threshold** — see [Energy tracking](energy.md) | The relay or **Any Device** |
| **Several Devices Offline Together** | Three or more Shellys stop answering within three minutes of each other — usually the Wi-Fi or the router rather than the devices | Nothing to choose |

A few notes:

- On a relay, only a button wired to input 0 counts. On a Shelly with several outputs, it runs the trigger for the first output's device.
- **Device Went Offline** does not run for a relay with **Suppress Offline Alerts** ticked.
- **Several Devices Offline Together** runs once for the group. **Device Went Offline** still runs for each of them.
- The relay's **Last Switched By** state says what switched it, if your trigger's actions need to know.

For example, if someone switches the garage lights on at the wall, **Switched Outside Indigo** could have Indigo switch them off again after half an hour.
