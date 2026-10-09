# Gree LE60-13/GH zone controller — protocol notes

Everything here was worked out against a real system: zone control interface
LE60-13/GH, wall panel, four RF remote/sensors LE60-13/C1, WiFi module
ME31-00/C13 running firmware code `362001062617` v1.27 (`U-W05SAV1.27.bin`).

## Transport

Standard Gree WiFi LAN protocol: JSON over UDP port 7000, payloads AES-128-ECB
encrypted (PKCS7), base64 in a `pack` field.

* Discovery: send `{"t":"scan"}`; the reply `pack` is encrypted with the generic
  key `a3K8Bx%2r8Y7#xDh` and contains
  `{"t":"dev","mid":"50","name":"GR-ZCntrlr_5000_02_xxxx_EC","ver":"V1.2.1","mac":"<12 hex>","subCnt":5,...}`.
  `subCnt > 0` marks a gateway.
  Note: **the reply has no `cid` field** (most Gree units send one). Clients that
  require it fail to discover this device.
* Bind: `{"mac":<mac>,"t":"bind","uid":0}` with the generic key, outer `"i":1`;
  reply `{"t":"bindOk","key":"<16 chars>"}`. The key is stable across binds and
  module reboots.
* Everything else is encrypted with the device key, outer
  `{"cid":"app","i":0,"pack":...,"t":"pack","tcid":<gateway mac>,"uid":0}`.

## Sub-units

Only the legacy **`subDev`** form of the sub-unit list works on this module
(the `subList` forms used by VRF gateways get no reply):

```json
{"cid":"<mac>","i":0,"mac":"<mac>","t":"subDev"}
```
reply:
```json
{"t":"subList","c":5,"list":[
  {"mac":"<mac>00","mid":"5000","name":"zone"},   // the ducted AC unit
  {"mac":"<mac>01","mid":"5001","name":"zone"},   // zone 1
  ... up to <mac>08
]}
```

* Status of a sub-unit: `{"cols":[...],"mac":"<sub mac>","t":"status"}` → `{"t":"dat","mac":"<sub mac>","cols":[...],"dat":[...]}`.
  Only the columns the module knows are returned.
* Command to a sub-unit: `{"opt":[...],"p":[...],"t":"cmd","sub":"<sub mac>"}` → `{"t":"res","r":200,...}`.
* Status of the gateway itself: `"mac":"<gateway mac>"`.
* Every sub-unit answers the info columns (`name`, `mid`, `hid`, `host`, `ver`) with
  the **controller's** values (`name` = `GR-ZCntrlr_…`, `mid` = `3017`), so only the
  sub-device list tells the AC unit (`5000`) from a zone (`5001`); the MAC suffix
  (`00` = AC unit) works too.

## ⚠ Request size limit

**Keep every request at ≤ 20 columns.** (A careful probe — the one in the
`gree_custom` 5.0 integration — measures the real limit as 29: 30 columns return an
empty result.) With ~30 columns the module answers
with an empty list; with ~40+ it stops answering and **reboots** (its `time`
column resets to `2020-01-01 00:00:00`). Repeated reboots left it without a cloud
connection, which made the Gree+ app show the device "Off-line". The module
also copes poorly with bursts — space requests a few hundred ms apart.

## Columns that matter

