---
title: Getting started
nav_order: 2
---

# Getting started

This takes about ten minutes, and you only do it once.

## What you need

- Indigo 2022.1 or later, on a Mac that is on the same home network as your Shellys.
- One or more Shelly Plus, Pro, Gen 3 or Gen 4 devices already joined to your Wi-Fi, which you do with the Shelly app or the Shelly's own web page when you first unbox it.
- The **network address** of the Mac that runs Indigo. This is the set of four numbers separated by dots, such as `192.168.1.5`. You can find it in **System Settings → Network** on that Mac.
- The first three of those four numbers for the part of the network your Shellys are on, such as `192.168.1`. The plugin scans that range to find them.

It helps to ask your router to keep giving each Shelly the same address, which most routers call a **reserved address** or **DHCP reservation**. The plugin copes if an address changes, but it copes faster if it never does.

Each Shelly also needs to be able to reach the Indigo Mac on port 8178 — the number the plugin listens on for messages from your Shellys. On an ordinary home network with no firewall between the two, there is nothing to do.

## 1. Install the plugin

1. Go to the [Releases page](https://github.com/Highsteads/ShellyDirect/releases/latest) and download `ShellyDirect.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `ShellyDirect.indigoPlugin`
3. Double-click `ShellyDirect.indigoPlugin` — Indigo will install it automatically

Indigo asks whether to enable the plugin. Say yes. Indigo then fetches the two small extras the plugin uses, which takes a moment the first time.

## 2. Tell the plugin about your network

Open **Plugins → Shelly Direct → Configure** and fill in two things:

- **Indigo Server IP** — the network address of the Mac that runs Indigo. Your Shellys use it to send changes to Indigo.
- **Discovery Subnets** — the first three numbers of your Shellys' addresses, such as `192.168.1`. If your Shellys are spread over more than one part of the network, put each one in, separated by commas, such as `192.168.1, 192.168.10`. The dialog will not save without one.

Leave everything else as it is to start with, and click **Save**. Every setting is explained on the [Settings](settings.md) page.

If your Shellys have a password set on them, fill in **Shelly Username** and **Shelly Password** as well. All your Shellys must share the same one.

## 3. Find your Shellys

Choose **Plugins → Shelly Direct → Discover Shelly Devices**.

The plugin tries every address from `.1` to `.254` in each range you gave it, which takes a minute or two, and writes its progress to the Event Log. For each Shelly it finds, it creates an Indigo device of the right kind in a device folder called **ShellyDirect**:

- A plug or relay becomes a **Shelly Relay**.
- A Shelly with two or more outputs becomes one device for each output, named **Ch1**, **Ch2** and so on.
- A two-channel Shelly set up to drive a blind becomes one **Shelly Cover / Roller**.
- A dimmer, colour light, energy meter, i4 or Uni becomes the matching device.

The device takes the name you gave the Shelly in the Shelly app, or the model and the last number of its address if you never named it. Rename them in Indigo as you like.

When the scan finishes, the Event Log says how many Shellys it found and how many devices it created. It also names any device you already had in that range that did not answer.

Battery sensors such as the H&T, Smoke and Flood sleep between readings, so the scan usually misses them. Add those by hand, as below, after pressing the sensor's button to wake it.

## Adding a Shelly by hand

1. In Indigo, choose **New Device**.
2. Set **Type** to **Shelly Direct**, then pick the model — the [Your devices](devices.md) page says which to choose.
3. Type the Shelly's network address into **IP Address**. The Shelly app shows it under the device's settings.
4. On a Shelly with more than one output, pick the **Channel**, and make one device for each output.
5. Click **Save**.

## 4. Check it works

Within a few seconds each new device shows its state in Indigo's device list — on or off, a brightness, or a reading.

Now switch a plug with its own button, or from the Shelly app. Indigo should show the change straight away.

If you want a single check of the whole set-up, choose **Plugins → Shelly Direct → Test Shelly Connection**. It writes a summary to the Event Log, tries every Shelly, and ends with **Connection test PASSED** or a list of what is wrong.

If nothing appears, the [When something goes wrong](troubleshooting.md) page goes through the usual causes.
