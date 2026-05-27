"""ULID minimalista — estável, ordenável por tempo, sem dependência externa."""
from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = ["0"] * length
    for i in range(length - 1, -1, -1):
        out[i] = _ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(out)


def new_ulid() -> str:
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    return _encode(ts_ms, 10) + _encode(rand, 16)
