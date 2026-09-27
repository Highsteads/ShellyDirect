---
title: Your devices
nav_order: 3
---

# Your devices

Each Shelly you add becomes one Indigo device, or one for each output on a Shelly with several. This page says which kind to choose for each Shelly and what each one shows.

Every device also has a **Device Online** state, which is true while the Shelly is answering and false once it has stopped.

## Which kind for which Shelly

Discovery picks the kind for you. This table is for adding a Shelly by hand, or for checking what discovery chose.

| In Indigo | Your Shelly |
|---|---|
| **Shelly Relay** | Plus Plug UK, S, IT or US, Plug S Gen 3, Outdoor Plug S Gen 3, Plus 1 and 1PM (and the Mini versions), Pro 1 and 1PM, the 1, 1PM and 1L Gen 3 and Gen 4, the 1 Mini and 1PM Mini Gen 3 and Gen 4 |
| **Shelly Relay**, one per output | Plus 2PM, Pro 2 and 2PM, 2PM and 2L Gen 3 and Gen 4 (two outputs), Pro 3 (three), Pro 4PM and Power Strip Gen 4 (four) |
| **Shelly Cover / Roller** | Any two-output Shelly set up in the Shelly app to drive a blind, shutter or gate |
| **Shelly Dimmer** | Plus 0-10V Dimmer, Plus Wall Dimmer, Dimmer Gen 3 and Gen 4, Dimmer 0/1-10V PM Gen 3 and Gen 4, and the Pro Dimmer 1PM and 2PM (one device per output) |
| **Shelly RGBW** | Plus RGBW PM |
| **Shelly Energy Meter** | Pro EM and EM Gen 3 (one device per clamp), Pro 3EM, Pro 3EM-400 and 3EM Gen 3 |
| **Shelly Plus Uni** | Plus Uni |
| **Shelly Plus i4** | Plus i4, Plus i4 DC, i4 Gen 3 |
| **Shelly H&T Sensor** | Plus H&T, H&T Gen 3 |
| **Shelly Smoke Detector** | Plus Smoke |
| **Shelly Flood Sensor** | Flood Gen 4 |
| **Shelly BLU Button** | Shelly BLU Button |
| **Shelly BLU RC Button 4** | Shelly BLU RC Button 4 |
| **Shelly BLU Sensor (via BTHome gateway)** | Shelly BLU H&T, Door/Window, Motion, Distance and other BLU sensors |

A newer model that is not in the list still works. Discovery asks the Shelly what it has — switches, lights, a cover, meters or inputs — and creates the matching kind of device.

The plugin talks to the energy meters, the RGBW and the three battery sensors the way Shelly's own documentation describes, but I do not have any of them here to test against.

## Shelly Relay

For a plug or relay that switches something on and off. You control it with Indigo's usual **Turn On**, **Turn Off** and **Toggle**, from the device list, a control page, a schedule, a trigger or an action group.

| Shown as | What it means |
|---|---|
| **On / Off** | Whether the output is on or off right now. |
| **Power (W)** | The power the load is drawing, in watts. |
| **Voltage (V)** | The mains voltage at the plug. |
| **Current (A)** | The current the load is drawing, in amps. |
| **Energy Today (kWh)** | Energy used since midnight. The [Energy tracking](energy.md) page explains how it is counted. |
| **Energy This Month (kWh)** | Energy used since the first of the month. |
| **Device Temperature (C)** | How warm the Shelly itself is. |
| **Add-on Probe Temperature (C)** | The reading from a temperature probe on a Shelly Plus Add-on, if you have ticked **Has Temperature Add-on**. |
| **Last Switched By** | Who or what switched it last — see below. |

The power, voltage, current, energy and temperature readings only appear when **Has Power Monitoring (PM)** is ticked, which it should be for any Shelly that measures power.

**Last Switched By** shows one of: **Indigo**, **the button on the device**, **the switch wired to the device**, **the Shelly app**, **the device's own timer**, **the device starting up** (after a power cut), **a script on the device**, **a schedule on the device**, **a safety limit on the device**, or **another app on the network** (anything else that sent it a command). If the Shelly ever reports something the plugin does not know, it is shown in quotes, as the Shelly gave it. It only changes when the output actually switches.

## Shelly Cover / Roller

For a blind, shutter or gate driven by a two-output Shelly in cover mode. **Turn On** opens it, **Turn Off** closes it and **Toggle** does whichever is the opposite of now. The [Actions and triggers](actions-and-triggers.md) page lists the actions for stopping it, sending it to a position and tilting the slats.

