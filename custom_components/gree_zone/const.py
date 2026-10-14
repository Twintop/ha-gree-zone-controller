"""Constants for the Gree Zone Controller integration."""
from __future__ import annotations

DOMAIN = "gree_zone"
PLATFORMS = ["climate", "number", "select", "switch"]

PORT = 7000
GENERIC_KEY = b"a3K8Bx%2r8Y7#xDh"
# The WiFi module drops (or reboots on) requests with much more than 20 columns.
MAX_COLS_PER_REQUEST = 20
SCAN_INTERVAL_SECONDS = 10

CONF_MAC = "mac"
CONF_KEY = "key"
CONF_AC_UNIT = "ac_unit"
CONF_ZONES = "zones"  # list of {"mac": ..., "name": ..., "always_on": bool}

# Option: learn the zone setpoints per mode and set them again on a mode change
# from Home Assistant, like the wall panel does.
CONF_SETPOINT_MEMORY = "setpoint_memory"
DEFAULT_SETPOINT_MEMORY = True

# Field names come from the WiFi module firmware (U-W05SA v1.27) column table.
# TemUnit is the unit of the controller and the wall panel: 0 °C, 1 °F.
AC_COLS = ["Pow", "Mod", "WdSpd", "AllErr", "TemUnit"]
# Setpoints come from the gateway's StTem1..8 and StFahFlg1..8, see
# temperature.py for how StTem and its bit encode °C and °F.
ZONE_COLS = ["Pow"]

# The AC unit is the sub-unit whose MAC ends in 00, the others are the zones.
AC_UNIT_SUFFIX = "00"
