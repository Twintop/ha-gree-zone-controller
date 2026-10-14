"""Exercise gree_zone's per-mode setpoint memory against a simulated controller,
with just enough of Home Assistant stubbed out to import the coordinator.

Run with `pytest` or `python tests/test_setpoint_memory.py` (needs `cryptography`)."""
import asyncio
from pathlib import Path
import sys
import types
from typing import Generic, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
T = TypeVar("T")


def stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod


class DataUpdateCoordinator(Generic[T]):
    def __init__(self, hass, logger, name, update_interval):
        self.hass, self.data = hass, None

    def async_set_updated_data(self, data):
        self.data = data

    async def async_request_refresh(self):
        self.data = await self._async_update_data()


class Store(Generic[T]):
    saved = None

    def __init__(self, hass, version, key):
        pass

    async def async_load(self):
        return None

    def async_delay_save(self, func, delay):
        Store.saved = func()


class Err(Exception):
    pass


for pkg in ("homeassistant", "homeassistant.helpers"):
    stub(pkg, __path__=[])
stub("homeassistant.const", CONF_HOST="host")
stub("homeassistant.config_entries", ConfigEntry=object)
stub("homeassistant.core", HomeAssistant=object)
stub("homeassistant.exceptions", HomeAssistantError=Err)
stub("homeassistant.helpers.event", async_call_later=lambda hass, delay, action: None)
stub("homeassistant.helpers.storage", Store=Store)
stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=DataUpdateCoordinator, UpdateFailed=Err)

from gree_zone import coordinator as coord  # noqa: E402
from gree_zone.api import GreeZoneError  # noqa: E402

AC, Z = "ac00", ["z01", "z02", "z03", "z04"]


class FakeController:
    """Mode changes over WiFi do NOT swap setpoints (like the real one)."""

    def __init__(self):
        self.mac = "gw"
        self.state = {AC: {"Pow": 1, "Mod": 1, "WdSpd": 5, "AllErr": 0, "TemUnit": 0}}
        for z, t in zip(Z, [3, 4, 2, 4]):
            self.state[z] = {"Pow": 1, "StTem": t, "StFahFlg": 0}

    async def status(self, target, cols):
        if target == self.mac:  # gateway mirrors Mod and every zone's StTemN and StFahFlgN
            view = {"Mod": self.state[AC]["Mod"]}
            view.update({f"StTem{int(z[-2:])}": self.state[z]["StTem"] for z in Z})
            view.update({f"StFahFlg{int(z[-2:])}": self.state[z]["StFahFlg"] for z in Z})
            return {c: view[c] for c in cols if c in view}
        return {c: self.state[target][c] for c in cols if c in self.state[target]}

    def panel_mode(self, mode, recalled):
        """Mode change on the wall panel: it recalls its own per-mode setpoints."""
        self.state[AC]["Mod"] = mode
        for z, t in zip(Z, recalled):
            self.state[z].update({"StTem": t - 16, "StFahFlg": 0})

    async def command(self, target, values):
        self.state[target].update(values)

    async def bind(self):
        raise GreeZoneError("unused")

    def setpoints(self):
        return [self.state[z]["StTem"] + 16 for z in Z]


class Entry:
    entry_id = "e1"
    data = {"ac_unit": AC, "key": "k", "zones": [{"mac": z, "name": z, "always_on": i == 0} for i, z in enumerate(Z)]}
    options: dict = {}


def raws(slot):
    """The raw StTem per zone of one mode in the memory."""
    return {z: setpoint["StTem"] for z, setpoint in slot.items()}


clock = [1000.0]
coord.time.monotonic = lambda: clock[0]


async def poll(c, advance=0):
    clock[0] += advance
    await c.async_request_refresh()


