---
title: The plugin menu
nav_order: 13
---

# The plugin menu

These are under **Plugins → Shelly Direct**. The ones that talk to every Shelly run in the background and write their results to the Event Log, so Indigo stays usable while they work.

| Menu item | What it does |
|---|---|
| **Discover Shelly Devices** | Scans the ranges in **Discovery Subnets** and creates an Indigo device for each new Shelly it finds, in the **ShellyDirect** device folder. A Shelly that has moved to a new address has its device updated rather than a second one made. At the end it names any of your devices in that range that did not answer. See [Getting started](getting-started.md). |
| **Show mDNS Discovered Shellys** | Lists every Shelly announcing itself on your network, with its MAC address, its current address and the Indigo device it matches. A device whose stored address is out of date is marked as such. |
| **Device Health Summary** | Writes a table of every device — its address, kind, whether it is online, its firmware version, and when it was last heard from. |
| **Check Firmware Versions** | Asks every Shelly whether a firmware update is waiting, and says for each. |
| **Update Firmware on All Devices** | Updates every Shelly in turn, skipping any with **Hold Firmware** ticked. See [Firmware updates](firmware.md). |
| **Show BLU Devices on Gateways** | Lists every BLU device paired with each of your gateway Shellys, with the number to put in **BTHome Device ID** and what it reports. See [BLU buttons and sensors](blu-devices.md). |
| **Show Electricity Price on All Plugs** | Ticks **Show Electricity Price on LED Ring** on every plug that has an LED ring. See [The price light](price-light.md). |
| **Stop Showing Electricity Price on Plugs** | Unticks it on every plug and puts the rings back as they were. |
| **Reconfigure Webhooks (All Devices)** | Sets up the webhooks on every Shelly again, which helps after a change to your network. It says how many it did. |
| **Export Energy History to CSV** | Writes the last 30 days of energy use for each device to a spreadsheet file. See [Energy tracking](energy.md). |
| **Toggle Timestamps in Log (on/off)** | Every line the plugin writes to the log starts with the time to the thousandth of a second, which helps when lining events up. This turns that on or off. It stays as you leave it. |
| **Test Shelly Connection** | Writes the plugin's details to the Event Log, then checks the Indigo server address, the webhook listener, the discovery ranges, tries every mains Shelly, and ends with **Connection test PASSED** or a list of what is wrong. This is the one to run before asking for help. |
| **Show Plugin Info** | Writes the plugin's version, details of your Mac and Indigo, and a summary of the plugin's state — how many devices and how many online, how many live connections are up, and whether the webhook listener is running — to the Event Log. |