| Where | Column | Meaning |
| --- | --- | --- |
| sub `00` (AC) | `Pow` | **whole-system power** (the panel's ON/OFF button). Zones keep their own `Pow` while it is off. |
| sub `00`, gateway, zones | `Mod` | mode — **1 Cool, 2 Heat, 3 Dry, 4 Fan, 5 Auto** (not the usual Gree 0 Auto … 4 Heat) |
| sub `00`, gateway, zones | `WdSpd` | fan — 0 Auto, 1 Low, 2 Med-Low, 3 Medium, 4 Med-High, 5 High, **6 Turbo** (Cool/Heat only). Dry forces 1. |
| sub `00` | `AllErr` | error flag |
| zone sub `0N` | `Pow` | zone open (1) / closed (0) |
| zone sub `0N` | `StTem` | zone setpoint, **°C − 16** (0 = 16 °C … 14 = 30 °C). Writable. |
| gateway | `StTem1`…`StTem8` | the same setpoints, all zones in one read (mirrors each zone's `StTem`) |
| gateway | `Mod` + `StTem1..N` | read together for a consistent mode/setpoint snapshot |

The gateway's own `Pow` reads 0 while the system runs; it is not the system power.

### Full column table (firmware v1.27)

From the module firmware (`tools/firmware_fields.py`). The same table is in
v1.21 (subset) and v1.28 (identical).

```
Pow Mod StTem WdSpd EnSvSt StFahFlg HeatSvStTemMax CoolSvStTemMin TemUnit Dry OMod
Quier LowDeHumi HSvStTemMaxFlg CSvStTemMinFlg ColdMod ErWdVlv ErVavle RmType RmNum
WdVlvAllOnNum IndoorType AllErr Dred VavleAllOn Demand InProtocol NoD MasterPow
EnWdVlv1..8 StTem1..8 StFahFlg1..8 RmType1..8 RmNum1..8 EnValve1..8
IntProVer MainConProVer SubConProVer Tcloud AppTimer ElcErg ElcGear Elc1Kwh
AutoUpdate AutoComnCloud apssid appsw time lat lon mid country hid mac ver
HidSvrVer InHid InHidSvrVer
```

Observed values on a 4-zone system: `EnWdVlv1..4 = 1`, `EnValve1..4 = 1`
(5–8 = 0) — zone enabled; `RmType1..4` = 1/14/7/8 and `RmNum1..4` = 0/1/0/2 —
the room-name preset and number chosen on the panel; `MasterPow = 1`;
`IndoorType = 1`; `InProtocol = 19`; `HeatSvStTemMax`/`CoolSvStTemMin`/`EnSvSt`
— the energy-saving setpoint limits (0 = off). Unused zones report `StTemN = 4`.

## Wall-panel per-mode setpoint memory

The panel stores each zone's setpoint per mode and pushes them to the
controller when the mode is changed **on the panel**. A `Mod` change over WiFi
leaves the setpoints untouched (they carry over into the new mode). The module
exposes no per-mode setpoint fields, so a client that wants panel-like
behaviour must remember setpoints per mode itself — see the integration's
coordinator.

## Message types handled by the module

LAN: `scan`, `pack` → `bind`, `status`, `cmd`, `subDev`, `setT`/`queryT`/`updateT`/`deleteT` (timers), `wlan`, `upgrade`.
Cloud adds `loginRes` and `dump` (periodic status push). There is no raw/transparent pass-through.

## Zone ambient temperatures

**Not available over WiFi.** No column exists in any released firmware
(v1.21, v1.27, v1.28) and there is no pass-through, so neither this
integration nor the Gree+ app can show them.

Where they travel (from the Gree installation manuals):

```
RF remote/sensor per zone ──radio──▶ zone control interface ──4-core cable──▶ wall panel
(LE60-13/C1, CR2450 coin cell,        (antenna; drives dampers)  12V/GND/RS-485   ("Ambient
 DIP switches = room number)                  │                                  temperature of zone")
                                              └──RS-485──▶ WiFi module (drops them)
```

Ways to get them, best first:

1. **Listen-only RS-485 tap on the wall-panel cable** (or the interface's spare
   *Wired Remote Controller 2* port) with an ESP32 + RS-485 transceiver running
   ESPHome. Gree's wired-controller bus is documented in
   [maxim-smirnov/gree-wired-proto](https://github.com/maxim-smirnov/gree-wired-proto):
   RS-485 on A/B, 12 V supply, 1200 baud 8N1, frames `7E 7E <src> <dst> 11 <len> <body…> <xor>`.
   Frame contents for this product still need decoding (correlate with the
   panel's readings).
2. The WiFi module's debug UART (Realtek AmebaZ): AT command `GATD=3` prints all
   RS-485 traffic between the interface and the module — a cheap way to see the
   frame format, though that link may not carry temperatures.
3. SDR (`rtl_433`) on the RF remotes — frequency and protocol undocumented.
4. Or simply a separate temperature sensor next to each RF remote.

## Firmware

Images are served by Gree's update servers:
`http://<server>/wifiModule/Lastversion?firmwareCode=362001062617`
(`au.grih.gree.com`/`eu.grih.gree.com`: v1.27 "bug fixes"; `test.grih.gree.com`:
v1.28 "mask faults"; `kfgrih.gree.com`: v1.21 "zone controller cloud control").
Release note for v1.27: "Commercial zone controller room number error fix".

## Upstream

This support has been ported to RobHofmann's `gree_custom` (5.0) integration; see
[`upstream/README.md`](../upstream/README.md).
