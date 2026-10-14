"""Zone setpoint conversions: StTem and its StFahFlg bit in °C and °F.

The expected values are the ones the wall panel showed. temperature.py has no
Home Assistant imports, so it is loaded on its own.

Run with `pytest` or `python tests/test_temperature.py`."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "gree_zone" / "temperature.py"
_SPEC = importlib.util.spec_from_file_location("gree_zone_temperature", _PATH)
temperature = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(temperature)


def test_fahrenheit_as_seen_on_the_panel():
    """64 °F is StTem 2 with bit 0, 66 °F 3/0, 67 °F 3/1, 70 °F 5/1, 72 °F 6/1."""
    seen = {64: (2, 0), 66: (3, 0), 67: (3, 1), 70: (5, 1), 72: (6, 1)}
    for fahrenheit, pair in seen.items():
        assert temperature.from_fahrenheit(fahrenheit) == pair, fahrenheit
        assert temperature.to_fahrenheit(*pair) == fahrenheit, pair


def test_every_fahrenheit_value_comes_back():
    """61 to 86 °F each get their own StTem and bit, and read back the same."""
    pairs = {f: temperature.from_fahrenheit(f) for f in range(61, 87)}
    assert len(set(pairs.values())) == len(pairs)
    for fahrenheit, pair in pairs.items():
        assert temperature.to_fahrenheit(*pair) == fahrenheit


def test_fahrenheit_is_rounded_and_clamped():
    """Home Assistant turns 21 °C into 69.8 °F, which goes out as 70."""
    assert temperature.from_fahrenheit(69.8) == temperature.from_fahrenheit(70)
    assert temperature.from_fahrenheit(50) == temperature.from_fahrenheit(61)
    assert temperature.from_fahrenheit(95) == temperature.from_fahrenheit(86)


def test_celsius_takes_half_degrees():
    """The bit is the half degree: 18.5 °C is StTem 2 with bit 1."""
    assert temperature.from_celsius(18.5) == (2, 1)
    assert temperature.to_celsius(2, 1) == 18.5
    assert temperature.from_celsius(18) == (2, 0)
    assert temperature.from_celsius(21.2) == (5, 0)
    assert temperature.from_celsius(21.3) == (5, 1)
    assert temperature.from_celsius(35) == (14, 0)
    assert temperature.from_celsius(10) == (0, 0)


def test_the_unit_picks_the_table():
    """TemUnit 0 is °C, 1 is °F, and unknown is °C."""
    assert temperature.to_unit(3, 1, 0) == 19.5
    assert temperature.to_unit(3, 1, 1) == 67
    assert temperature.to_unit(3, 1, None) == 19.5
    assert temperature.from_unit(67, 1) == (3, 1)
    assert temperature.from_unit(19.5, 0) == (3, 1)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ALL PASSED")
