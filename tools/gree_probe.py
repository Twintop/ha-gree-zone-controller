#!/usr/bin/env python3
"""Small CLI for poking at Gree WiFi devices (UDP 7000), including gateways
such as the LE60-13/GH zone controller that front several sub-units.

    python tools/gree_probe.py 192.168.1.50 scan
    python tools/gree_probe.py 192.168.1.50 subdev
    python tools/gree_probe.py 192.168.1.50 status --sub 01 Pow StTem
    python tools/gree_probe.py 192.168.1.50 status Mod StTem1 StTem2 StTem3 StTem4
    python tools/gree_probe.py 192.168.1.50 cmd --sub 04 StTem=3

Every request binds first to obtain the device key (harmless; the key does not
change). Requests are limited to 20 columns: the zone controller's WiFi module
drops larger requests and reboots on ones much larger than that.

Requires `cryptography`.
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import sys

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

GENERIC_KEY = b"a3K8Bx%2r8Y7#xDh"
MAX_COLS = 20


def encrypt(text: str, key: bytes) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def decrypt(b64: str, key: bytes) -> dict:
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    text = (dec.update(base64.b64decode(b64)) + dec.finalize()).decode(errors="ignore")
    return json.loads(text[: text.rfind("}") + 1])


class Device:
    def __init__(self, host: str, timeout: float = 4.0) -> None:
        self.host, self.timeout = host, timeout
        self.mac, self.key = "", GENERIC_KEY

    def _send(self, payload: dict) -> dict:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(self.timeout)
            s.connect((self.host, 7000))
            s.send(json.dumps(payload, separators=(",", ":")).encode())
            return json.loads(s.recv(65535))

    def request(self, inner: dict, key: bytes | None = None, i: int = 0) -> dict:
        key = key or self.key
        reply = self._send({
            "cid": "app", "i": i, "pack": encrypt(json.dumps(inner, separators=(",", ":")), key),
            "t": "pack", "tcid": self.mac, "uid": 0,
        })
        return decrypt(reply["pack"], key)

    def scan(self) -> dict:
        info = decrypt(self._send({"t": "scan"})["pack"], GENERIC_KEY)
        self.mac = info["mac"]
        return info

    def bind(self) -> str:
        if not self.mac:
            self.scan()
        res = self.request({"mac": self.mac, "t": "bind", "uid": 0}, GENERIC_KEY, i=1)
        self.key = res["key"].encode()
        return res["key"]


def parse_value(raw: str):
    try:
        return int(raw)
    except ValueError:
        return raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("scan", help="discovery reply (name, mac, firmware, subCnt)")
    sub.add_parser("bind", help="print the device key")
    sub.add_parser("subdev", help="list sub-units (AC unit + zones) of a gateway")
    st = sub.add_parser("status", help="read columns")
    st.add_argument("--sub", help="sub-unit suffix, e.g. 00 (AC unit) or 01 (zone 1)")
    st.add_argument("cols", nargs="+")
    cm = sub.add_parser("cmd", help="write columns, e.g. Pow=1")
    cm.add_argument("--sub", help="sub-unit suffix, e.g. 00 or 04")
    cm.add_argument("values", nargs="+", metavar="COL=VALUE")
    args = ap.parse_args()

    dev = Device(args.host)
    if args.action == "scan":
        out = dev.scan()
    elif args.action == "bind":
        out = {"key": dev.bind()}
    else:
        dev.bind()
        if args.action == "subdev":
            out = dev.request({"cid": dev.mac, "i": 0, "mac": dev.mac, "t": "subDev"})
        elif args.action == "status":
            if len(args.cols) > MAX_COLS:
                sys.exit(f"Refusing more than {MAX_COLS} columns per request (crashes the module).")
            target = dev.mac + (args.sub or "")
            res = dev.request({"cols": args.cols, "mac": target, "t": "status"})
            out = dict(zip(res.get("cols", []), res.get("dat", [])))
        else:
            values = dict(v.split("=", 1) for v in args.values)
            inner = {"opt": list(values), "p": [parse_value(v) for v in values.values()], "t": "cmd"}
            if args.sub:
                inner["sub"] = dev.mac + args.sub
            out = dev.request(inner)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
