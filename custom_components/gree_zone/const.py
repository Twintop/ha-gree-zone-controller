"""Constants for the Gree Zone Controller integration."""
from __future__ import annotations

DOMAIN = "gree_zone"
PLATFORMS = ["climate", "number", "switch"]

PORT = 7000
GENERIC_KEY = b"a3K8Bx%2r8Y7#xDh"
# The WiFi module drops (or reboots on) requests with much more than 20 columns.
MAX_COLS_PER_REQUEST = 20
SCAN_INTERVAL_SECONDS = 10

CONF_MAC = "mac"
CONF_KEY = "key"
CONF_AC_UNIT = "ac_unit"
CONF_ZONES = "zones"  # list of {"mac": ..., "name": ..., "always_on": bool}

AC_COLS = ["Pow", "Mod", "WdSpd", "AllErr"]
# Field names come from the WiFi module firmware (U-W05SA v1.27) column table.
# StTem is the setpoint as degrees above 16 °C (0 = 16, 14 = 30).
ZONE_COLS = ["Pow"]  # setpoints come from the gateway's StTem1..8
TEMP_OFFSET = 16
MIN_TEMP = 16
MAX_TEMP = 30

# Sub-unit model ids reported by the gateway's subDev list.
MID_AC_UNIT = "5000"
MID_ZONE = "5001"
