# Gree Zone Controller for Home Assistant

Local control of the **Gree LE60-13/GH zone control system** (sold in Australia
and New Zealand, also under Seeley/Braemar) through its optional **ME31-00/C13
WiFi module**, using the same LAN protocol as the Gree+ app. No cloud.

The stock Home Assistant Gree integration and the popular custom Gree
components treat every Gree device as a single split-system AC. The zone
controller is different: it is a *gateway* with one sub-unit for the ducted AC
and one per zone, it uses its own mode numbering and its own column names, and
its WiFi module is fragile. This integration handles all of that.

## Entities

| Entity | What it does |
| --- | --- |
| `climate` | AC power, mode (Cool / Heat / Dry / Fan / Auto) and fan speed (Auto, Low … High, Turbo in Cool/Heat). Attribute `setpoint_memory` shows the remembered per-mode setpoints, in the controller's unit. |
| `switch` **System** | Whole-system power. Zones keep their own on/off setting while the system is off, exactly like the wall panel. |
| `switch` per zone | Opens/closes the zone. Zones marked *always open* get no switch: turning them off is refused by the controller or shuts the whole system down. |
| `number` per zone | Zone target temperature in the controller's unit: 16–30 °C in half degrees, or 61–86 °F. Home Assistant shows it in your own unit. The wall panel shows only whole degrees in °C, so it shows 18 for 18.5. |
| `select` **Temperature unit** | °C or °F for the whole controller, wall panel included. |

### Per-mode setpoint memory

The wall panel remembers each zone's setpoint per mode and recalls them when
you change mode **on the panel**. Mode changes over WiFi (Gree+ app, Home
Assistant) bypass that, so the integration keeps its own copy:

* it learns each zone's setpoint per mode from every change, whether made in
  Home Assistant, on the panel or in the app;
* before Home Assistant changes the mode it snapshots the current setpoints
  under the outgoing mode, then sends the incoming mode's saved setpoints;
* it keeps the half-degree/°F bit with each setpoint, so 18.5 °C or 67 °F
  comes back exactly;
* the memory survives restarts (`.storage/gree_zone.<entry_id>.setpoints`).
  A memory saved by version 0.1 is converted when it is loaded.

A mode's values are learned once the system has run in that mode for one poll.

### Not available: current zone temperatures

The panel shows each zone's ambient temperature, but the WiFi module never
exposes it: no released firmware (v1.21, v1.27, v1.28) has a field for it and
there is no raw pass-through. See [docs/PROTOCOL.md](docs/PROTOCOL.md#zone-ambient-temperatures)
for where the values actually travel and the hardware options for reading them.

## Installation

1. Pair the zone controller's WiFi module with the Gree+ app as usual.
2. Install it, then restart Home Assistant:
   * **HACS:** HACS → ⋮ → *Custom repositories* → add
     `https://github.com/Twintop/ha-gree-zone-controller` as an *Integration*,
     then download **Gree Zone Controller**; or
   * **manually:** copy `custom_components/gree_zone` into your Home Assistant
     `config/custom_components/` folder.
3. **Settings → Devices & services → Add integration → Gree Zone Controller**,
   enter the WiFi module's IP address, then name your zones and tick the
   always-open zone(s) (zone 1 by default).

Give the module a fixed IP (DHCP reservation).

## Notes

* Polls every 10 s with requests of at most 20 columns. **Larger requests make
  the WiFi module drop them, and much larger ones reboot it** (it then takes a
  while to reconnect to Gree's cloud) — please keep that limit if you extend
  this.
* New values are held in Home Assistant until the controller confirms them, so
  the UI doesn't bounce back while the controller is applying a change.
* If the module is re-paired in Gree+ and its key changes, the integration
  re-binds automatically.
* Local only. You can remove the controller from your Gree+ account after
  pairing, and local control keeps working. A cloud-only setup in another
  integration can't control it: the WiFi module uses an older Gree cloud
  protocol, not MQTT. See [docs/PROTOCOL.md](docs/PROTOCOL.md#gree-cloud).

## Upstream

The same support is in the process of being ported to RobHofmann's
[HomeAssistant-GreeClimateComponent](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent)
5.0 rewrite (`gree_custom`), with tests. See [upstream/README.md](upstream/README.md).

## Repository layout

```
custom_components/gree_zone/   the integration
docs/PROTOCOL.md               everything known about the device and protocol
tests/                         setpoint-memory tests against a simulated controller,
                               and the °C/°F setpoint conversions
tools/gree_probe.py            CLI to scan / bind / list sub-units / read / write columns
tools/firmware_fields.py       list the column names a module firmware supports
upstream/                      notes and patch for the port to gree_custom (5.0)
```

Tests: `pip install cryptography pytest && pytest`.

Tested with: LE60-13/GH, WiFi module firmware `362001062617` v1.27
(`U-W05SAV1.27`), Home Assistant 2026.10.

## License

MIT, see [LICENSE](LICENSE).

Not affiliated with or endorsed by Gree. Gree and the Gree logo, used as the
integration's icon, are trademarks of Gree Electric Appliances, Inc. of Zhuhai.
