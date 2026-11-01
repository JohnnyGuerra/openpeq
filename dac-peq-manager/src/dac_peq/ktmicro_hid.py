"""USB HID communication layer for KTMicro KT02H20 / WalkPlay SoC DACs.

Implements the 11-byte register protocol:
  - Report ID: 0x4B ('K')
  - Read: [0x4B, reg, 0x00, 0x00, 0x00, 0x52, 0x00, 0x00, 0x00, 0x00, 0x00]
  - Write Gain/Freq: [0x4B, reg, 0x00, 0x00, 0x00, 0x57, 0x00, gain_lo, gain_hi, freq_lo, freq_hi]
  - Write Q/Type: [0x4B, reg, 0x00, 0x00, 0x00, 0x57, 0x00, q_lo, q_hi, type_byte, 0x00]
  - Write Preamp: [0x4B, 0x66, 0x00, 0x00, 0x00, 0x57, 0x00, gain_byte, 0x00, 0x00, 0x00]
    (0.5 dB resolution: value = round(db * 2))
  - Write DAC Filter: [0x4B, 0x11, 0x00, 0x00, 0x00, 0x57, 0x00, filter_idx, 0x00, 0x00, 0x00]
  - Enable/Slot: [0x4B, 0x24, 0x00, 0x00, 0x00, 0x57, 0x00, slot_id, 0x00, 0x00, 0x00]
  - Commit/Save: [0x4B, 0x00, 0x00, 0x00, 0x00, 0x53, 0x00, 0x00, 0x00, 0x00, 0x00]

Safety Guard (defence in depth):
  - The device table (data/dacs.json) is the single source of truth for what this tool may
    write. It refuses a device whose identity it cannot confirm and a coefficient outside the
    accepted range before any packet is built.
  - It is a guard on this tool only: the hardware offers no protection of its own. A write to a
    fixed-mask-ROM device is accepted by the device and corrupts its OTP descriptor registers.

--------------------------------------------------------------------------------
ACKNOWLEDGMENTS & UPSTREAM ATTRIBUTION:
This module incorporates protocol research, register mapping, and hardware
workarounds reverse-engineered by the open-source community:
  1. gxcreator/ktmicro-tools (https://github.com/gxcreator/ktmicro-tools):
     - Reverse-engineered KT02H20 11-byte USB HID report framing.
     - Register map layout: 0x24 (DAC EQ Enable), 0x26-0x2F (Bands 1-5 A/B registers).
     - Digital volume/preamp register 0x66 signed byte 0.5 dB resolution (dig_encode/decode).
  2. jeromeof/devicePEQ (https://github.com/jeromeof/devicePEQ):
     - USB HID hardware capture traces for Kiwi Ears Allegro Mini (0x31B2:0x0111).
     - Identification of the KT Micro 'compensate2X' frequency scaling clock divisor bug.
     - Post-commit USB PHY bus re-enumeration handling ('disconnectOnSave').
  3. Ircama/ja11-config (https://github.com/Ircama/ja11-config):
     - KT02H20 FIR digital reconstruction filter constants at register 0x11
       (FAST-LL, FAST-PC, SLOW-LL, SLOW-PC, NON-OS).
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from dac_peq import safety
from dac_peq.transport import BaseDSPDevice

try:
    import hid
except ImportError:
    hid = None


# Known KTMicro / WalkPlay Vendor IDs
KTMICRO_KNOWN_VIDS = [
    0x31B2,  # KTMicro / JCALLY / Kiwi Ears Allegro Mini
    0x2972,  # FiiO / JadeAudio JA11
    0x3302,  # KTMicro / Kiwi Ears OEM Type-C DACs
    0x0BDA,  # Realtek / WalkPlay OEM
    0x0661,  # KTMicro OEM
    0x262A,  # WalkPlay OEM
]

# Blocked hardware: Conexant CX31993 (Fixed Mask ROM - DO NOT FLASH). The device answers writes;
# nothing on the device refuses them, so the refusal has to happen here.
CONEXANT_VID = 0x0572
CONEXANT_PID = 0x1B08
KNOWN_CONEXANT_DEVICES = [
    (0x0572, 0x1B08),  # Conexant / JCALLY JM6 / JM6 Pro
    (0x3302, 0x3365),  # TTGK Technology CX31993 384kHz HiFi Audio
]

WALKPLAY_PIDS = {0xC20F, 0x43CC, 0x4362, 0x431D, 0x4307, 0x4353}
NON_FLASHABLE_FIIO_PIDS = {0x0047, 0x0066, 0x0104, 0x0105, 0x0107}
MOONDROP_FREEDSP_PID = 0x0112


DeviceSecurityException = safety.DeviceSecurityException

class DeviceCommunicationError(Exception):
    """Raised when HID communication fails or device times out."""
    pass


@dataclass
class DiscoveredDevice:
    vendor_id: int
    product_id: int
    path: bytes
    manufacturer_string: str
    product_string: str
    serial_number: str
    release_number: int = 0x0100
    firmware_quirks: Optional[Dict[str, Any]] = None
    is_ktmicro: bool = False
    is_conexant: bool = False
    status_description: str = ""

    @property
    def vid_pid_hex(self) -> str:
        return f"0x{self.vendor_id:04X}:0x{self.product_id:04X}"


def detect_firmware_quirks(
    vendor_id: int,
    product_id: int,
    release_number: int = 0x0100,
    product_string: str = "",
) -> Dict[str, Any]:
    """Detect firmware revision and clock divisor quirks for KTMicro KT02H20 hardware.

    Generic KT02H20 firmwares (and older OEM builds like Kiwi Ears Allegro Mini with
    bcdDevice <= 0x0100) run internal DSP biquads with a 2X frequency divisor at 48kHz,
    requiring frequency values to be halved (f / 2) when writing registers.

    Modern revisions (such as FiiO JA11 v1.8+ with bcdDevice >= 0x0180 or firmware > v1.0)
    corrected this internally in MCU firmware.

    Returns:
        {
            'requires_compensate_2x': bool,
            'firmware_version': str (e.g. '1.0', '1.8', '2.0'),
            'release_number': int,
            'description': str,
        }
    """
    major = (release_number >> 8) & 0xFF
    minor = (release_number >> 4) & 0x0F
    patch = release_number & 0x0F
    version_str = f"{major}.{minor}"
    if patch != 0:
        version_str += f".{patch}"

    # FiiO JA11 firmware v1.8+ (release_number >= 0x0180) or modern firmwares (> 0x0100) resolved the bug
    if (vendor_id == 0x2972 and release_number >= 0x0180) or release_number > 0x0100:
        return {
            "requires_compensate_2x": False,
            "firmware_version": version_str,
            "release_number": release_number,
            "description": f"Firmware v{version_str}: Native clocking (no 2X divisor needed)",
        }

    # Older generic KT02H20 with bcdDevice <= 0x0100 has the 2X clock divisor bug
    return {
        "requires_compensate_2x": True,
        "firmware_version": version_str,
        "release_number": release_number,
        "description": f"Detected Firmware v{version_str} (2X clock divisor quirk active)",
    }


def is_conexant_cx31993(dev_info: Dict[str, Any]) -> bool:
    """Check if a device is a Conexant CX31993 fixed-mask-ROM part (table match or USB descriptor string)."""
    vid = dev_info.get("vendor_id", 0)
    pid = dev_info.get("product_id", 0)
    entry = safety.match_device(safety.load_table(), vid, pid, str(dev_info.get("product_string", "")))
    if entry is not None and entry["architecture"] in safety.BLOCKED_ARCHITECTURES:
        return True
    prod = str(dev_info.get("product_string", "")).lower()
    mfg = str(dev_info.get("manufacturer_string", "")).lower()
    return "cx31993" in prod or "cx31993" in mfg or "conexant" in prod or "conexant" in mfg


def is_ktmicro_candidate(dev_info: Dict[str, Any]) -> bool:
    """Check if device descriptor matches supported KTMicro KT02H20 hardware.

    Explicitly excludes Conexant CX31993, Moondrop FreeDSP, WalkPlay devices,
    and non-flashable FiiO devices per GEMINI.md safety rules.
    """
    if is_conexant_cx31993(dev_info):
        return False

    vid = dev_info.get("vendor_id", 0)
    pid = dev_info.get("product_id", 0)
    prod = str(dev_info.get("product_string", "")).lower()
    mfg = str(dev_info.get("manufacturer_string", "")).lower()

    # 1. Safety Guard: Exclude Conexant CX31993
    if vid == CONEXANT_VID or (vid == 0x3302 and pid == 0x3365) or "cx31993" in prod or "cx31993" in mfg:
        return False

    # 2. Exclude Moondrop FreeDSP (0x31B2:0x0112)
    if vid == 0x31B2 and pid == MOONDROP_FREEDSP_PID:
        return False

    # 3. Exclude known WalkPlay PIDs under 0x3302
    if vid == 0x3302 and pid in WALKPLAY_PIDS:
        return False

    # 4. Exclude non-flashable FiiO PIDs
    if vid == 0x2972 and pid in NON_FLASHABLE_FIIO_PIDS:
        return False

    # KTMicro supported VIDs
    if vid == 0x31B2:
        return True
    if vid == 0x2972:
        return True
    if vid == 0x1908:
        return True
    if vid in (0x0661, 0x3302, 0x0BDA, 0x262A):
        return True

    kt_keywords = ["allegro", "bmaster", "kt02h20", "ktmicro", "ja11", "jm12", "s-link", "slink", "kt0211", "kt1132", "kt3016"]
    if any(k in prod or k in mfg for k in kt_keywords):
        return True

    return False


def scan_devices() -> List[DiscoveredDevice]:
    """Scan and classify all connected USB HID audio/DSP devices."""
    if hid is None:
        return []

    results: List[DiscoveredDevice] = []
    seen_paths = set()

    for item in hid.enumerate():
        path = item.get("path", b"")
        if path in seen_paths:
            continue
        seen_paths.add(path)

        vid = item.get("vendor_id", 0)
        pid = item.get("product_id", 0)
        prod = item.get("product_string") or "Unknown Device"
        mfg = item.get("manufacturer_string") or ""
        serial = item.get("serial_number") or ""

        is_cx = is_conexant_cx31993(item)
        is_kt = is_ktmicro_candidate(item)

        release_number = item.get("release_number", 0x0100)
        quirks = detect_firmware_quirks(vid, pid, release_number, prod)

        if is_cx:
            status = "Host DSP Only (Conexant CX31993 - Flash BLOCKED for hardware safety)"
        elif is_kt:
            status = f"Hardware Flashable (KTMicro KT02H20 HID - FW v{quirks['firmware_version']})"
        elif vid == 0x31B2 and pid == MOONDROP_FREEDSP_PID:
            status = "Hardware Flashable (Moondrop FreeDSP Custom HID)"
        elif vid == 0x3302 and pid in WALKPLAY_PIDS:
            status = "Hardware Flashable (WalkPlay Scheme 11/15/16 HID)"
        else:
            status = "Standard USB HID Device"

        results.append(
            DiscoveredDevice(
                vendor_id=vid,
                product_id=pid,
                path=path,
                manufacturer_string=mfg,
                product_string=prod,
                serial_number=serial,
                release_number=release_number,
                firmware_quirks=quirks,
                is_ktmicro=is_kt,
                is_conexant=is_cx,
                status_description=status,
            )
        )

    return results


class MockKTDevice:
    """Emulates KTMicro KT02H20 USB HID registers for testing and dry-run without hardware."""

    def __init__(self, vendor_id: int = 0x31B2, product_id: int = 0x0111, release_number: int = 0x0200):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.release_number = release_number
        self.is_open = True
        self.ram_registers: Dict[int, List[int]] = {}
        self.nvram_registers: Dict[int, List[int]] = {}
        self.last_sent: List[int] = []
        self.response_queue: List[List[int]] = []
        self.commit_count = 0

        # Initialize defaults
        self._init_defaults()

    def _init_defaults(self):
        # Register 0x24: EQ slot (default active slot = 0x03)
        self.ram_registers[0x24] = [0x24, 0, 0, 0, 0x57, 0, 0x03, 0, 0, 0]
        # Register 0x66: Preamp (0.0 dB, 0.5 dB steps: 0*2 = 0)
        self.ram_registers[0x66] = [0x66, 0, 0, 0, 0x57, 0, 0x00, 0, 0, 0]
        # Register 0x11: DAC Digital Filter (1 = FAST-LL default)
        self.ram_registers[0x11] = [0x11, 0, 0, 0, 0x57, 0, 0x01, 0, 0, 0]

        default_freqs = [100, 500, 1000, 2500, 10000]
        for i in range(5):
            gf_reg = 0x26 + i * 2
            q_reg = gf_reg + 1
            freq = default_freqs[i]
            # gain=0, freq
            self.ram_registers[gf_reg] = [gf_reg, 0, 0, 0, 0x57, 0, 0, 0, freq & 0xFF, (freq >> 8) & 0xFF]
            # Q=1.00 (1000), type=0 (PK)
            self.ram_registers[q_reg] = [q_reg, 0, 0, 0, 0x57, 0, 232, 3, 0, 0]

        self.nvram_registers = {k: list(v) for k, v in self.ram_registers.items()}

    def write(self, data: Sequence[int]) -> int:
        pkt = list(data)
        self.last_sent = pkt
        if not pkt or pkt[0] != 0x4B:
            return len(data)

        payload = pkt[1:]
        reg = payload[0]
        cmd = payload[4]

        if cmd == 0x52:  # READ
            # Respond with current register content
            content = self.ram_registers.get(reg, [reg, 0, 0, 0, 0x52, 0, 0, 0, 0, 0])
            resp = [0x4B] + list(content)
            resp[5] = 0x52  # CMD byte in report response
            self.response_queue.append(resp)

        elif cmd == 0x57:  # WRITE to RAM
            self.ram_registers[reg] = list(payload)

        elif cmd == 0x53:  # COMMIT to NVRAM
            self.nvram_registers = {k: list(v) for k, v in self.ram_registers.items()}
            self.commit_count += 1
            # Commit ACK response
            self.response_queue.append([0x4B, 0, 0, 0, 0, 0x53, 0, 3, 0, 0, 0])

        elif cmd == 0x43:  # CLEAR / RESET
            self._init_defaults()
            self.response_queue.append([0x4B, 0, 0, 0, 0, 0x43, 0, 0, 0, 0, 0])

        return len(data)

    def read(self, max_length: int, timeout_ms: int = 500) -> List[int]:
        if self.response_queue:
            return self.response_queue.pop(0)
        return []

    def close(self):
        self.is_open = False


class KTMicroDSPDevice(BaseDSPDevice):
    """Manages high-level PEQ operations for KTMicro KT02H20 / WalkPlay DSP DACs."""

    BASE_REG_OFFSET = 0x26
    REG_SLOT = 0x24
    REG_PREAMP = 0x66
    REG_DAC_FILTER = 0x11
    REPORT_ID = 0x4B
    CMD_READ = 0x52    # 'R'
    CMD_WRITE = 0x57   # 'W'
    CMD_COMMIT = 0x53  # 'S'
    CMD_CLEAR = 0x43   # 'C'

    @property
    def max_bands(self) -> int:
        return 5

    @property
    def architecture_name(self) -> str:
        return "ktmicro_dsp"

    TYPE_MAP = {
        "PK": 0,
        "PEAK": 0,
        "PEAKING": 0,
        "LPF": 1,
        "HPF": 2,
        "LSQ": 3,
        "LOW_SHELF": 3,
        "LOWSHELF": 3,
        "HSQ": 4,
        "HIGH_SHELF": 4,
        "HIGHSHELF": 4,
    }

    TYPE_REV_MAP = {
        0: "PK",
        1: "LPF",
        2: "HPF",
        3: "LSQ",
        4: "HSQ",
    }

    DAC_FILTERS = {
        "FAST-LL": 1,  # Fast roll-off, linear phase
        "FAST-PC": 2,  # Fast roll-off, phase compensation
        "SLOW-LL": 3,  # Slow roll-off, linear phase
        "SLOW-PC": 4,  # Slow roll-off, phase compensation
        "NON-OS": 5,   # Non-oversampling (NOS)
    }

    DAC_FILTERS_REV = {v: k for k, v in DAC_FILTERS.items()}

    def __init__(
        self,
        vendor_id: Optional[int] = None,
        product_id: Optional[int] = None,
        path: Optional[bytes] = None,
        use_mock: bool = False,
        no_pregain: bool = False,
    ):
        self._vid = vendor_id
        self._pid = product_id
        self.path = path
        self.use_mock = use_mock
        self.no_pregain = no_pregain
        self._dev = None
        self.release_number: int = 0x0200
        self.firmware_quirks: Optional[Dict[str, Any]] = None

    @property
    def vendor_id(self) -> Optional[int]:
        return self._vid

    @vendor_id.setter
    def vendor_id(self, val: Optional[int]) -> None:
        self._vid = val

    @property
    def product_id(self) -> Optional[int]:
        return self._pid

    @product_id.setter
    def product_id(self, val: Optional[int]) -> None:
        self._pid = val

    def is_allegro_mini_or_no_pregain(self) -> bool:
        """True when the device is Kiwi Ears (0x31B2), records noPregain quirk, or is configured with no_pregain."""
        vid = self._vid if self._vid is not None else self.vendor_id
        if vid == 0x31B2:
            return True
        if self.no_pregain:
            return True
        if self.firmware_quirks and self.firmware_quirks.get("no_pregain"):
            return True
        entry = safety.match_device(safety.load_table(), vid, self._pid)
        return bool(entry) and "noPregain" in (entry.get("quirks") or [])

    def supports_dac_filter(self) -> bool:
        """True strictly for FiiO JA11 (0x2972) with fiio_dac_filter quirk, or unconfigured mock devices."""
        if self.is_allegro_mini_or_no_pregain():
            return False
        vid = self._vid if self._vid is not None else self.vendor_id
        if vid is None and self.use_mock:
            return True
        entry = safety.match_device(safety.load_table(), vid, self._pid)
        if entry:
            return "fiio_dac_filter" in (entry.get("quirks") or []) or entry.get("architecture") == "fiio_dsp"
        return vid == 0x2972

    def connect(self):
        """Connect to target HID device with safety verification."""
        vid = self._vid if self._vid is not None else self.vendor_id
        pid = self._pid if self._pid is not None else self.product_id

        # Safety guard before anything is opened: identity must be confirmed from the table.
        # Runs without the hid library so a blocked device is refused even when it is not present.
        if not self.use_mock and vid is not None and pid is not None:
            safety.check_identity(vid, pid)

        if self.use_mock:
            self._dev = MockKTDevice(vid or 0x31B2, pid or 0x0111)
            self.firmware_quirks = detect_firmware_quirks(self._dev.vendor_id, self._dev.product_id, self._dev.release_number)
            return

        if hid is None:
            raise DeviceCommunicationError("Python 'hid' library is not available.")

        # A path carries no identity: resolve it against the table before opening it.
        if self.path:
            item = next((i for i in hid.enumerate() if i["path"] == self.path), None)
            if item is None:
                raise DeviceSecurityException(
                    f"SAFETY GUARD: cannot confirm the identity behind path {self.path!r} - it is not in the "
                    "device table, so writes are refused. Use host-side DSP exporters instead."
                )
            entry = safety.check_identity(item["vendor_id"], item["product_id"], item.get("product_string", ""))
            self._entry = entry
            self.vendor_id, self.product_id = item["vendor_id"], item["product_id"]
            self._dev = hid.device()
            self._dev.open_path(self.path)
            self.release_number = item.get("release_number", 0x0100)
            self.firmware_quirks = detect_firmware_quirks(self.vendor_id, self.product_id, self.release_number, item.get("product_string", ""))
            return

        # If VID/PID specified, find and verify
        if vid is not None and pid is not None:
            for item in hid.enumerate(vid, pid):
                entry = safety.check_identity(item["vendor_id"], item["product_id"], item.get("product_string", ""))
                self._entry = entry
                self._dev = hid.device()
                self._dev.open_path(item["path"])
                self.release_number = item.get("release_number", 0x0100)
                prod_str = item.get("product_string", "")
                self.firmware_quirks = detect_firmware_quirks(vid, pid, self.release_number, prod_str)
                return
            raise DeviceCommunicationError(f"Device 0x{vid:04X}:0x{pid:04X} not found.")

        # Otherwise dynamic scan for KTMicro candidate
        candidates = scan_devices()
        kt_candidates = [d for d in candidates if d.is_ktmicro and not d.is_conexant]
        if not kt_candidates:
            raise DeviceCommunicationError(
                "No compatible KTMicro / WalkPlay DSP DAC found. "
                "Ensure device is connected and udev rules are installed."
            )

        # Open the first matching KTMicro candidate
        chosen = kt_candidates[0]
        self._vid = chosen.vendor_id
        self._pid = chosen.product_id
        self.release_number = chosen.release_number
        self.firmware_quirks = chosen.firmware_quirks
        self._dev = hid.device()
        self._dev.open_path(chosen.path)

    def close(self):
        if self._dev:
            self._dev.close()
            self._dev = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _send_packet(self, reg: int, cmd: int, d0: int = 0, d1: int = 0, d2: int = 0, d3: int = 0) -> None:
        """Frame and send an 11-byte report to the DAC."""
        report = [
            self.REPORT_ID,
            reg & 0xFF,
            0x00,
            0x00,
            0x00,
            cmd & 0xFF,
            0x00,
            d0 & 0xFF,
            d1 & 0xFF,
            d2 & 0xFF,
            d3 & 0xFF,
        ]
        if not self._dev:
            raise DeviceCommunicationError("Device not connected.")
        self._dev.write(report)

    def _read_register(self, reg: int, timeout_ms: int = 500) -> List[int]:
        """Send a READ request for register and return the received payload matching reg."""
        self._send_packet(reg=reg, cmd=self.CMD_READ)
        start_time = time.time()
        while (time.time() - start_time) * 1000 < timeout_ms:
            resp = self._dev.read(64, timeout_ms=50)
            if not resp:
                continue
            # Strip ReportID byte if returned by backend
            if resp[0] == self.REPORT_ID:
                resp = resp[1:]
            # Ensure packet is the READ response for requested register
            if len(resp) >= 6 and resp[0] == reg and resp[4] == self.CMD_READ:
                return resp

        raise DeviceCommunicationError(f"Timeout reading register 0x{reg:02X}.")

    def set_dac_filter(self, filter_name: str, commit_flash: bool = False) -> None:
        """Set hardware DAC reconstruction filter (FAST-LL, FAST-PC, SLOW-LL, SLOW-PC, NON-OS)."""
        if not self.supports_dac_filter():
            raise ValueError(
                "Register 0x11 (DAC reconstruction filter) is strictly a FiiO JA11 (0x2972) feature. "
                "Writing to register 0x11 on non-FiiO KTMicro hardware is blocked to prevent volume "
                "control lockout per GEMINI.md Rule 1."
            )
        idx = self.DAC_FILTERS.get(filter_name.upper())
        if not idx:
            valid = ", ".join(self.DAC_FILTERS.keys())
            raise ValueError(f"Unknown filter '{filter_name}'. Valid options: {valid}")
        self._send_packet(self.REG_DAC_FILTER, self.CMD_WRITE, idx, 0, 0, 0)
        time.sleep(0.02)
        if commit_flash:
            self._send_packet(0x00, self.CMD_COMMIT, 0, 0, 0, 0)
            time.sleep(0.05)
            try:
                self._dev.read(64, timeout_ms=300)
            except Exception:
                pass

    def apply_preset(
        self,
        preset: Dict[str, Any],
        commit_flash: bool = False,
        compensate_2x: Optional[bool] = None,
    ) -> None:
        """Write 5-band PEQ and preamp into the DAC.

        If commit_flash is True, commits settings to onboard NVRAM.
        If compensate_2x is True, compensates for older KT02H20 firmwares with 2x frequency offset.
        If compensate_2x is None, auto-detected from firmware quirks/heuristics.
        """
        if compensate_2x is None:
            compensate_2x = bool(self.firmware_quirks.get("requires_compensate_2x", False)) if self.firmware_quirks else False

        bands = preset.get("bands", [])
        if len(bands) < 5:
            raise ValueError(f"Preset requires 5 bands, got {len(bands)}.")

        # Validate every band against the table before anything is packed: a rejected
        # write is aborted in full, never partially applied. Frequencies are checked as the
        # user asked for them, before the compensate_2x halving.
        for i, b in enumerate(bands):
            safety.validate_band(self.architecture_name, i, float(b.get("freq", 1000.0)), float(b.get("gain", 0.0)), float(b.get("q", 1.0)))

        # 1. Enable EQ slot (Slot 0x03)
        slot_id = preset.get("slot_id", 0x03)
        self._send_packet(reg=self.REG_SLOT, cmd=self.CMD_WRITE, d0=slot_id)
        time.sleep(0.01)

        # 2. Write 5 bands
        for i in range(5):
            band = bands[i]
            enabled = band.get("enabled", True)
            gain = float(band.get("gain", 0.0)) if enabled else 0.0
            freq = float(band.get("freq", 1000.0))
            if compensate_2x:
                freq = freq / 2.0
            q = float(band.get("q", 1.0))
            ftype = str(band.get("type", "PK")).upper()

            # Encode Gain: signed 16-bit little-endian, scaled x 10
            gain_scaled = int(round(gain * 10.0))
            if gain_scaled < 0:
                gain_scaled += 0x10000
            gain_lo = gain_scaled & 0xFF
            gain_hi = (gain_scaled >> 8) & 0xFF

            # Encode Frequency: unsigned 16-bit little-endian, Hz
            freq_val = int(round(freq))
            freq_lo = freq_val & 0xFF
            freq_hi = (freq_val >> 8) & 0xFF

            # Encode Q: unsigned 16-bit little-endian, scaled x 1000
            q_scaled = int(round(q * 1000.0))
            q_lo = q_scaled & 0xFF
            q_hi = (q_scaled >> 8) & 0xFF

            # Encode Type
            type_val = self.TYPE_MAP.get(ftype, 0)

            # Register addresses
            reg_gf = self.BASE_REG_OFFSET + i * 2
            reg_q = reg_gf + 1

            # Fire register writes (Gain/Freq then Q/Type)
            self._send_packet(reg_gf, self.CMD_WRITE, gain_lo, gain_hi, freq_lo, freq_hi)
            time.sleep(0.01)
            self._send_packet(reg_q, self.CMD_WRITE, q_lo, q_hi, type_val, 0x00)
            time.sleep(0.01)

        # 3. Write Preamp (Register 0x66)
        # KTMicro stores signed digital gain with 0.5 dB steps: value = round(gain_db * 2)
        # Per GEMINI.md Rule 1: skip register 0x66 on Allegro Mini / no_pregain to prevent volume lockout
        # Preamp is clamped to [-24.0, +12.0] dB to prevent signed int8 overflow/acoustic safety hazard.
        if not self.is_allegro_mini_or_no_pregain():
            preamp_val = preset.get("preamp")
            try:
                preamp_db = float(preamp_val) if preamp_val is not None else 0.0
                if math.isnan(preamp_db):
                    preamp_db = 0.0
            except (ValueError, TypeError):
                preamp_db = 0.0
            clamped_preamp = max(-24.0, min(12.0, preamp_db))
            preamp_encoded = int(round(clamped_preamp * 2.0)) & 0xFF
            self._send_packet(self.REG_PREAMP, self.CMD_WRITE, preamp_encoded, 0x00, 0x00, 0x00)
            time.sleep(0.01)

        # 4. Optional NVRAM Flash Commit
        if commit_flash:
            # Commit command to register 0x00
            try:
                self._send_packet(0x00, self.CMD_COMMIT, 0x00, 0x00, 0x00, 0x00)
                time.sleep(0.05)
                # Read and consume commit ACK
                self._dev.read(64, timeout_ms=300)
            except Exception:
                # Catch expected post-commit soft-reboot detachment
                pass
            self._wait_for_reenumeration()

    def factory_reset(self) -> None:
        """Send hardware 0x43 CLEAR command to wipe flash and restore factory defaults."""
        self._send_packet(0x00, self.CMD_CLEAR, 0x00, 0x00, 0x00, 0x00)
        time.sleep(0.05)
        try:
            self._dev.read(64, timeout_ms=300)
        except Exception:
            pass
        self._wait_for_reenumeration()

    def _wait_for_reenumeration(
        self,
        timeout_s: float = 4.0,
        poll_interval_s: float = 0.15,
        enumerate_fn: Optional[Any] = None,
    ) -> bool:
        """Poll USB HID enumeration after 0x53 NVRAM commit until the microcontroller re-attaches."""
        if self.use_mock and enumerate_fn is None:
            return True

        enum_callable = enumerate_fn or (hid.enumerate if hid is not None else None)
        if enum_callable is None:
            return False

        vid = self.vendor_id or 0x31B2
        pid = self.product_id or 0x0111

        if enumerate_fn is None:
            time.sleep(0.20)  # Grace window for microcontroller soft-reset initiation

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                matches = enum_callable(vid, pid)
                if matches:
                    if not self.use_mock and hid is not None:
                        try:
                            self._dev.close()
                        except Exception:
                            pass
                        self._dev = hid.device()
                        self._dev.open_path(matches[0]["path"])
                    return True
            except Exception:
                pass
            time.sleep(poll_interval_s)

        return False

    def read_current_peq(self, compensate_2x: Optional[bool] = None) -> Dict[str, Any]:
        """Read 5 bands, global preamp, and active slot from the hardware registers.

        Read-back detection only: this reports what the registers answer, it cannot confirm that an
        earlier write landed. A fixed-mask-ROM device answers with its ROM contents, not with the
        values that were written.

        If compensate_2x is None, auto-detected from the device table quirks/heuristics.
        """
        if compensate_2x is None:
            compensate_2x = bool(self.firmware_quirks.get("requires_compensate_2x", False)) if self.firmware_quirks else False

        # 1. Read active slot
        slot_resp = self._read_register(self.REG_SLOT)
        slot_id = slot_resp[6] if len(slot_resp) > 6 else 0x03

        # 2. Read preamp (0.5 dB step decoding: signed_byte / 2.0)
        # Per GEMINI.md Rule 1: skip register 0x66 on Allegro Mini / no_pregain to prevent volume lockout
        if self.is_allegro_mini_or_no_pregain():
            preamp_db = 0.0
        else:
            preamp_resp = self._read_register(self.REG_PREAMP)
            raw_preamp = preamp_resp[6] if len(preamp_resp) > 6 else 0
            signed_preamp = raw_preamp - 256 if raw_preamp > 127 else raw_preamp
            preamp_db = round(signed_preamp / 2.0, 1)

        # 3. Read DAC reconstruction filter (Register 0x11)
        # Strictly a FiiO JA11 (0x2972) feature; skipped on other KTMicro devices to prevent volume lockout
        if self.supports_dac_filter():
            try:
                filter_resp = self._read_register(self.REG_DAC_FILTER, timeout_ms=200)
                filter_idx = filter_resp[6] if len(filter_resp) > 6 else 1
                filter_name = self.DAC_FILTERS_REV.get(filter_idx, f"FILTER_{filter_idx}")
            except Exception:
                filter_name = "FAST-LL"
        else:
            filter_name = None

        # 4. Read 5 bands
        bands = []
        for i in range(5):
            reg_gf = self.BASE_REG_OFFSET + i * 2
            reg_q = reg_gf + 1

            gf_resp = self._read_register(reg_gf)
            q_resp = self._read_register(reg_q)

            # Decode gain & freq
            gain_raw = gf_resp[6] | (gf_resp[7] << 8)
            gain_signed = gain_raw - 0x10000 if gain_raw > 0x7FFF else gain_raw
            gain_db = round(gain_signed / 10.0, 1)

            freq_hz = float(gf_resp[8] | (gf_resp[9] << 8))
            if compensate_2x:
                freq_hz = freq_hz * 2.0

            # Decode Q & filter type
            q_raw = q_resp[6] | (q_resp[7] << 8)
            q_val = round(q_raw / 1000.0, 2)
            type_val = q_resp[8]
            ftype = self.TYPE_REV_MAP.get(type_val, "PK")

            bands.append({
                "index": i + 1,
                "type": ftype,
                "freq": freq_hz,
                "gain": gain_db,
                "q": q_val,
            })

        return {
            "slot_id": slot_id,
            "preamp": preamp_db,
            "dac_filter": filter_name,
            "bands": bands,
        }
