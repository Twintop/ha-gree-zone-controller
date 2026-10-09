#!/usr/bin/env python3
"""List the status/command column names a Gree WiFi module firmware supports.

Gree's modules keep a table of every JSON column they understand. Guessing
column names over the network is hopeless (the zone controller's setpoints are
`StTem1`..`StTem8`, not `SetTem`), but the table is plain text in the firmware.

    # firmware code + version come from the module's `hid` column,
    # e.g. "362001062617+U-W05SAV1.27.bin" -> code 362001062617
    python tools/firmware_fields.py --fetch 362001062617 --server au.grih.gree.com
    python tools/firmware_fields.py firmware.bin

Firmware images and their metadata are served by Gree's update servers
(`http://<server>/wifiModule/Lastversion?firmwareCode=<code>`); see
https://github.com/maxim-smirnov/gree-wifimodule-firmware for known codes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

ANCHOR = b"WdSpd"  # present in every AC-style column table


def fetch(code: str, server: str) -> bytes:
    meta = json.load(urllib.request.urlopen(f"http://{server}/wifiModule/Lastversion?firmwareCode={code}", timeout=15))
    if meta.get("r") != 200:
        sys.exit(f"{server}: {meta}")
    print(f"# {code} v{meta['ver']} ({meta.get('CreateDate')}): {meta.get('desc')}", file=sys.stderr)
    return urllib.request.urlopen(meta["url"], timeout=60).read()


def column_table(image: bytes) -> list[str]:
    """The NUL-separated run of identifiers around the first WdSpd."""
    at = image.find(ANCHOR)
    if at < 0:
        return []
    start = at
    while True:  # walk back over preceding NUL-padded identifiers
        m = re.search(rb"([A-Za-z][A-Za-z0-9]{1,30})\x00+$", image[max(0, start - 40):start])
        if not m:
            break
        start = start - (len(image[max(0, start - 40):start]) - m.start())
    names = []
    for m in re.finditer(rb"([A-Za-z][A-Za-z0-9]{1,30})\x00+", image[start:start + 4096]):
        if m.start() != 0 and names and image[start + m.start() - 1] != 0:
            break
        names.append(m.group(1).decode())
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="firmware .bin")
    ap.add_argument("--fetch", metavar="CODE", help="download the latest image for this firmware code")
    ap.add_argument("--server", default="au.grih.gree.com")
    args = ap.parse_args()
    if not args.image and not args.fetch:
        ap.error("give a firmware file or --fetch CODE")
    image = fetch(args.fetch, args.server) if args.fetch else open(args.image, "rb").read()
    names = column_table(image)
    if not names:
        sys.exit("No column table found.")
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
