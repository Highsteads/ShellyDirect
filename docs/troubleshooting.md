---
title: When something goes wrong
nav_order: 14
---

# When something goes wrong

Each section starts with what you see, then what it means and what to do.

## A device shows Device Online false

The Shelly has missed three checks in a row, or nothing has been heard from it for the **Offline Detection Threshold**.

- Check it has power, and that the Shelly app can see it.
- Choose **Plugins → Shelly Direct → Show mDNS Discovered Shellys**. If the list says the device's stored address is out of date, the plugin moves the device to the new address by itself. **Discover Shelly Devices** does it at once.
- If the plug is switched off at the wall on purpose between uses, tick **Suppress Offline Alerts** in its settings, so it goes offline quietly.

When it answers again, **Device Online** goes back to true by itself.

## The log says several Shelly devices stopped answering together

Three or more Shellys dropped off within three minutes of each other. That is almost always the Wi-Fi or the router rather than the Shellys. Check your access points and router, and the Shellys come back by themselves when the network does.

## The log says "wrong device at" an address

A different Shelly is answering at this device's address. Nothing from it is recorded, so its readings cannot end up on the wrong device.

- If your router has moved the Shelly to a new address, the plugin looks for it and updates the device itself — give it a few minutes, or run **Discover Shelly Devices**.
- If you have replaced the Shelly with a new one at the same address, the new one has a different MAC address, so the plugin will not take it as the old one until you tell it to. Choose **Plugins → Shelly Direct → Accept Replaced Shellys**. The device keeps its name, triggers, schedules and control pages, and takes on the new Shelly. The plugin checks first that the new Shelly is answering and that the old one has not simply moved to another address, and says in the Event Log what it did.

## A switch at the wall takes a while to show in Indigo

Neither the live connection nor the webhooks are reaching Indigo, so the change waited for the next check.

- Check **Indigo Server IP** in **Plugins → Shelly Direct → Configure** is the address of the Mac that runs Indigo.
- Run **Plugins → Shelly Direct → Test Shelly Connection** and read what it says about the webhook listener.
- Check nothing between your Shellys and the Indigo Mac, such as a firewall, blocks port 8178.
- Run **Plugins → Shelly Direct → Reconfigure Webhooks (All Devices)**.
- Choose **Show Plugin Info** and look at the **Live Connections** line. If it says none are up, check **Live Connection to Each Shelly** is ticked, and remember it is not used while **Shelly Username** and **Shelly Password** are set.

## The log says "Could not start webhook listener on port 8178"

Something else on the Mac is already using that port. Choose another number, such as 8180, in **Webhook Listener Port**, click **Save**, and restart the plugin with **Plugins → Shelly Direct → Reload**. Your Shellys are pointed at the new number by themselves.

## The log says "Webhooks skipped - no Indigo server IP configured"

Fill in **Indigo Server IP** in **Plugins → Shelly Direct → Configure**, or in the shared settings file described on the [Settings](settings.md) page.

## Discovery finds nothing

- Check **Discovery Subnets** holds only the first three numbers, such as `192.168.1`, not `192.168.1.0`.
- Check your Shellys really are in that range — the Shelly app shows each one's address.
- Discovery only finds Plus, Pro, Gen 3 and Gen 4 Shellys. The older Gen 1 models need my [Shelly Gen 1](https://github.com/Highsteads/ShellyGen1) plugin.
- Battery sensors are usually asleep. Add them by hand.

## A battery sensor says "Sensor webhook not configured (device likely asleep)"

The sensor was asleep when the plugin tried to set it up. Press the sensor's button to wake it, then straight away choose **Plugins → Shelly Direct → Reconfigure Webhooks (All Devices)**. The log line also gives the web address, if you would rather put it into the sensor's own settings by hand.

## A plug's price light does not change

- Check **Show Electricity Price on Plug LED Rings** is ticked in the plugin's settings, and that at least one price variable is chosen.
- Check the variable holds a price — a number of pence, or a list of rates that covers the present moment.
- Only the Plus Plug UK and the Plug S have a ring. The menu item says which plugs have none.

## Energy Today looks wrong

- After a power cut, the plugin waits for a second reading before it believes a Shelly's total has gone back to zero, so the figure holds still for one check.
- If the log says an earlier counter reset was a glitch and the baselines are restored, the plugin has already put it right.
- A plug that was away over midnight starts its new day when it next answers.

The [Energy tracking](energy.md) page explains how the figures are worked out.

## The log says "The live connection needs the websockets package"

Indigo has not finished installing the extra the live connection uses. The plugin keeps checking your Shellys meanwhile. Restart the plugin with **Plugins → Shelly Direct → Reload** once Indigo has finished.

## Still stuck?

Choose **Plugins → Shelly Direct → Test Shelly Connection**, copy the lines it writes to the Event Log, and post them on the [Indigo forum](https://forums.indigodomo.com) with a description of what you see. You can also [raise an issue on GitHub](https://github.com/Highsteads/ShellyDirect/issues).
