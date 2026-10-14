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

**Remaining: three PRs**, each built on the one before, all on `5.0-dev` @ `c2bc8c4`:

| PR | Branch | Commits | What | Tests | Status |
| --- | --- | --- | --- | --- | --- |
| 4 | [`zone-controller-support`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-controller-support) | `43f4881`, `d54829c`, `fe1f4de`, `5bfa6cb`, `d6abdcd`, `d666fe1`, `3a806af`, `9f11775`, `d7f57c4`, `6d4c77b`, `2f14e87`, `07f605c`, `b922a26`, `a788528`, `e21a986`, `e33b6f7`, `3f55495` | Zone controller support, a `DeviceType` for every device, the gateway labelled as a zone controller, °C and °F, target temperature columns as groups like the sensors, no error log for Quiet/Turbo on units without them, documented as local only, the cloud login kept out of logs and diagnostics, and cloud discovery keeping the sub-units of a gateway | 288 | in review: [#552](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent/pull/552), requested changes made |
| 5 | [`zone-setpoint-memory`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-setpoint-memory) | `f55ddc8`, `e41ab45`, `72ed332`, `deb83a1` | Remember the zone target temperatures per mode, stored per device as raw columns (with the half-degree/°F bit) | 297 | ready, after PR 4 |
| 6 | [`setpoint-memory-all-devices`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/setpoint-memory-all-devices) | `5f7388e` | Remember the target temperature per mode on standalone and VRF units too (opt-in) | 301 | ready, after PR 5 |

The `5.0-dev` baseline is 255 tests. Every branch passes Ruff 0.17.0 (the pinned
version), and Mypy and Pylint show nothing new compared with `5.0-dev`. Mypy
has to run with Home Assistant installed (`pip install homeassistant`, plus the
`enum_identity_compare` plugin from Home Assistant core that `mypy.ini` names).
Without it every Home Assistant type is `Any`, and real errors slip through: the
first runs here missed the one Rob found in #552.

### Review of #552

| Point | What it was | Fix |
| --- | --- | --- |
| Blocker | When a gateway had no bound sub-unit at start, `reconcile_vrf_controllers()` passed `translation_key=UNDEFINED` to the device registry. Home Assistant treats it as a key and crashes on `.format()`. The whole entry failed, and the next start failed without a retry. Reproduced on the test install with an offline fake gateway. Plain VRF users were hit too. | `5bfa6cb`: `_controller_label()` leaves model and name out when the device exists and no sub-unit is bound, and uses the VRF gateway label for a new one. The entry now loads, and the offline gateway keeps its label. |
| @p-monteiro: are all zone controllers `5000`/`5001`? | Those model ids, the `GR-ZCntrlr` name and the `00` suffix of the AC unit are fixed in the WiFi module firmware (v1.21, v1.27, v1.28), not taken from the units. The only other model found, the Braemar LE60, uses the same module. The `5000` in the name comes from a value we could not trace. | `3a806af`: `ZONE_CONTROLLER_MODELS`, one entry per model, longest matching name prefix wins. A general `GR-ZCntrlr` entry plus a `GR-ZCntrlr_5000_` one as an example. |
| @p-monteiro: wire the zone target into `target_temperature`? | Yes. | `9f11775`: zones use `target_temperature` and `set_target_temperature`. |
| Found while digging: °F | The panel can show °F, and the controller has its own `TemUnit` and `StFahFlg` columns. In °F, `StTem` + 16 and `StFahFlg` follow the `SetTem`/`TemRec` table. Sending only `StTem` keeps the old bit. | `d7f57c4`: zones read and write both columns, the zone number follows the unit (16–30 °C or 61–86 °F), and the Temperature Units select works on the AC unit. PR 5 stores the bit too (`deb83a1`). |
| @p-monteiro, round 3 (commit comments on 3a806af and d7f57c4, plus the `device.py` thread) | (1) The model table is not needed: detection is name only, why not the suffix? (2) Pick columns by what a device answers, not by type; do the controllers answer the old columns, or `Add0.5`? (3) 25.5 °C is valid: °C to the nearest half degree when supported, °F to integers. (4) The zone select filter should not be needed. | (1) `6d4c77b`: two constants (`GR-ZCntrlr`, `00`), discovery names by controller name plus suffix. (2) `2f14e87`: no sub-unit answers `SetTem`/`TemRec`/`TemUn`/`Add0.5`; `StTem`/`StFahFlg`/`TemUnit` are in the default poll and dropped where not answered; `TemUn` wins over `TemUnit`; type kept only where columns cannot tell (the AC unit answers `StTem` = 0). (3) `07f605c`: rounding moved into the device; zones do half degrees in °C (checked: 2/1 stays, panel shows 18). (4) Kept: zones answer `TemUnit`. |
| @p-monteiro, round 4 (two PR comments) | (1) Treat the target temperature, bit and unit like the sensors: numbered props, `invalidate_missing_property_group()` for all three in `_remove_unsupported_props()`, and have it return the prop that survives so the device saves it (sensors too) and uses it directly. Drop the AC unit's `StTem` 0, or use `missing_value=-1` if 0 is valid. (2) Only mids 5000/5001 answer those columns, but some units send no mid or name, so go by what answers. | (1) `b922a26`: the function returns the survivor, the sensor props are saved on the device. `a788528`: `TARGET_TEMPERATURE_1/2` (`SetTem`/`StTem`), `_BIT_1/2` (`TemRec`/`StFahFlg`), `_UNIT_1/2` (`TemUn`/`TemUnit`), saved and used directly. 0 is valid in all three (`StTem` 0 = 16 °C), so `missing_value=-1`; the AC unit's always-0 `StTem`/`StFahFlg` look like a zone at 16 °C, so it drops them by type. The bit only goes to a device that answers it (before, `TemRec` always went with `SetTem`). PR 5 memory uses the saved columns, so PR 6 no longer touches `device.py`. (2) Nothing uses the mids since `6d4c77b`. |
| @p-monteiro, round 5: test a cloud-only entry added through the UI and post the cloud discovery log; the bit also matters in °F | Cloud discovery lists 6 devices with one shared key: the gateway (`pmac` empty, mid `50`), the AC unit (`…00`, mid `5000`) and the zones (`…01`–`…04`, mid `5001`), each with `pmac` = the gateway MAC. `_filter_duplicate_devices_complete()` keeps only `…00`, and `gree_extract_macs()` only treats MACs ending in `00` as sub-units. The MQTT bind gets no reply, although the Gree+ app controls the controller over cellular: the ME31-00/C13 firmware has no MQTT client, only the older TCP cloud (`dis.gree.com`). Also found: `GreeCloudApi.login()` logs the session token and email at debug level. | `e21a986`: docs say a zone controller is local only; docstring of `has_target_temperature_bit` mentions °F. A redacted debug log of the flow was posted. Offered as a separate PR: `pmac` for the controller MAC, a `pmac`-based duplicate filter, and redacting the login log lines. |
| @p-monteiro, round 6: add the redaction (or leave it to them); with cloud and local discovery, does `gree_merge_discovered_devices()` offer the zones with local preference? For VRF, `pmac` may not be the MQTT controller, so more VRF data is needed first | Redaction went further than the login lines: setting up an entry logged its data with only the device key redacted (so for a cloud entry the password and token too), the UI new-entry log did the same, entry diagnostics kept the token and email, some lines logged the email or the entry title, and the repr of `GreeDiscoveredDevice` (logged by discovery) held the key and email. Cloud + local offered only the AC unit: local devices are only offered when the cloud lists them, and the duplicate filter had cut the cloud list to `…00`. | `e33b6f7`: login response logged as `r`/`msg`/`uid`/`alive` only, a shared `TO_REDACT` (device key, password, token, email) for the entry logs and diagnostics, user id or entry id instead of the email or title, key and email out of the repr. `3f55495`: a listed device that others point to with their `pmac` is a gateway; it is left out and its sub-units are kept, everything else goes through the key check as before. `gree_extract_macs()` left alone. |
| Question | The device options form copied the previous sub-unit's options as defaults, so Zone 1 opened with Zone Switch unticked after the AC unit, the AC unit could get `zone`, and every sub-unit got the previous one's **name**. | `d6abdcd`: only the mode lists and features are copied. `zone` is never copied, and every zone starts with Zone Switch ticked. The features default is filtered against what the device supports. |

Found on the way, already on `5.0-dev`, fixed in PR 4 (`d666fe1`):
`cleanup_device_connection_issues()` deleted repair issues while it looped over
`registry.issues`. When a removed device still had a "connection failed" issue,
the entry failed with `RuntimeError: dictionary changed size during iteration`,
and the stale gateway device stayed. It now loops over a copy. Checked on the
test install: with the offline fake gateway removed from the YAML again, the
entry loads at the next start and both the issue and the gateway device are
gone.

### Checked on the real system (Home Assistant 2026.10, LE60-13/GH)

Each branch was installed on a Home Assistant test install (YAML, next to
`gree_zone`) and driven through real service calls. After every run the
controller, the memory stores of both integrations, the test config and the
installed code were put back exactly as they were, and checked.

| PR | What was checked |
| --- | --- |
| 4 | Entities and states (AC unit: modes, fan incl. turbo, no target temperature or swing; zones: switch and 16–30 °C number). Gateway device shown as "Zone controller", with the AC unit and zones linked. Through Home Assistant: a zone target temperature, a zone switch, the fan speed, and Heat + Turbo (`Mod` 2, `WdSpd` 6), each confirmed on the controller. Found and fixed: an error log for Quiet on every fan change. |
| 5 | A mode change from Home Assistant recalls the zone setpoints of the new mode (Heat → all zones 18 °C, Fan → 20 °C), with the memory in the new per-device format. No errors. |
| 6 | The new option is accepted by the YAML schema and has no effect on the zone controller, whose recall still works. Standalone and VRF units are covered by tests against fakes only: there is no such unit here. |
| 4–6 after #552 review | With all three branches in place, from an empty memory: Fan medium and back to High (no error log); Heat with Master set to 18 °C; Fan brings Master back to 20 °C; Heat brings 18 °C back. The memory store holds `{"fan": {"StTem": 4}, "heat": {"StTem": 2}}` for Master. Gateway labelled "Zone controller c5a5f". |
| 4, °F | Over WiFi: `TemUnit=1` on the AC unit switched every unit and the panel to °F. Set on the panel: 64 °F = `StTem` 2/`StFahFlg` 0, 66 °F = 3/0, 67 °F = 3/1. Sent over WiFi: 5/1 showed 70 °F; `StTem` 6 alone kept bit 1 and showed 72 °F. Through Home Assistant with PR 4: the Temperature Units select (AC unit only) switched the controller to °F, and Master set to 21 °C went out as 70 °F (5/1). Back to °C, everything checked against the snapshot, and both integrations' memory stores put back. |
| 4–6, review round 4 | Through Home Assistant with PR 4: the AC unit polls only `Pow`, `Mod`, `WdSpd` and `TemUnit` (from diagnostics), zones keep `StTem`, `StFahFlg` and `TemUnit`; the AC unit has no target temperature. Master 18.5 °C went out as 2/1; in °F, 21 °C as 70 °F (5/1); back in °C, 18 as 2/0. Master at 16 °C (`StTem` 0) kept its target temperature through a restart. With PR 6: the memory learned all four zones with both columns and nothing for the AC unit, and Master 18.5 °C as 2/1. Restored afterwards, everything matched the snapshot. |
| 4, cloud-only (review round 5) | The controller was paired with Gree+ again for this (its local key changed, `gree_zone` re-bound by itself). A cloud-only entry added through the UI offered only the AC unit, and its MQTT bind timed out (v1 twice, v2 once), so no entry was created. Afterwards the gree_custom test entry, its devices and entities were merged back from the backup into the current registries (other integrations had changed them meanwhile), and the controller matched the snapshot. |
| 4, cloud + local (review round 6) | With `3f55495`, a cloud + local entry added through the UI offered the AC unit and all four zones with the names from the Gree app, all marked Local. Every device bound locally with the key from the cloud, the gateway device showed as "Zone controller" with all five linked, and Master 18.5 °C went out as 2/1 and back to 2/0. The debug log of the flow had no token, password or email. Before the fix, the first try offered only the AC unit, and its setup log held the cloud password in clear text: the reason for `e33b6f7`. Restored afterwards by merging only the gree_custom items back into the registries; the controller matched the snapshot. |
| 4, review round 3 | In °C, `StTem` 2 with `StFahFlg` 1 written over WiFi stayed for minutes and through panel use, while the panel showed 18: the bit is the half degree, the panel shows only whole degrees. Through Home Assistant with PR 4: zone numbers step 0.5 °C; Master 18.5 °C went out as 2/1; in °F, 21 °C went out as 70 °F (5/1); back in °C, 18 went out as 2/0. After the first poll every unit keeps only `StTem`, `StFahFlg` and `TemUnit`. Restored afterwards, both memory stores put back. |

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
  * The target temperature, its bit and the unit are column groups, like the
    sensors: `SetTem`/`StTem`, `TemRec`/`StFahFlg`, `TemUn`/`TemUnit`. Each
    device keeps the first column of each group it answers (`missing_value=-1`,
    since `StTem` 0 is 16 °C), so other units keep their columns. The AC unit
    drops its always-0 `StTem`/`StFahFlg`. A zone is `StTem` + 16 with the
    `SetTem`/`TemRec` table: half degrees in °C, whole degrees in °F, unit from
    `TemUnit`. The bit is only sent to a device that answers it.
  * Discovery names the sub-units `AC unit`, `Zone 1` … instead of five times
    `zone`.
* **Home Assistant layer**
  * Zones get no climate entity; they get a **switch** (named like the zone) and
    a **Target Temperature** number.
  * The zone switch is the optional feature **Zone Switch**, so it can be left
    out for an always-open zone. The feature is only offered on zones; zones
    don't show the climate options. A new zone always starts with it ticked.
  * When several sub-units are set up in one go, the next one's form takes the
    mode lists and features of the one before, not its name, and never `zone`.
  * `GreeEntityDescription.device_filter`: a small generic hook so an entity can
    be limited to a kind of device when the props alone can't tell.
  * The gateway device of a zone controller is labelled "Zone controller"
    instead of "VRF gateway".
  * Fan mode changes only touch Quiet and Turbo on units that have them; before,
    every fan change on a unit without Quiet logged an error.
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
  zone `{"StTem": 4, "StFahFlg": 0}`. The columns are the ones the device uses,
  so a standalone unit stores `SetTem` and `TemRec` the same way, without
  conversions and without a migration.
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
