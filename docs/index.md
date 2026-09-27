---
title: Home
nav_order: 1
---

# Shelly Direct for Indigo

This plugin lets [Indigo](https://www.indigodomo.com) control and watch the newer Shelly devices — the Plus and Pro ranges and the Gen 2, Gen 3 and Gen 4 models — straight over your home network. There is no Shelly account involved, nothing goes out to the internet, and nothing sits in between. Indigo talks to each Shelly directly.

It looks after most of the Shelly range:

- **Plugs and relays**, such as the Plus Plug UK or the Shelly 1PM, which switch something on and off and, on most models, measure the power it uses.
- **Dimmers and colour lights**, such as the Dimmer Gen 3 or the Plus RGBW PM.
- **Blinds and shutters** driven by a two-channel Shelly set up as a cover.
- **Energy meters**, such as the Pro 3EM, which clamp round a cable and measure what flows through it.
- **Input devices and sensors** — the i4, the Plus Uni, the H&T, the Smoke and the Flood.
- **Shelly BLU Bluetooth buttons and sensors**, which reach Indigo through a mains Shelly nearby.

If your Shellys are the older Gen 1 models, such as the original Shelly 1, you want my other plugin, [Shelly Gen 1](https://github.com/Highsteads/ShellyGen1), instead.

## What it does for you

- **Switches your Shellys** from Indigo, from a control page, from a schedule or from a trigger, the same way you switch any other Indigo device.
- **Finds your Shellys for you.** One menu item scans your network and creates an Indigo device for each Shelly it finds, of the right kind.
- **Shows each change the moment it happens.** The plugin keeps a live connection open to every Shelly, so a switch flipped at the wall, a button press or a change in power reaches Indigo straight away.
- **Tells you who switched it** — Indigo, the button on the plug, the Shelly app, the plug's own timer, or the plug starting up after a power cut — and can run a trigger when anything other than Indigo switches it.
- **Counts the energy each plug uses**, today and this month, keeps 30 days of history, and can warn you when a plug draws more than you expect.
- **Shows the electricity price on your plugs' LED rings** — green at the cheap rate, amber at the standard rate and red at the peak rate.
- **Keeps safety settings on the plug itself**, such as turning off after so many minutes or cutting the power above a set load, so they keep working when Indigo is down.
- **Updates your Shellys' firmware** from Indigo, one at a time, and leaves alone any you have told it to hold.
- **Knows each Shelly by the number it was made with**, so if your router gives a Shelly a new address the plugin finds it again, and it never records one Shelly's readings against another.
- **Keeps the log tidy.** When several Shellys drop off the network together, you get one line saying so rather than a warning for each.

## Where to go next

| If you want to... | Read |
|---|---|
| Install the plugin and add your Shellys | [Getting started](getting-started.md) |
| Know what each device shows in Indigo | [Your devices](devices.md) |
| Understand what the plugin is doing behind the scenes | [How it works](how-it-works.md) |
| Know about the live connection to each Shelly | [The live connection](live-connection.md) |
| Track the energy your plugs use | [Energy tracking](energy.md) |
| Show the electricity price on your plugs | [The price light](price-light.md) |
| Keep safety settings on the plug itself | [Switch settings on the Shelly](switch-settings.md) |
| Update your Shellys' firmware | [Firmware updates](firmware.md) |
| Add Shelly BLU buttons and sensors | [BLU buttons and sensors](blu-devices.md) |
| Switch things from triggers, schedules and action groups | [Actions and triggers](actions-and-triggers.md) |
| Know what every setting does | [Settings](settings.md) |
| Know what each item in the Plugins menu does | [The plugin menu](plugin-menu.md) |
| Sort out a problem | [When something goes wrong](troubleshooting.md) |
| See what changed in each version | [Version history](changelog.md) |

## Download

The latest version is always on the [Releases page](https://github.com/Highsteads/ShellyDirect/releases/latest).
