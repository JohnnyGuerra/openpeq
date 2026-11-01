"""Safety guard: one rule, one table.

`data/dacs.json` is the single source of truth for what this tool may write to and
what coefficient values it accepts. Every surface that talks to hardware (Python,
Rust, browser) reads this same table — no per-device or per-architecture copies.

The guard is defence in depth, not a guarantee: it refuses devices whose identity it
cannot confirm, and it rejects coefficients outside the accepted range before any
packet is built. A rejected write is aborted in full — no partial application.

Identity is resolved by exact VID/PID match, then by product-name substring under the
same vendor. A device that reports a known vendor with an unlisted product is refused.

Ranges are what the tool accepts, not a claim about the hardware's limits.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

TABLE_PATH = Path(__file__).resolve().parent / "data" / "dacs.json"

# Architectures the guard refuses to write to: fixed mask ROM / OTP descriptor registers.
BLOCKED_ARCHITECTURES = {"conexant_fixed"}


class DeviceSecurityException(ValueError):
    """Raised when a device cannot be confirmed as safe to write to."""


class CoefficientRangeError(ValueError):
    """Raised when a coefficient falls outside the accepted range for its architecture."""


@lru_cache(maxsize=1)
def load_table(path: Optional[str] = None) -> Dict[str, Any]:
    table_path = Path(path) if path else TABLE_PATH
    table = json.loads(table_path.read_text(encoding="utf-8"))
    if not isinstance(table, dict) or "devices" not in table or "ranges" not in table:
        raise DeviceSecurityException(f"Device table {table_path} has no 'devices' or 'ranges' section.")
    return table


def match_device(table: Dict[str, Any], vid: int, pid: int, product_name: str = "") -> Optional[Dict[str, Any]]:
    """Resolve a device entry: exact VID/PID first, then product-name substring under the vendor."""
    for entry in table["devices"]:
        if entry["vid"] == vid and entry["pid"] == pid:
            return entry
    name = (product_name or "").lower().strip()
    if name:
        for entry in table["devices"]:
            if entry["vid"] == vid and name in entry["name"].lower():
                return entry
    return None


def resolve_path_identity(table: Dict[str, Any], path, enumerate_fn=None) -> Optional[Dict[str, Any]]:
    """Resolve what a hidraw path actually is. A path names a node, not a device."""
    if enumerate_fn is None:
        try:
            import hid
        except ImportError:
            return None
        enumerate_fn = hid.enumerate
    needle = path.decode() if isinstance(path, bytes) else str(path)
    for item in enumerate_fn():
        item_path = item.get("path")
        item_path = item_path.decode() if isinstance(item_path, bytes) else str(item_path or "")
        if item_path == needle:
            return match_device(table, int(item.get("vendor_id", 0)), int(item.get("product_id", 0)), str(item.get("product_string", "")))
    return None


def check_identity(vid: int, pid: int, product_name: str = "") -> Dict[str, Any]:
    """Return the table entry for a device, or raise when its identity cannot be confirmed."""
    table = load_table()
    entry = match_device(table, vid, pid, product_name)
    if entry is None:
        raise DeviceSecurityException(
            f"SAFETY GUARD: cannot confirm device identity for 0x{vid:04X}:0x{pid:04X} "
            f"({product_name or 'no product string'}) - it is not in the device table, so writes are refused. "
            "Use host-side DSP exporters instead."
        )
    if entry["architecture"] in BLOCKED_ARCHITECTURES:
        raise DeviceSecurityException(
            f"SAFETY GUARD: {entry['name']} (0x{vid:04X}:0x{pid:04X}) is a {entry['chipset']} device - "
            "fixed mask ROM, no hardware PEQ (GEMINI.md Rule 2). Use host-side DSP exporters."
        )
    return entry


def ranges_for(architecture: str) -> Dict[str, float]:
    table = load_table()
    ranges = table["ranges"].get(architecture)
    if ranges is None:
        raise CoefficientRangeError(f"SAFETY GUARD: no accepted ranges for architecture '{architecture}'.")
    return ranges


def band_range_problems(architecture: str, band_index: int, freq: float, gain: float, q: float) -> list:
    """Return the list of accepted-range problems for one band (empty when the band is valid)."""
    r = ranges_for(architecture)
    problems = []
    if not (math.isfinite(freq) and 0 < freq <= r["freq_max_hz"]):
        problems.append(f"band {band_index}: freq {freq} Hz (accepted 0 to {r['freq_max_hz']} Hz)")
    if not (math.isfinite(q) and r["q_min"] <= q <= r["q_max"]):
        problems.append(f"band {band_index}: Q {q} (accepted {r['q_min']} to {r['q_max']})")
    if not (math.isfinite(gain) and r["gain_min_db"] <= gain <= r["gain_max_db"]):
        problems.append(f"band {band_index}: gain {gain} dB (accepted {r['gain_min_db']} to {r['gain_max_db']} dB)")
    return problems


def validate_band(architecture: str, band_index: int, freq: float, gain: float, q: float) -> None:
    problems = band_range_problems(architecture, band_index, freq, gain, q)
    if problems:
        raise CoefficientRangeError("SAFETY GUARD: write rejected - " + "; ".join(problems))