async def main():
    dev = FakeController()
    c = coord.GreeZoneCoordinator(object(), Entry(), dev)
    await c.async_load_memory()

    await poll(c)                      # first sight of Cool: not learned yet
    assert c.setpoint_memory == {}, c.setpoint_memory
    await poll(c, advance=25)          # Cool steady >20s: learned
    assert raws(c.setpoint_memory["1"]) == dict(zip(Z, [3, 4, 2, 4])), c.setpoint_memory
    assert c.setpoint_memory["1"]["z01"] == {"StTem": 3, "StFahFlg": 0}
    print("1. Cool learned after settling:", dev.setpoints())

    await c.async_set_mode(2)          # -> Heat, nothing remembered for Heat yet
    assert dev.state[AC]["Mod"] == 2 and dev.setpoints() == [19, 20, 18, 20]
    print("2. Heat (no memory yet), setpoints untouched:", dev.setpoints())

    await poll(c, advance=1)           # confirm Mod hold
    for z, t in zip(Z, [3, 2, 1, 4]):  # user sets Heat temps on the wall panel
        dev.state[z]["StTem"] = t
    await poll(c, advance=5)           # mode changed <20s ago... but mode didn't change since last poll
    await poll(c, advance=25)
    assert raws(c.setpoint_memory["2"]) == dict(zip(Z, [3, 2, 1, 4])), c.setpoint_memory
    print("3. Heat temps set on panel and learned:", dev.setpoints())

    dev.state["z02"]["StTem"] = 5      # panel tweak just before switching, not yet polled
    await c.async_set_mode(1)          # -> Cool: snapshot Heat, recall Cool
    assert c.setpoint_memory["2"]["z02"]["StTem"] == 5, "snapshot missed last-second panel change"
    assert dev.state[AC]["Mod"] == 1 and dev.setpoints() == [19, 20, 18, 20], dev.setpoints()
    print("4. Back to Cool, recalled:", dev.setpoints(), "(Heat snapshot kept late tweak)")

    await poll(c, advance=1)
    await poll(c, advance=25)          # holds confirmed; Cool steady
    await c.async_set_mode(2)
    assert dev.setpoints() == [19, 21, 17, 20], dev.setpoints()
    print("5. Heat again, recalled:", dev.setpoints())

    await poll(c, advance=1)
    await poll(c, advance=25)
    await c.async_set_mode(2)          # same mode: no recall, no snapshot side effects
    assert dev.setpoints() == [19, 21, 17, 20]
    print("6. Re-selecting Heat changes nothing:", dev.setpoints())

    await c.async_command("z03", {"StTem": 6, "StFahFlg": 0})  # HA sets a setpoint in Heat
    assert c.setpoint_memory["2"]["z03"] == {"StTem": 6, "StFahFlg": 0}
    print("7. HA-set setpoint remembered for Heat:", c.setpoint_memory["2"])
    assert Store.saved == c.setpoint_memory
    print("8. Memory persisted:", Store.saved)

    await poll(c, advance=1)
    await poll(c, advance=25)          # settle after the HA command
    dev.state["z04"]["StTem"] = 7      # panel/app temp change, mode unchanged
    await poll(c, advance=10)
    assert c.setpoint_memory["2"]["z04"]["StTem"] == 7, c.setpoint_memory
    print("9. Panel temp change learned on next poll:", c.setpoint_memory["2"])

    dev.panel_mode(3, [22, 22, 22, 22])  # panel switches to Dry, recalls its own temps
    await poll(c, advance=10)          # first sight of Dry: not learned yet
    assert "3" not in c.setpoint_memory
    await poll(c, advance=10)          # Dry seen twice: learned; Heat untouched
    assert raws(c.setpoint_memory["3"]) == dict(zip(Z, [6, 6, 6, 6])), c.setpoint_memory
    assert c.setpoint_memory["2"]["z04"]["StTem"] == 7
    print("10. Panel mode change learned for Dry, Heat memory untouched:", c.setpoint_memory["3"])

    dev.state["z01"]["StTem"] = 8      # panel tweak in Dry, then HA switches to Heat before a poll
    await c.async_set_mode(2)
    assert c.setpoint_memory["3"]["z01"]["StTem"] == 8, c.setpoint_memory
    assert dev.setpoints() == [19, 21, 22, 23], dev.setpoints()
    print("11. Fresh snapshot caught Dry tweak; Heat recalled:", dev.setpoints())

    await poll(c, advance=1)
    await poll(c, advance=25)          # settle in Heat
    await c.async_command("z02", {"StTem": 2, "StFahFlg": 1})  # HA sets 18.5 °C
    assert c.setpoint_memory["2"]["z02"] == {"StTem": 2, "StFahFlg": 1}, c.setpoint_memory
    await poll(c, advance=1)
    await poll(c, advance=25)
    dev.state["z02"]["StFahFlg"] = 0   # only the bit changes on the panel: 18 °C
    await poll(c, advance=10)
    assert c.setpoint_memory["2"]["z02"] == {"StTem": 2, "StFahFlg": 0}, c.setpoint_memory
    print("12. The bit is learned, also on its own:", c.setpoint_memory["2"]["z02"])

    dev.state["z02"]["StFahFlg"] = 1   # back to 18.5 °C on the panel
    await poll(c, advance=10)
    await c.async_set_mode(3)          # -> Dry: recalls 22 °C, without the bit
    assert dev.state["z02"] == {"Pow": 1, "StTem": 6, "StFahFlg": 0}, dev.state["z02"]
    await poll(c, advance=1)
    await poll(c, advance=25)
    await c.async_set_mode(2)          # -> Heat: 18.5 °C comes back with its bit
    assert dev.state["z02"] == {"Pow": 1, "StTem": 2, "StFahFlg": 1}, dev.state["z02"]
    print("13. A half degree is recalled with its bit:", dev.state["z02"])
    print("ALL PASSED")


