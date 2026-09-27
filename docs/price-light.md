---
title: The price light
nav_order: 7
---

# The price light

The Plus Plug UK and the Plug S have a ring of light round the socket. The plugin can colour that ring by the price of electricity, so you can see at a glance whether now is a good time to put the washing on:

| Ring colour | Means |
|---|---|
| **Green** | The cheap rate — below **Cheap Below**, 20p a unit to start with |
| **Amber** | The standard rate — anything between the two |
| **Red** | The peak rate — above **Peak Above**, 30p a unit to start with |

The ring is bright while the plug is switched on, and dim while it is off, so you can still tell which plugs are on.

## What it needs

The plugin does not fetch prices itself. It reads them from an Indigo variable that something else keeps up to date — another plugin, or a script of your own. It can use either or both of these:

- **A list of the day's rates**, in the form Octopus Energy publishes them: a list in JSON text with a start time, an end time and a price including VAT for each period, under the names `valid_from`, `valid_to` and `value_inc_vat`. With this, the ring changes on the minute the rate does. You can give it today's rates and tomorrow's rates in two separate variables.
- **The price now**, as a number of pence per unit. The plugin uses this when there is no list, or when the list does not cover the present moment.

## Setting it up

1. Open **Plugins → Shelly Direct → Configure** and tick **Show Electricity Price on Plug LED Rings**.
2. Choose the variables in **Today's Rates (variable)**, **Tomorrow's Rates (variable)** and **Current Price (variable)**. Leave any you do not use on **- none -**.
3. Set **Cheap Below (p/kWh)** and **Peak Above (p/kWh)** to suit your tariff, and click **Save**.
4. Choose **Plugins → Shelly Direct → Show Electricity Price on All Plugs**. The Event Log says which plugs now show the price, and which have no ring.

To do it one plug at a time instead, double-click the plug in Indigo and tick **Show Electricity Price on LED Ring**.

## How it behaves

- The plugin works out the price once a minute, and changes the ring only when the band changes.
- A plug that is switched off at the wall, or away, is brought up to date when it comes back.
- The first time the plugin colours a ring, it notes how the ring was set up, and puts it back exactly as it was when you untick the plug or choose **Plugins → Shelly Direct → Stop Showing Electricity Price on Plugs**.
- Untick **Show Electricity Price on Plug LED Rings** in the plugin's settings and every ring goes back to how it was.
- If the menu item cannot reach a plug to find out whether it has a ring, it ticks it anyway, and the ring shows the price when the plug is back, if it has one.
- Each time the band changes, the plugin's own log notes the new rate and the price.
