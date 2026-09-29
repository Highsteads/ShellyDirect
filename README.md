# Shelly Direct for Indigo

**Control and watch the Shelly Plus, Pro, Gen 3 and Gen 4 range from Indigo, straight over your home network.**

**Version:** 4.3.2 | **Author:** CliveS & Claude | **Needs:** Indigo 2022.1 or later

**[Read the full guide](https://highsteads.github.io/ShellyDirect/)** — setting up, what everything means, and what to do when something goes wrong.

---

## What it does

This plugin lets [Indigo](https://www.indigodomo.com) control the newer Shelly devices. It talks to each one directly over your home network, so there is no Shelly account involved and nothing goes out to the internet.

- **Switches, dims and colours** your Shellys from Indigo, a control page, a schedule or a trigger, the same as any other Indigo device, and drives blinds and shutters.
- **Finds your Shellys for you.** One menu item scans your network and creates a device of the right kind for each Shelly, one per output on a Shelly with several.
- **Shows each change the moment it happens,** because the plugin keeps a live connection open to every Shelly — a switch at the wall, a button press or a change in power.
- **Tells you who switched it** — Indigo, the button on the plug, the Shelly app, its own timer, or starting up after a power cut — and can run a trigger when anything other than Indigo switches it.
- **Counts the energy each plug uses,** today and this month, keeps 30 days of history, and can warn you when a plug draws more than you expect.
- **Shows the electricity price on your plugs' LED rings** — green at the cheap rate, amber at the standard rate, red at the peak rate.
- **Keeps safety settings on the plug itself,** such as turning off after so many minutes or cutting the power above a set load, so they keep working when Indigo is down.
- **Updates your Shellys' firmware** from Indigo, one at a time, leaving alone any you have told it to hold.
- **Knows each Shelly by the number it was made with,** so if your router gives a Shelly a new address the plugin finds it again, and never records one Shelly's readings against another.
- **Keeps the log tidy.** When several Shellys drop off the network together, you get one line saying so rather than a warning for each.

## Which Shellys it works with

| In Indigo | Your Shelly |
|---|---|
| **Shelly Relay** | Plugs and relays — Plus Plug UK, S, IT and US, Plug S Gen 3, the 1 and 1PM families, and multi-output Shellys such as the Plus 2PM and Pro 4PM (one device per output) |
| **Shelly Cover / Roller** | A two-output Shelly set up to drive a blind, shutter or gate |
| **Shelly Dimmer** and **Shelly RGBW** | The Plus, Gen 3 and Gen 4 dimmers, the Pro Dimmer, and the Plus RGBW PM |
| **Shelly Energy Meter** | Pro EM, EM Gen 3, Pro 3EM, Pro 3EM-400, 3EM Gen 3 |
| **Shelly Plus Uni** and **Shelly Plus i4** | The Plus Uni, and the Plus i4, i4 DC and i4 Gen 3 |
| **Shelly H&T Sensor**, **Shelly Smoke Detector**, **Shelly Flood Sensor** | Plus H&T and H&T Gen 3, Plus Smoke, Flood Gen 4 |
| **Shelly BLU Button**, **BLU RC Button 4** and **BLU Sensor** | Shelly BLU buttons and sensors, through a mains Shelly nearby |

A newer model that is not in the list is set up from what it reports it can do. The [guide](https://highsteads.github.io/ShellyDirect/devices.html) has the full list.

For the older Gen 1 Shellys, such as the original Shelly 1, use my other plugin, [Shelly Gen 1](https://github.com/Highsteads/ShellyGen1).

## Installing

1. Go to the [Releases page](https://github.com/Highsteads/ShellyDirect/releases/latest) and download `ShellyDirect.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `ShellyDirect.indigoPlugin`
3. Double-click `ShellyDirect.indigoPlugin` — Indigo will install it automatically

## Setting it up

1. Open **Plugins → Shelly Direct → Configure**, fill in **Indigo Server IP** with the network address of the Mac that runs Indigo, and **Discovery Subnets** with the first three numbers of your Shellys' addresses, such as `192.168.1`. Click **Save**.
2. Choose **Plugins → Shelly Direct → Discover Shelly Devices**. The plugin scans your network and creates a device for each Shelly it finds, in a device folder called **ShellyDirect**.
3. Switch a plug with its own button or the Shelly app, and Indigo should show the change straight away.

Battery sensors sleep, so discovery usually misses them. Add those by hand with **New Device**. The [full guide](https://highsteads.github.io/ShellyDirect/) goes through each step, explains every setting, and covers what to do if something does not work.

## What's new

**v4.3.2** — Fewer false alarms at midnight. Plugs no longer log "cumulative energy went backwards" when the first reading after midnight comes in a fraction of a watt-hour below the new day's starting point. The energy figures were never wrong, only the warning.

**v4.3.1** — No change to how the plugin works. Two notes in the code now explain why the relay list for the Switched Outside Indigo trigger, and discovery, include disabled devices.

**v4.3.0** — The smoke and flood alarms, the i4's first input and the energy meter's total power now show in Indigo, and the H&T, Smoke and Flood report their battery. A new **Accept Replaced Shellys** menu item lets a device take on a Shelly you have swapped for a new one. A plug with a High Power Alert no longer reports a false problem when a reading comes without a power figure. BLU buttons no longer write a reading that went nowhere on every press.

**v4.2.0** — A new **Set Firmware Hold** action ticks or unticks **Hold Firmware** on a device, so it can be changed from a schedule or a script as well as the device dialog.

**v4.1.0** — Two new menu items, **Show Electricity Price on All Plugs** and **Stop Showing Electricity Price on Plugs**, set the price light on every plug with an LED ring at once. The LED ring, colour and switch-settings commands now work, and "- none -" in the price menus really means none.

Every version is listed in the [version history](https://highsteads.github.io/ShellyDirect/changelog.html).

## Authors & licence

Vibed into existence by **CliveS**, who knew what he wanted, argued until he got it, and tested it on a real house. Typed at inhuman speed by **Claude** (Anthropic), who mostly did as it was told.

© 2026 CliveS · [MIT licence](LICENSE) — copy it, fork it, bend it, break it, fix it, ship it. If it breaks, you get to keep both pieces.
