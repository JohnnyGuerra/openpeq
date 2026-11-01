"""Abstract base class and device factory for USB Audio DSP controllers.

--------------------------------------------------------------------------------
ACKNOWLEDGMENTS & UPSTREAM ATTRIBUTION:
This module establishes a vendor-agnostic hardware DSP abstraction layer
unifying multiple reverse-engineered protocols:
  1. KTMicro KT02H20 / WalkPlay (gxcreator/ktmicro-tools, jeromeof/devicePEQ, Ircama/ja11-config)
  2. Moondrop FreeDSP / Savitech / Comtrue (MiyukiVigil/Hub_Moon)
--------------------------------------------------------------------------------
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from dac_peq import safety

try:
    import hid
except ImportError:
    hid = None


class BaseDSPDevice(ABC):
    """Abstract interface representing a programmable USB Audio DSP hardware device."""

    def __init__(
        self,
        vendor_id: Optional[int] = None,
        product_id: Optional[int] = None,
        path: Optional[bytes] = None,
        use_mock: bool = False,
    ):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.path = path
        self.use_mock = use_mock

    @property
    @abstractmethod
    def max_bands(self) -> int:
        """Maximum number of hardware biquad bands supported by this device."""
        ...

    @property
    @abstractmethod
    def architecture_name(self) -> str:
        """Architecture identifier string."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """Open USB HID handle and verify device connectivity and safety."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close USB HID handle."""
        ...

    def __enter__(self) -> BaseDSPDevice:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @abstractmethod
    def apply_preset(
        self,
        preset: Dict[str, Any],
        commit_flash: bool = False,
        compensate_2x: bool = False,
    ) -> None:
        """Write PEQ bands and preamp to live RAM (or commit to NVRAM flash)."""
        ...

    @abstractmethod
    def read_current_peq(self, compensate_2x: bool = False) -> Dict[str, Any]:
        """Read active PEQ registers from hardware."""
        ...


# Alias for Moondrop FreeDSP device class
try:
    from dac_peq.moondrop import MoondropFreeDSPDevice as MoondropDSPDevice
except ImportError:
    MoondropDSPDevice = None


def get_dsp_device(
    vendor_id: Optional[int] = None,
    product_id: Optional[int] = None,
    path: Optional[bytes] = None,
    use_mock: bool = False,
    mock: Optional[bool] = None,
) -> BaseDSPDevice:
    """Factory creating the appropriate DSP driver instance based on USB IDs."""
    if mock is not None:
        use_mock = mock

    table = safety.load_table()
    entry = safety.match_device(table, vendor_id, product_id) if vendor_id and product_id else None

    if path and not use_mock:
        # A path names a node, not a device: confirm what is actually behind it before writing.
        resolved = safety.resolve_path_identity(table, path)
        if resolved is None:
            raise safety.DeviceSecurityException(
                f"SAFETY GUARD: cannot confirm the identity of the device at path {path!r} - "
                "it is not in the device table, so writes are refused. Use host-side DSP exporters."
            )
        if entry is not None and (entry["vid"], entry["pid"]) != (resolved["vid"], resolved["pid"]):
            raise safety.DeviceSecurityException(
                f"SAFETY GUARD: path {path!r} is {resolved['name']} "
                f"(0x{resolved['vid']:04X}:0x{resolved['pid']:04X}) but the requested ids describe "
                f"{entry['name']} (0x{entry['vid']:04X}:0x{entry['pid']:04X}) - mismatch, so writes are refused."
            )
        entry = resolved

    # Device table is the single source of truth for identity and ranges
    if entry is not None and entry["architecture"] in safety.BLOCKED_ARCHITECTURES:
        raise safety.DeviceSecurityException(
            f"SAFETY GUARD: Device 0x{vendor_id:04X}:0x{product_id or 0:04X} matches {entry['chipset']}. "
            "Hardware DSP access blocked per GEMINI.md Rule 2. "
            f"{entry['chipset']} uses fixed mask ROM with OTP registers. "
            "Use host-side DSP exporters (export-pipewire, export-apo)."
        )

    def driver_for(e, vid, pid, dev_path, mock_flag):
        arch = e["architecture"]
        if arch in ("ktmicro_dsp", "fiio_dsp", "ktmicro_31b2_oem"):
            from dac_peq.ktmicro_hid import KTMicroDSPDevice
            return KTMicroDSPDevice(vid, pid, dev_path, mock_flag)
        if arch == "moondrop_dsp":
            from dac_peq.moondrop import MoondropFreeDSPDevice
            return MoondropFreeDSPDevice(vid, pid, dev_path, mock_flag)
        if arch == "walkplay_dsp":
            from dac_peq.walkplay_hid import WalkPlayDSPDevice
            return WalkPlayDSPDevice(vid, pid, dev_path, mock_flag)
        raise safety.DeviceSecurityException(
            f"SAFETY GUARD: {e['name']} (0x{vid or 0:04X}:0x{pid or 0:04X}) has no confirmed DSP protocol "
            f"in the device table (architecture: {arch}), so writes are refused. "
            "Use host-side DSP exporters (export-pipewire, export-apo)."
        )

    # Auto-discovery when no VID/PID is given and not in mock mode
    if vendor_id is None and product_id is None and not use_mock and hid is not None:
        try:
            for item in hid.enumerate():
                vid = item.get("vendor_id", 0)
                pid = item.get("product_id", 0)
                e = safety.match_device(table, vid, pid, str(item.get("product_string", "")))
                if e is None or e["architecture"] in safety.BLOCKED_ARCHITECTURES:
                    continue
                return driver_for(e, vid, pid, item.get("path"), False)
        except ValueError:
            raise
        except Exception:
            pass

    if entry is None and use_mock:
        # shortcut: a mock device is not hardware, so there is no identity to confirm
        from dac_peq.ktmicro_hid import KTMicroDSPDevice
        return KTMicroDSPDevice(vendor_id, product_id, path, True)

    if entry is None:
        raise safety.DeviceSecurityException(
            f"SAFETY GUARD: cannot confirm the identity of 0x{vendor_id or 0:04X}:0x{product_id or 0:04X} - "
            "it is not in the device table, so writes are refused. "
            "Use host-side DSP exporters (export-pipewire, export-apo)."
        )

    return driver_for(entry, vendor_id, product_id, path, use_mock)
