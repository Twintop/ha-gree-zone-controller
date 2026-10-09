# Porting zone controller support to RobHofmann/HomeAssistant-GreeClimateComponent

Everything learned in this project, ported onto the 5.0 rewrite of
[RobHofmann/HomeAssistant-GreeClimateComponent](https://github.com/RobHofmann/HomeAssistant-GreeClimateComponent)
(domain `gree_custom`), so zone controllers can be supported in one place.

* Fork: https://github.com/Twintop/HomeAssistant-GreeClimateComponent — five branches,
  all based on `5.0-dev` @ `5e18a8e` (2026-10-09).
* No PR or issue has been opened.

| # | Branch | Based on | Commit | What |
| --- | --- | --- | --- | --- |
| 1 | [`fix-scan-without-cid`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/fix-scan-without-cid) | `5.0-dev` | `ce6d16e` | Accept a scan reply without `cid` (+ test, docs) |
| 2 | [`fix-dhcp-gateway-sub-units`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/fix-dhcp-gateway-sub-units) | `5.0-dev` | `47ee6b7` | DHCP step: use the sub-unit MAC, deep copy (+ docs) |
| 3 | [`fix-climate-unsupported-features`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/fix-climate-unsupported-features) | `5.0-dev` | `d99874f` | `continue` not `return`; target temperature and swing only when supported (+ docs) |
| 4 | [`zone-controller-support`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-controller-support) | `5.0-dev` + copies of 1–3 | `dd4f191` | Zone controller support |
| 5 | [`zone-setpoint-memory`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/tree/zone-setpoint-memory) | branch 4 | `bfc7d74` | Per-mode zone setpoint memory |

Branches 1–3 are independent of each other. Branch 4 needs all three fixes
(without 1 the controller can't even be discovered), so it carries
patch-identical copies of them; once they are merged upstream, `git rebase
origin/5.0-dev` drops the copies automatically. A PR for branch 4 opened before
then shows 4 commits; review only the last one.

Tests per branch: 1 → 255, 2 → 254, 3 → 254, 4 → 271, 5 → 277 (all passing; the
`5.0-dev` baseline is 254).

The combined change of all five branches:
[`5.0-dev...zone-setpoint-memory`](https://github.com/Twintop/HomeAssistant-GreeClimateComponent/compare/5.0-dev...zone-setpoint-memory).

## Status

| Check | Result |
| --- | --- |
| Upstream test suite (`pytest`, Python 3.14) | **277 passed** on branch 5 — the 254 existing tests plus 23 new ones |
| Ruff lint + format | clean |
| Mypy | no new errors (56 before and after, all from Home Assistant not being installed locally) |
| Pylint (protocol layer + tests) | no new findings |
| Each branch on its own | passes (see the table above) |
| Real controller, protocol layer | discovery, bind, roles, modes, zone temperatures, column probe (29), writes of a zone setpoint and fan speed — all correct; no module reboot |
| Real controller, inside Home Assistant (installed via YAML) | entities created as designed, states correct, external changes picked up, per-mode memory learned; no errors in the log |
| Not tested on real hardware | changing the **mode** from Home Assistant through this branch, and the recall of zone setpoints after it (covered by tests against the fake controller; avoided on the real system while nobody was home) |

## What changes, and why

### Bugs in upstream that a zone controller hits

1. **Discovery fails outright.** The zone controller's scan reply has no `cid`;
   `DeviceScanInfoResponse` required it, so validation raised before anything
   else ran. `cid` is now optional (nothing reads it).
2. **Wrong / crashing modes.** The ducted unit uses `Mod` 1 Cool, 2 Heat, 3 Dry,
   4 Fan, 5 Auto. Upstream read Fan as **Heat**, and Auto (5) raised
   `ValueError` from `OperationMode(5)`.
3. **`async_step_dhcp` KeyError** (any VRF gateway): it indexed the entry's
   devices with the DHCP (gateway) MAC instead of the discovered sub-unit's MAC.
   It also mutated the entry data in place via a shallow copy, so the IP update
   was never saved. Fixed with `d.mac` and a deep copy.
4. **`return` instead of `continue`** in the climate platform setup: one device
   without HVAC modes stopped climate entities for all later devices.
5. **Climate offered a target temperature and swing modes the unit doesn't
   have** (the defaults fill in when the options form leaves them out). Both are
   now gated on the device actually supporting `SetTem` / `SwUpDn` /
   `SwingLfRig`. Units that support them are unaffected.

### Zone controller support

* **Protocol layer (`aiogree`)**
  * `GreeProp.ZONE_TARGET_TEMPERATURE = "StTem"` (°C − 16), polled **only** by
    zones (`DeviceState.add_polled`) — normal units send exactly the same
    columns as before (there is a test for that).
  * `ZoneRole` (`ac_unit` / `zone`) detected after the info fetch: the sub-unit
    reports the controller's name (`GR-ZCntrlr…`) and the MAC suffix gives the
    role. No config entry changes, no migration.
  * Mode translation for the zone-controller dialect, turbo as `WdSpd` 6
    (no `Tur` column), leaving Cool/Heat drops turbo to High.
  * Zone target temperature getter/setter with clamping to 16–30 °C.
  * Discovery names the sub-units `AC unit`, `Zone 1` … instead of five times
    `zone`.
  * `zone_memory.py`: `ZoneSetpointMemory`, the per-mode zone setpoint memory
    the wall panel has (learn from polls once the mode is seen twice; snapshot
    before a mode change; recall after). No Home Assistant imports, fully
    tested.
* **Home Assistant layer**
  * Zones get no climate entity; they get a **switch** (named like the zone)
    and a **Target Temperature** number.
  * The zone switch is the optional feature **Zone Switch** in the device
    options, so it can be left out for an always-open zone. The feature is only
    offered on zones; zones don't show the climate options.
  * `GreeEntityDescription.device_filter` — a small generic hook so an entity
    can be limited to a kind of device when the props alone can't tell.
  * The ducted unit's climate entity snapshots/recalls the zone setpoints when
    the mode changes. The memory is stored per config entry
    (`.storage/gree_custom.<entry_id>.zone_setpoints`).
* **Tests**: `tests/fakes/zone.py` (a fake controller that behaves like the real
  one: subDev only, no `cid`, per-unit columns, mirrored mode/fan, column cap),
  `tests/test_zone_controller.py` (16 tests), `tests/test_zone_memory.py` (6).
* **Docs**: `docs/protocol.md` (zone controller section), `docs/entities.md`,
  `docs/configuration.md`, `docs/architecture.md`, `supported-devices.md`.

The repository's `AGENTS.md` rules were followed (plain English, no em dashes,
no version bump, tests for `aiogree` changes, docs updated).

## The split (one PR per branch)

The five branches above follow this split:

1. *Fix discovery of units whose scan reply has no `cid`* — one line + the fake.
2. *Fix the DHCP step for sub-units of a gateway* — `config_flow.py` only.
3. *Climate: `continue` instead of `return`; only offer target temperature and
   swing when the unit has them* — `climate.py` only.
4. *Support Gree zone controllers* — roles, mode dialect, turbo, zones, entities,
   options, docs, tests.
5. *Remember zone target temperatures per mode* — `zone_memory.py`, its wiring,
   tests and docs.

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
controller after a restart. The per-mode memory is stored in
`.storage/gree_custom.<entry_id>.zone_setpoints`.

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
