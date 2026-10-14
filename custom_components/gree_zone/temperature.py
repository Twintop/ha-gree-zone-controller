"""Zone setpoints: the StTem column and its StFahFlg bit, in °C or °F.

StTem is the setpoint in °C minus 16. StFahFlg is a bit that works like
TemRec on other Gree units:

* in °C it is the half degree: StTem 2 with the bit is 18.5 °C (the wall
  panel shows only whole degrees, so it shows 18);
* in °F it tells which of the Fahrenheit values next to a whole °C degree is
  meant: 64 °F is StTem 2 with bit 0, 66 °F is 3/0, 67 °F is 3/1, 70 °F is 5/1
  (all checked on the panel).

The controller keeps the old bit when only StTem is written, so both are
always sent together. TemUnit says which unit the controller and the panel
use: 0 °C, 1 °F.

No Home Assistant imports, so the tests can load this file on its own.
"""
from __future__ import annotations

OFFSET = 16
MIN_C, MAX_C = 16, 30
MIN_F, MAX_F = 61, 86
UNIT_C, UNIT_F = 0, 1


def to_celsius(raw: int, bit: int) -> float:
    """StTem and its bit as °C, in half degrees."""
    return raw + OFFSET + (0.5 if bit else 0.0)


def from_celsius(value: float) -> tuple[int, int]:
    """StTem and bit for the nearest half degree, within 16–30 °C."""
    halves = round(min(max(value, MIN_C), MAX_C) * 2)
    return halves // 2 - OFFSET, halves % 2


def from_fahrenheit(value: float) -> tuple[int, int]:
    """StTem and bit for the nearest whole °F, within 61–86 °F.

    StTem is the °C value rounded to a whole degree. The bit is set when the
    exact °C value is at or above that whole degree. Worked in ninths of a
    degree so there is no float rounding: whole °F values never fall on a tie.
    """
    fahrenheit = min(max(round(value), MIN_F), MAX_F)
    ninths = (fahrenheit - 32) * 5  # °C times 9
    whole = (ninths * 2 + 9) // 18  # nearest whole °C
    return whole - OFFSET, int(ninths >= whole * 9)


def to_fahrenheit(raw: int, bit: int) -> int:
    """The whole °F value that from_fahrenheit turns into this StTem and bit."""
    for fahrenheit in range(MIN_F, MAX_F + 1):
        if from_fahrenheit(fahrenheit) == (raw, bit):
            return fahrenheit
    # Not a pair the °F table makes (for example 16 °C set in °C): convert.
    return round(to_celsius(raw, bit) * 9 / 5 + 32)


def to_unit(raw: int, bit: int, unit: int | None) -> float:
    """StTem and bit in the controller's unit."""
    return to_fahrenheit(raw, bit) if unit == UNIT_F else to_celsius(raw, bit)


def from_unit(value: float, unit: int | None) -> tuple[int, int]:
    """StTem and bit for a value in the controller's unit."""
    return from_fahrenheit(value) if unit == UNIT_F else from_celsius(value)
