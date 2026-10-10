# Porting zone controller support to RobHofmann/HomeAssistant-GreeClimateComponent

Everything learned in this project, ported onto the 5.0 rewrite of
[RobHofmann/HomeAssistant-GreeClimateComponent](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent)
(domain `gree_custom`), so zone controllers can be supported in one place.
Work happens on branches of the fork
[Twintop/HomeAssistant-GreeClimateComponent](https://github.com/Twintop/HomeAssistant-GreeClimateComponent).

## Where things stand

**Merged upstream** (preparation, found while porting):

| PR | What |
| --- | --- |
| [#547](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent/pull/547) | Accept a scan reply without `cid` (the zone controller sends none, so it could not be discovered) |
| [#548](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent/pull/548) | DHCP step: look up the sub-unit by its own MAC, and deep-copy the entry data so a new IP is saved |
| [#549](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent/pull/549) | Climate: skip a device without modes instead of stopping; offer target temperature and swing only when the unit has them |

**Remaining: three PRs**, each built on the one before:

| PR | Branch | What | Status |
| --- | --- | --- | --- |
| 4 | [`zone-controller-support`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-controller-support) | Zone controller support, with a `DeviceType` for every device and the gateway device labelled as a zone controller | in progress |
| 5 | [`zone-setpoint-memory`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-setpoint-memory) | Remember the zone target temperatures per mode, with storage keyed by device so PR 6 only adds | in progress |
| 6 | [`setpoint-memory-all-devices`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/setpoint-memory-all-devices) | Remember the target temperature per mode on every device that has one (opt-in per device) | planned |

## The plan

### Why three PRs

Review of #547–#549 brought two suggestions from @p-monteiro
([#549](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent/pull/549)):
give every device a type instead of a zone-only role, and remember the target
temperature per mode on every device, not only zones. They were weighed before
the zone PRs were opened:

* **`DeviceType` goes into PR 4.** It is a widening of the zone role (37
  references in 9 files), with no change of design: the type is still found at
  runtime after the info fetch, with no config entry change. Doing it after the
  merge would only touch the same lines again. It also lets the gateway device be
  labelled correctly: the zone controller showed up as a "VRF gateway".
* **Memory for every device is its own PR (6).** It changes behaviour for every
  split and VRF owner, a unit's target temperature has half degrees and a
  Fahrenheit table, Auto ignores the target, and it can only be tried on hardware
  this project does not have. Kept separate, it can't hold up the zone controller
  work, which is verified on real hardware.
* **PR 5 is shaped so PR 6 only adds.** Its storage is keyed by device and holds
  the raw target temperature columns, and the class has a generic name. No
  storage migration is needed later.
* **Not four PRs.** A `DeviceType`-only PR first would be a refactor with nothing
  using it yet, and PR 4 would have to be rebuilt on it anyway: more review
  rounds, no less risk.

### PR 4: Support Gree zone controllers

* **Protocol layer (`aiogree`)**
  * `DeviceType` for every device, found after the info fetch: `ac_unit` (a
    standalone unit), `vrf_unit` (an indoor unit behind a VRF gateway),
    `zone_controller` (sub-unit `00` of a zone controller, the ducted unit that
    owns mode and fan) and `zone` (sub-units `01` to `08`). A sub-unit of a zone
    controller reports the controller's name (`GR-ZCntrlr…`), and the MAC suffix
    tells the two apart. No config entry change, no migration. Only the zone
    controller types change behaviour; `ac_unit` and `vrf_unit` work as before.
  * Mode translation for the zone controller numbering (1 Cool, 2 Heat, 3 Dry,
    4 Fan, 5 Auto), turbo as `WdSpd` 6 (no `Tur` column), leaving Cool/Heat
    drops turbo to High.
  * `GreeProp.ZONE_TARGET_TEMPERATURE = "StTem"` (°C − 16), polled **only** by
    zones (`DeviceState.add_polled`), so other units send exactly the same
    columns as before (there is a test for that). Getter/setter clamp to
    16–30 °C.
  * Discovery names the sub-units `AC unit`, `Zone 1` … instead of five times
    `zone`.
* **Home Assistant layer**
  * Zones get no climate entity; they get a **switch** (named like the zone) and
    a **Target Temperature** number.
  * The zone switch is the optional feature **Zone Switch**, so it can be left
    out for an always-open zone. The feature is only offered on zones; zones
    don't show the climate options.
  * `GreeEntityDescription.device_filter`: a small generic hook so an entity can
    be limited to a kind of device when the props alone can't tell.
  * The gateway device of a zone controller is labelled "Zone controller"
    instead of "VRF gateway".
* **Tests**: `tests/fakes/zone.py` (a fake controller that behaves like the real
  one: subDev only, no `cid`, per-unit columns, mirrored mode/fan, column cap)
  and `tests/test_zone_controller.py`.
* **Docs**: `docs/protocol.md`, `docs/entities.md`, `docs/configuration.md`,
  `docs/architecture.md`, `supported-devices.md`.

### PR 5: Remember zone target temperatures per mode

* `SetpointMemory` in `aiogree/setpoint_memory.py`, the per-mode memory the wall
  panel has: learn from polls once a zone reports the same mode twice; before a
  mode change from Home Assistant, read the zones again and store them under the
  old mode; after it, send the stored values of the new mode.
* Storage keyed by device: `{device MAC: {mode: {column: raw value}}}`, for a
  zone `{"StTem": 4}`. A standalone unit can later store `SetTem` and `TemRec`
  the same way, without conversions and without a migration.
* `__init__.py` keeps it in a `Store` per config entry
  (`.storage/gree_custom.<entry_id>.setpoints`) and feeds it from the zone
  coordinators. No Home Assistant imports in the memory itself; fully tested.

### PR 6: Remember the target temperature per mode on every device

* A device option, **Remember the target temperature per mode**, for units that
  have a target temperature. Off by default, because it changes how the unit
  behaves after a mode change.
* Learns from the unit's own polls (mode and `SetTem`/`TemRec` come in one
  reply). On a mode change from Home Assistant, the stored target of the new
  mode goes out in the same command as the mode.
* No recall into Auto for these units: in Auto the unit ignores the target
  temperature.
* Raw columns are stored, so a unit set to Fahrenheit needs no conversion.
* Tested against fakes only; a split or VRF owner should try it before merge.

## Testing a branch in Home Assistant without the UI

The 5.0 integration also reads a `gree_custom:` block from `configuration.yaml`
and creates its config entry at startup, which is handy for testing a branch on a
real system. Copy `custom_components/gree_custom` from the branch into your
config folder, then add for example:

```yaml
gree_custom:
  - devices:
      "<controller mac>00@<controller mac>":          # the AC unit
        connection: {scan_interval: 30, local: {host: "<controller ip>", encryption_version: "1"}}
        options: {name: "Test AC unit", restore_states: false}
      "<controller mac>01@<controller mac>":          # zone 1, always open: no zone switch
        connection: {scan_interval: 30, local: {host: "<controller ip>", encryption_version: "1"}}
        options: {name: "Test Zone 1", features: [], restore_states: false}
      "<controller mac>02@<controller mac>":          # zone 2
        connection: {scan_interval: 30, local: {host: "<controller ip>", encryption_version: "1"}}
        options: {name: "Test Zone 2", features: [zone], restore_states: false}
```

`restore_states: false` keeps a test install from pushing old states to the real
controller after a restart. With PR 5 the per-mode memory is stored in
`.storage/gree_custom.<entry_id>.setpoints`.

Home Assistant shows a **"legacy folder"** repair while an old 4.x
`custom_components/gree` folder exists. That is upstream asking you to remove the
old version, not a problem with the branch.

Running this next to `gree_zone` doubles the polling of the fragile WiFi module.
Keep only one of them long-term.

## Running the upstream tests on Windows

The suite puts `custom_components/gree_custom` on `sys.path`, and its
`select.py` shadows the stdlib `select` extension module on Windows (on Linux
`select` is built in). Import `asyncio` before pytest changes the path:

```python
# run_pytest.py
import asyncio, select, selectors, sys  # noqa
import pytest
sys.exit(pytest.main(sys.argv[1:]))
```

Python 3.14 is required (PEP 758 syntax); `uv python install 3.14` works.
