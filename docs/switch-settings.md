---
title: Switch settings on the Shelly
nav_order: 8
---

# Switch settings on the Shelly

A Shelly relay can hold a few safety settings of its own. Because the Shelly enforces them itself, they keep working when Indigo, the plugin or your network is down. The plugin lets you set them from Indigo, so they are written down in one place and put back if anything changes them.

## The settings

Double-click a Shelly Relay in Indigo and tick **Manage Switch Settings from Indigo**. Four more fields appear:

| Setting | What it does |
|---|---|
| **Turn Off After (minutes)** | The relay turns itself off this long after being turned on, however it was turned on. Leave it blank, or put 0, for never — and the plugin then switches off any timer already set on the Shelly. |
| **Cut Power Above (W)** | The relay turns off if the load draws more than this many watts. Leave it blank to keep the Shelly's own limit. |
| **Cut Power Above (A)** | The same, in amps. Leave it blank to keep the Shelly's own limit. A Plus Plug UK allows up to 3000 W and 13 A. |
| **After a Power Cut** | What the relay does when the power comes back: **Stay off**, **Come on**, **Go back to how it was**, or **Follow its switch**. **Leave as set on the device** leaves it alone. |

Click **Save**. The plugin sends only what has changed, and the Event Log says what it set, such as "set on the device: cut the power above 2000 W".

## Keeping them in place

Every six hours the plugin reads the settings back from each Shelly it manages and puts right any that something else has changed — the Shelly app, or a Shelly that has been reset. It says so in the Event Log when it does. When all is well it says nothing.

Untick **Manage Switch Settings from Indigo** and the plugin stops managing them. The Shelly keeps whatever it was last set to.

If a setting cannot be made, the Event Log has a warning naming the relay.