async def memory_off():
    """With the option off, nothing is learned or recalled, and what was stored stays."""
    dev = FakeController()
    entry = Entry()
    entry.options = {"setpoint_memory": False}
    c = coord.GreeZoneCoordinator(object(), entry, dev)
    await c.async_load_memory()
    stored = {"2": {z: {"StTem": 9, "StFahFlg": 0} for z in Z}}
    c.setpoint_memory = {mode: dict(zones) for mode, zones in stored.items()}

    await poll(c)
    await poll(c, advance=25)          # Cool steady, but nothing is learned
    assert c.setpoint_memory == stored, c.setpoint_memory
    await c.async_set_mode(2)          # -> Heat: no recall of the stored 25 °C
    assert dev.state[AC]["Mod"] == 2 and dev.setpoints() == [19, 20, 18, 20], dev.setpoints()
    await c.async_command("z03", {"StTem": 6, "StFahFlg": 0})
    assert c.setpoint_memory == stored, c.setpoint_memory

    entry.options = {"setpoint_memory": True}   # on again: learning carries on
    await poll(c, advance=1)
    await poll(c, advance=25)
    assert raws(c.setpoint_memory["2"]) == dict(zip(Z, [3, 4, 6, 4])), c.setpoint_memory


def test_memory_off():
    asyncio.run(memory_off())


def test_memory_migration():
    """Version 1 kept only StTem per zone. It loads as StTem with bit 0."""
    old = {"1": {"z01": 4, "z02": 2}, "2": {"z01": 2}}
    assert coord.migrate_memory(old) == {
        "1": {"z01": {"StTem": 4, "StFahFlg": 0}, "z02": {"StTem": 2, "StFahFlg": 0}},
        "2": {"z01": {"StTem": 2, "StFahFlg": 0}},
    }
    new = {"2": {"z01": {"StTem": 2, "StFahFlg": 1}}}
    assert coord.migrate_memory(new) == new


def test_setpoint_memory():
    asyncio.run(main())


if __name__ == "__main__":
    test_setpoint_memory()
    test_memory_off()
    test_memory_migration()
