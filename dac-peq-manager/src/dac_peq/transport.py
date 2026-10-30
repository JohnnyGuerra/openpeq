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

    # Conexant CX31993 hardware safety guardrail per GEMINI.md Rule 2
    if vendor_id == 0x0572 or (vendor_id == 0x3302 and product_id == 0x3365):
        raise ValueError(
            f"SAFETY GUARD: Device 0x{vendor_id:04X}:0x{product_id or 0:04X} matches Conexant CX31993. "
            "Hardware DSP access blocked per GEMINI.md Rule 2. "
            "Conexant CX31993 uses fixed mask ROM with OTP registers. "
            "Use host-side DSP exporters (export-pipewire, export-apo)."
        )

    # When no VID/PID is provided and not running in mock mode, attempt auto-discovery
    if vendor_id is None and product_id is None and not use_mock and hid is not None:
        try:
            walkplay_pids = {0xC20F, 0x43CC, 0x4362, 0x431D, 0x4307, 0x4353}
            for item in hid.enumerate():
                vid = item.get("vendor_id", 0)
                pid = item.get("product_id", 0)
                prod = str(item.get("product_string", "")).lower()

                # Safety guard: skip Conexant CX31993
                if vid == 0x0572 or (vid == 0x3302 and pid == 0x3365) or "cx31993" in prod:
                    continue

                # Check Moondrop FreeDSP
                if vid == 0x31B2 and pid == 0x0112:
                    from dac_peq.moondrop import MoondropFreeDSPDevice
                    return MoondropFreeDSPDevice(vid, pid, path=item.get("path"), use_mock=False)

                # Check WalkPlay devices
                if vid == 0x3302 and pid in walkplay_pids:
                    from dac_peq.walkplay_hid import WalkPlayDSPDevice
                    return WalkPlayDSPDevice(vid, pid, path=item.get("path"), use_mock=False)

                # Check KTMicro devices (Kiwi Ears Allegro Mini, FiiO JA11, JM12, etc.)
                if vid in (0x31B2, 0x2972, 0x1908):
                    from dac_peq.ktmicro_hid import KTMicroDSPDevice
                    return KTMicroDSPDevice(vid, pid, path=item.get("path"), use_mock=False)
        except Exception:
            pass

    # Explicit or fallback routing based on VID/PID
    if vendor_id == 0x31B2 and product_id == 0x0112:
        from dac_peq.moondrop import MoondropFreeDSPDevice
        return MoondropFreeDSPDevice(vendor_id, product_id, path, use_mock)

    walkplay_pids = (0xC20F, 0x43CC, 0x4362, 0x431D, 0x4307, 0x4353)
    if vendor_id == 0x3302 and product_id in walkplay_pids:
        from dac_peq.walkplay_hid import WalkPlayDSPDevice
        return WalkPlayDSPDevice(vendor_id, product_id, path, use_mock)

    from dac_peq.ktmicro_hid import KTMicroDSPDevice
    return KTMicroDSPDevice(vendor_id, product_id, path, use_mock)