| Shown as | What it means |
|---|---|
| **On / Off** | On while it is open or opening. |
| **Cover State** | What the Shelly says it is doing, such as open, closed, opening, closing or stopped. |
| **Current Position (0-100)** | How far open it is — 0 is fully closed, 100 fully open. |
| **Target Position (0-100)** | Where it is heading. |
| **Tilt Current Position (0-100)** | The slat angle on a venetian blind. |
| **Tilt Target Position (0-100)** | The last slat angle you asked for. |
| **Obstruction Detected** | True if the Shelly stopped the motor because something was in the way. |

## Shelly Dimmer

A dimmable light. It answers Indigo's usual on, off, brightness, brighten and dim commands.

| Shown as | What it means |
|---|---|
| **On / Off and brightness** | Whether the light is on, and how bright, from 0 to 100. |
| **Power (W)** | The power the light is drawing, if **Has Power Monitoring (PM)** is ticked. |

## Shelly RGBW

A colour light strip or lamp on a Plus RGBW PM. It answers the same commands as a dimmer, and the **Set RGBW Color** action sets its colour.

| Shown as | What it means |
|---|---|
| **On / Off and brightness** | Whether it is on, and how bright. |
| **Red, Green, Blue, White (0-255)** | The level of each colour. |
| **Color Mode** | How the Shelly is set up to drive the lights. |
| **Power (W)** | The power it is drawing. |

## Shelly Energy Meter

A meter that clamps round a cable. It measures, it does not switch.

| Shown as | What it means |
|---|---|
| **Voltage Phase A, B, C (V)** | The voltage on each phase. |
| **Current Phase A, B, C (A)** | The current on each phase. |
| **Active Power Phase A, B, C (W)** | The power on each phase. |
| **Energy Today (kWh)** and **Energy This Month (kWh)** | Energy since midnight and since the first of the month. |

Tick **3-Phase Meter** for a Pro 3EM or 3EM Gen 3, and all three phases are shown on one device. On a single-phase meter such as the Pro EM, each clamp is its own device and its readings are in the Phase A states.

## Shelly Plus Uni

The Uni has one output, two inputs and two voltage inputs. The output answers **Turn On**, **Turn Off** and **Toggle**.

| Shown as | What it means |
|---|---|
| **On / Off** | Whether the output is on. |
| **Digital Input 0** and **Digital Input 1** | Whether each input is on. |
| **Analog Input 0 (V)** and **Analog Input 1 (V)** | The voltage on each voltage input. |

A button wired to either input can run a trigger — see [Actions and triggers](actions-and-triggers.md).

## Shelly Plus i4

The i4 has four inputs for switches or buttons, and no outputs.

| Shown as | What it means |
|---|---|
| **Input 1 State**, **Input 2 State**, **Input 3 State** | Whether each of those inputs is on. |

The first input, input 0, has no state of its own in Indigo, but a press on it runs the **Button Input Pressed** trigger like the other three.

## Shelly H&T Sensor

A battery temperature and humidity sensor. It sleeps between readings and sends each change to Indigo when it wakes, so the plugin never asks it anything.

| Shown as | What it means |
|---|---|
| **Temperature (C)** | The temperature it last sent. |
| **Humidity (%)** | The humidity it last sent. |

## Shelly Smoke Detector and Shelly Flood Sensor

Battery sensors that tell Indigo when the alarm starts and when it stops. When smoke or water is detected, the Event Log says so. If you tick **Mirror States to Variables**, a variable in the **ShellyDirect** folder holds the alarm as True or False, which a trigger can watch.

## Battery sensors and Device Online

The H&T, Smoke and Flood only speak when something changes, so they are not marked offline until nothing has been heard from them for 12 hours. You can change that in the plugin's **Battery Sensor Stale Threshold** setting.

## Shelly BLU buttons and sensors

These have their own page: [BLU buttons and sensors](blu-devices.md).

## Extra readings

Each Shelly reports more than the states above — its Wi-Fi signal, which access point it is connected to, how long since it last restarted, whether a firmware update is waiting, and so on. The plugin adds these to the device as extra states the first time it sees them, so they are there for triggers and control pages without a plugin update. The **Detail Sweep** setting on each device says how often the slower ones are read.

## Copying readings into variables

Tick **Mirror States to Variables** on a device, and the plugin writes its main readings — on or off, power, energy today, brightness, temperature and so on — into Indigo variables in a folder called **ShellyDirect**. Each variable is named after the device, such as `shelly_kitchen_plug_watts`.
