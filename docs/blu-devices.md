---
title: BLU buttons and sensors
nav_order: 10
---

# BLU buttons and sensors

Shelly's BLU range are small battery devices that talk Bluetooth rather than Wi-Fi. They have no network address of their own. Instead, a mains Shelly nearby listens for them and passes on what they say — Shelly calls it the **gateway**. So each BLU device in Indigo is set up with its gateway's address, plus the number the gateway knows it by.

The gateway must be one of your Shelly Direct devices in Indigo as well.

## Finding the number

Once a BLU device is paired with a gateway, the gateway gives it a number, usually 200 or above, which Indigo calls the **BTHome Device ID**.

Choose **Plugins → Shelly Direct → Show BLU Devices on Gateways**. For each gateway that has BLU devices paired, the Event Log lists each one with its number, the name you gave it, its Bluetooth address and what it reports, such as "BTHome device 200: "Hall Button" ... - reports battery and button". The gateway's own web page also shows it, under **Components**.

## BLU Button and BLU RC Button 4

1. Pair the button with a mains Shelly so that Shelly becomes its gateway.
2. In Indigo, create a new **Shelly Direct** device of type **Shelly BLU Button**, or **Shelly BLU RC Button 4** for the four-button remote.
3. Set **Gateway IP Address** to the gateway's network address, and **BTHome Device ID** to the button's number.
4. Click **Save**. The plugin sets up the gateway to pass each press on to Indigo.

Each press runs the **BLU Button Pressed** trigger, which you can narrow down to one button, one kind of press, and on the RC Button 4, which of its four buttons. The BLU Button knows a single, double and long press, and the RC Button 4 a triple press as well.

What each button shows in Indigo:

| Shown as | What it means |
|---|---|
| **Last Action** | The last press, such as `single_push` or `long_push`. |
| **Press Count** | How many presses Indigo has seen. |
| **Last Button (1-4)** | Which button was pressed last, on the RC Button 4 only. |
| **Battery (%)** and **RSSI (dBm)** | The battery level and Bluetooth signal, when the gateway sends them with a press. |

A button sleeps until it is pressed, so it is never marked offline.

## BLU sensors

A Gen 3, Gen 4 or Pro Shelly can read BLU sensors itself, with no script — the BLU H&T, Door/Window, Motion and Distance, and other BLU sensors that work the same way.

1. Pair the sensor from the gateway's own web page: **Components → Add BTHome device**.
2. In Indigo, create a new **Shelly Direct** device of type **Shelly BLU Sensor (via BTHome gateway)**.
3. Set **Gateway IP Address** to the gateway's address and **BTHome Device ID** to the sensor's number.
4. Set **Show in Device List** to **A reading** for a temperature, light or distance sensor, or **Open/closed or motion** for a door, window or motion sensor.
5. Click **Save**.

The plugin reads every value the sensor reports, using the names the gateway gives them. It sets up the gateway to call Indigo whenever a reading changes, and also checks the gateway at the pace set by **Check Every** — once a minute to start with.

| Shown as | What it means |
|---|---|
| **On / Off** | Open or closed, or motion or none, when **Show in Device List** is set to **Open/closed or motion**. |
| **Temperature (C)**, **Humidity (%)** | From a BLU H&T. |
| **Light (lux)** | Light level, from sensors that report it. |
| **Distance (mm)** | From a BLU Distance. |
| **Rotation (degrees)** | From sensors that report an angle. |
| **Battery (%)** and **Signal (dBm)** | The sensor's battery and Bluetooth signal. |
| **Last Report** | When the gateway last heard from the sensor. |

Anything else the sensor reports is added as an extra state under the gateway's own name for it.

A sensor that the gateway has not heard from for 12 hours is marked offline. That uses the same **Battery Sensor Stale Threshold** setting as the other battery sensors.

If the gateway has no BLU device with that number, the Event Log says so and points you at **Show BLU Devices on Gateways**.

I built the BLU sensor support from Shelly's documentation and a Gen 4 gateway, but I have no BLU sensor here to test it with, so I would be glad to hear how it goes with yours.
