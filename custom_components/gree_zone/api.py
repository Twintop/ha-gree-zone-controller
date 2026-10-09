"""Minimal async client for the Gree WiFi (UDP/7000) protocol, as spoken by the
Gree LE60-13/GH zone controller's ME31-00/C13 WiFi module.

The module is a gateway: the controller itself plus one sub-unit per zone
(the AC unit is sub-unit 00). Status/commands for a sub-unit are sent to the
gateway with the sub-unit's MAC inside the encrypted pack.

The module is fragile: requests asking for more than ~20 columns make it drop
the request or reboot, and it copes badly with concurrent requests, so every
exchange is serialised and column lists are chunked.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import GENERIC_KEY, MAX_COLS_PER_REQUEST, PORT

_LOGGER = logging.getLogger(__name__)


class GreeZoneError(Exception):
    """Raised when the controller does not answer or answers badly."""


def _encrypt(text: str, key: bytes) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode()


def _decrypt(b64: str, key: bytes) -> dict[str, Any]:
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    raw = dec.update(base64.b64decode(b64)) + dec.finalize()
    # Some firmwares pad with garbage rather than strict PKCS7: cut at the last brace.
    text = raw.decode(errors="ignore")
    return json.loads(text[: text.rfind("}") + 1])


class _OneShot(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.reply: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

    def datagram_received(self, data: bytes, addr) -> None:
        if not self.reply.done():
            self.reply.set_result(data)

    def error_received(self, exc: Exception) -> None:
        if not self.reply.done():
            self.reply.set_exception(exc)


class GreeZoneClient:
    """Talks to one zone controller gateway."""

    def __init__(self, host: str, mac: str = "", key: str = "") -> None:
        self.host = host
        self.mac = mac
        self.key = key.encode() if key else b""
        self._lock = asyncio.Lock()

    async def _exchange(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        transport, proto = await loop.create_datagram_endpoint(
            _OneShot, remote_addr=(self.host, PORT)
        )
        try:
            transport.sendto(json.dumps(payload, separators=(",", ":")).encode())
            return json.loads(await asyncio.wait_for(proto.reply, timeout))
        finally:
            transport.close()

    async def _request(
        self,
        inner: dict[str, Any],
        key: bytes,
        *,
        i: int = 0,
        retries: int = 2,
        timeout: float = 4.0,
    ) -> dict[str, Any]:
        payload = {
            "cid": "app",
            "i": i,
            "pack": _encrypt(json.dumps(inner, separators=(",", ":")), key),
            "t": "pack",
            "tcid": self.mac,
            "uid": 0,
        }
        last_err: Exception | None = None
        async with self._lock:
            for attempt in range(retries + 1):
                try:
                    reply = await self._exchange(payload, timeout)
                    # Give the module a moment before the next request.
                    await asyncio.sleep(0.25)
                    return _decrypt(reply["pack"], key)
                except (TimeoutError, asyncio.TimeoutError, OSError, KeyError, ValueError) as err:
                    last_err = err
                    _LOGGER.debug("Gree zone request failed (attempt %s): %s", attempt + 1, err)
                    await asyncio.sleep(1.0)
        raise GreeZoneError(f"No valid reply from {self.host}: {last_err}")

    async def scan(self) -> dict[str, Any]:
        """Unicast discovery; returns the device info (mac, name, subCnt...)."""
        async with self._lock:
            try:
                reply = await self._exchange({"t": "scan"}, 4.0)
                return _decrypt(reply["pack"], GENERIC_KEY)
            except (TimeoutError, asyncio.TimeoutError, OSError, KeyError, ValueError) as err:
                raise GreeZoneError(f"No discovery reply from {self.host}: {err}") from err

    async def bind(self) -> str:
        """Obtain the device key."""
        res = await self._request(
            {"mac": self.mac, "t": "bind", "uid": 0}, GENERIC_KEY, i=1
        )
        if res.get("t", "").lower() != "bindok" or "key" not in res:
            raise GreeZoneError(f"Bind failed: {res}")
        self.key = res["key"].encode()
        return res["key"]

    async def sub_units(self) -> list[dict[str, Any]]:
        """List the gateway's sub-units (AC + zones)."""
        res = await self._request(
            {"cid": self.mac, "i": 0, "mac": self.mac, "t": "subDev"}, self.key
        )
        return res.get("list", [])

    async def status(self, target: str, cols: list[str]) -> dict[str, Any]:
        """Read columns from a sub-unit (or the gateway), chunked to stay safe."""
        values: dict[str, Any] = {}
        for start in range(0, len(cols), MAX_COLS_PER_REQUEST):
            chunk = cols[start : start + MAX_COLS_PER_REQUEST]
            res = await self._request({"cols": chunk, "mac": target, "t": "status"}, self.key)
            values.update(zip(res.get("cols", []), res.get("dat", [])))
        return values

    async def command(self, target: str, values: dict[str, Any]) -> dict[str, Any]:
        """Write columns on a sub-unit."""
        res = await self._request(
            {"opt": list(values), "p": list(values.values()), "t": "cmd", "sub": target},
            self.key,
        )
        if res.get("r") != 200:
            raise GreeZoneError(f"Command {values} on {target} rejected: {res}")
        return res
