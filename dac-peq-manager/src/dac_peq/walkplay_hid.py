"""WalkPlay Scheme 11 & Scheme 16 hardware protocol adapter.

--------------------------------------------------------------------------------
ACKNOWLEDGMENTS & UPSTREAM ATTRIBUTION:
This module incorporates reverse-engineered packet framing and biquad arithmetic
derived from:
  1. CrinEar Protocol Micro (0x3302:0xC20F) & Protocol Max (0x3302:0x43CC) captures
     contributed by GitHub / r/chifi community member @demomanca.
  2. WalkPlay USB HID handler protocol implementations (jeromeof/devicePEQ, 0BSD License).
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import math
import struct
import time
from typing import Any, Dict, List, Optional, Sequence

from dac_peq import safety

try:
    import hid
except ImportError:
    hid = None

from dac_peq.ktmicro_hid import DeviceCommunicationError, DeviceSecurityException
from dac_peq.transport import BaseDSPDevice


class MockWalkPlayDevice:
    """Mock device emulating WalkPlay Scheme 11 / 16 HID endpoints for unit testing."""

    def __init__(
        self,
        vendor_id: int = 0x3302,
        product_id: int = 0xC20F,
        max_bands: int = 8,
    ):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.max_bands = max_bands
        self.is_open = True
        self.written_reports: List[List[int]] = []
        self.commit_count = 0
        self.current_slot = 101
        self.global_gain = 0

        # Initial flat bands
        self.filters: List[Dict[str, Any]] = [
            {"freq": 1000, "q": 1.0, "gain": 0.0, "type": "PK"}
            for _ in range(self.max_bands)
        ]

    def write(self, data: Sequence[int]) -> int:
        pkt = list(data)
        self.written_reports.append(pkt)

        # Strip report ID if present
        if pkt and pkt[0] == 0x4B:
            body = pkt[1:]
        else:
            body = pkt

        # Write filter packet: [0x01, 0x09, 0x18, 0x00, filter_idx, ...]
        if len(body) >= 37 and body[0] == 0x01 and body[1] == 0x09:
            filter_idx = body[4]
            if filter_idx < len(self.filters):
                freq, q_raw, gain_raw = struct.unpack("<HHh", bytes(body[27:33]))
                type_id = body[33]
                type_map = {1: "LSQ", 2: "PK", 3: "HSQ", 4: "LP", 5: "HP"}
                self.filters[filter_idx] = {
                    "freq": freq,
                    "q": round(q_raw / 256.0, 2),
                    "gain": round(gain_raw / 256.0, 2),
                    "type": type_map.get(type_id, "PK"),
                }

        # Write global gain: [0x01, 0x03, 0x02, 0x00, gain_val]
        elif len(body) >= 5 and body[0] == 0x01 and body[1] == 0x03:
            gain_val = body[4]
            if gain_val > 127:
                gain_val -= 256
            self.global_gain = gain_val

        # Flash commit sequence final command: [0x01, 0x01, 0x01, 0x00]
        elif len(body) >= 3 and body[0] == 0x01 and body[1] == 0x01:
            self.commit_count += 1

        return len(data)

    def read(self, max_length: int, timeout_ms: int = 500) -> List[int]:
        # Return generic response buffer
        return [0x00] * max_length

    def close(self):
        self.is_open = False


def compute_walkplay_biquad(freq: float, gain: float, q: float) -> bytes:
    """Compute 20-byte Q2.30 biquad coefficient array at 96 kHz sampling rate."""
    if abs(gain) < 1e-6:
        return bytes(20)

    a = 10.0 ** (gain / 40.0)
    w0 = (freq * 2.0 * math.pi) / 96000.0
    sinw0 = math.sin(w0)
    cosw0 = math.cos(w0)
    alpha = sinw0 / (2.0 * max(q, 0.01))

    b0 = 1.0 + alpha * a
    b1 = -2.0 * cosw0
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cosw0
    a2 = 1.0 - alpha / a

    scale = 1073741824.0  # 2^30
    i_b0 = round(b0 / a0 * scale)
    i_b1 = round(b1 / a0 * scale)
    i_b2 = round(b2 / a0 * scale)
    i_neg_a1 = round(-(a1 / a0) * scale)
    i_neg_a2 = round(-(a2 / a0) * scale)

    return struct.pack("<5i", i_b0, i_b1, i_b2, i_neg_a1, i_neg_a2)


def encode_walkplay_filter_packet(
    filter_idx: int,
    freq: float,
    gain: float,
    q: float,
    filter_type: str = "PK",
    slot: int = 101,
) -> bytes:
    """Encode a 37-byte WalkPlay filter packet."""
    type_map = {"LSQ": 1, "PK": 2, "PEAK": 2, "PEAKING": 2, "HSQ": 3, "LP": 4, "HP": 5}
    type_id = type_map.get(filter_type.upper(), 2)

    header = bytes([0x01, 0x09, 0x18, 0x00, filter_idx & 0xFF, 0x00, 0x00])
    biquad = compute_walkplay_biquad(freq, gain, q)

    # No silent clamping: reached only after safety.validate_band has accepted the band.
    freq_u16 = int(round(freq))
    q_u16 = int(round(q * 256.0))
    gain_i16 = int(round(gain * 256.0))

    meta = struct.pack("<HHh", freq_u16, q_u16, gain_i16)
    suffix = bytes([type_id, 0x00, slot & 0xFF, 0x00])

    return header + biquad + meta + suffix


def decode_walkplay_filter_packet(packet: Sequence[int]) -> Optional[Dict[str, Any]]:
    """Decode a WalkPlay input report into a filter dictionary."""
    if not packet or len(packet) < 32:
        return None

    raw = bytes(packet)
    if raw[0] == 0x4B:
        raw = raw[1:]
    if len(raw) < 32:
        return None

    filter_idx = raw[4] if len(raw) > 4 else 0
    freq_raw, q_raw, gain_raw = struct.unpack("<HHh", raw[27:33])
    type_id = raw[33] if len(raw) > 33 else 2

    if freq_raw == 0xFFFF and q_raw == 0xFFFF and gain_raw == -1:
        return {
            "filter_index": filter_idx,
            "freq": 0.0,
            "gain": 0.0,
            "q": 0.0,
            "type": "PK",
            "disabled": True,
        }

    type_rev_map = {1: "LSQ", 2: "PK", 3: "HSQ", 4: "LP", 5: "HP"}
    return {
        "filter_index": filter_idx,
        "freq": float(freq_raw),
        "gain": round(gain_raw / 256.0, 2),
        "q": round(q_raw / 256.0, 2),
        "type": type_rev_map.get(type_id, "PK"),
        "disabled": freq_raw == 0 or q_raw == 0,
    }


decode_walkplay_filter_response = decode_walkplay_filter_packet


def encode_walkplay_global_gain(gain_db: float) -> bytes:
    """Encode global gain command: [0x01, 0x03, 0x02, 0x00, gain_db_i8]."""
    val = int(round(max(-128.0, min(127.0, gain_db)))) & 0xFF
    return bytes([0x01, 0x03, 0x02, 0x00, val])


# Known WalkPlay Vendor & Product IDs
WALKPLAY_VID = 0x3302
KNOWN_WALKPLAY_DEVICES = [
    (0x3302, 0xC20F),  # CrinEar Protocol Micro
    (0x3302, 0x43CC),  # CrinEar Protocol Max
    (0x3302, 0x4362),  # Truthear KEYX
    (0x3302, 0x4307),  # Tanchjim SPACE Pro (Rev 1)
    (0x3302, 0x431D),  # Tanchjim SPACE Pro (Rev 2)
    (0x3302, 0x4353),  # Tanchjim STARGATE II
]


class WalkPlayDSPDevice(BaseDSPDevice):
    """Hardware DSP driver for WalkPlay-chipset DACs (CrinEar Protocol Micro/Max, Truthear KEYX, Tanchjim SPACE Pro)."""

    REPORT_ID = 0x4B
    WALKPLAY_VID = 0x3302
    CRINEAR_VID = 0x3302
    PROTOCOL_MICRO_PID = 0xC20F
    PROTOCOL_MAX_PID = 0x43CC
    TRUTHEAR_KEYX_PID = 0x4362
    TANCHJIM_SPACE_PRO_PID = 0x4307
    TANCHJIM_SPACE_PRO_REV2_PID = 0x431D
    TANCHJIM_SPACE_PRO_PIDS = (0x4307, 0x431D)
    TANCHJIM_STARGATE2_PID = 0x4353
    CMD_READ = 0x81
    CMD_PEQ_RW = 0x09
    CMD_GLOBAL_GAIN = 0x03
    END_BYTE = 0x00

    def __init__(
        self,
        vendor_id: Optional[int] = None,
        product_id: Optional[int] = None,
        path: Optional[bytes] = None,
        use_mock: bool = False,
    ):
        super().__init__(vendor_id, product_id, path, use_mock)
        pid = product_id or self.PROTOCOL_MICRO_PID
        if pid in (self.PROTOCOL_MAX_PID, 0x4307, 0x431D):
            self._max_bands = 10
        else:
            self._max_bands = 8

    @property
    def max_bands(self) -> int:
        return self._max_bands

    @property
    def architecture_name(self) -> str:
        return "walkplay_dsp"

    def connect(self) -> None:
        safety.check_identity(self.vendor_id or self.CRINEAR_VID, self.product_id or self.PROTOCOL_MICRO_PID)
        if self.use_mock:
            self._dev = MockWalkPlayDevice(
                self.vendor_id or self.CRINEAR_VID,
                self.product_id or self.PROTOCOL_MICRO_PID,
                self.max_bands,
            )
            return

        if hid is None:
            raise DeviceCommunicationError("Python 'hid' library is not available.")

        vid = self.vendor_id or self.CRINEAR_VID
        pid = self.product_id or self.PROTOCOL_MICRO_PID

        for item in hid.enumerate(vid, pid):
            self._dev = hid.device()
            self._dev.open_path(item["path"])
            return

        raise DeviceCommunicationError(f"WalkPlay DSP device 0x{vid:04X}:0x{pid:04X} not found.")

    def close(self) -> None:
        if hasattr(self, "_dev") and self._dev:
            self._dev.close()
            self._dev = None

    def apply_preset(
        self,
        preset: Dict[str, Any],
        commit_flash: bool = False,
        compensate_2x: bool = False,
    ) -> None:
        bands = preset.get("bands", [])
        if len(bands) > self.max_bands:
            from dac_peq.biquad import decimate_bands
            bands = decimate_bands(bands, target_bands=self.max_bands)

        # Validate every band against the table before anything is packed: a rejected
        # write is aborted in full, never partially applied.
        for i, b in enumerate(bands):
            safety.validate_band(self.architecture_name, i, float(b.get("freq", 1000.0)), float(b.get("gain", 0.0)), float(b.get("q", 1.0)))

        default_slot = 1 if self.product_id in (self.TRUTHEAR_KEYX_PID, 0x4307, 0x431D, self.TANCHJIM_STARGATE2_PID) else 101
        slot = preset.get("slot_id", default_slot)
        preamp = float(preset.get("preamp", 0.0))

        # Write each filter
        for i, band in enumerate(bands):
            enabled = band.get("enabled", True)
            eff_gain = float(band.get("gain", 0.0)) if enabled else 0.0
            pkt = encode_walkplay_filter_packet(
                filter_idx=i,
                freq=float(band.get("freq", 1000)),
                gain=eff_gain,
                q=float(band.get("q", 1.0)),
                filter_type=str(band.get("type", "PK")),
                slot=slot,
            )
            self._dev.write([self.REPORT_ID] + list(pkt))
            time.sleep(0.01)

        # Set global preamp
        gain_pkt = encode_walkplay_global_gain(preamp)
        self._dev.write([self.REPORT_ID] + list(gain_pkt))
        time.sleep(0.02)

        # Commit sequence if requested
        if commit_flash:
            self._dev.write([self.REPORT_ID, 0x01, 0x05, 0x00])
            time.sleep(0.01)
            self._dev.write([self.REPORT_ID, 0x01, 0x17, 0x00])
            time.sleep(0.01)
            self._dev.write([self.REPORT_ID, 0x01, 0x0A, 0x04, 0x00, 0x00, 0xFF, 0xFF, 0x00])
            time.sleep(0.02)
            self._dev.write([self.REPORT_ID, 0x01, 0x01, 0x01, 0x00])

    def read_current_peq(self, compensate_2x: bool = False) -> Dict[str, Any]:
        if isinstance(self._dev, MockWalkPlayDevice):
            return {
                "bands": list(self._dev.filters),
                "preamp": float(self._dev.global_gain),
                "slot_id": self._dev.current_slot,
            }

        if not self._dev:
            raise DeviceCommunicationError("Device not connected.")

        def _safe_read(length: int = 64, timeout_ms: int = 200) -> List[int]:
            try:
                res = self._dev.read(length, timeout_ms=timeout_ms)
            except TypeError:
                try:
                    res = self._dev.read(length, timeout_ms)
                except TypeError:
                    res = self._dev.read(length)
            return list(res) if res else []

        bands: List[Dict[str, Any]] = []
        for idx in range(self.max_bands):
            req = [self.REPORT_ID, self.CMD_READ, self.CMD_PEQ_RW, idx, self.END_BYTE]
            req_padded = req + [0x00] * (64 - len(req))
            self._dev.write(req_padded)
            time.sleep(0.01)
            resp = _safe_read(64, timeout_ms=200)
            if resp and len(resp) >= 32:
                filter_dict = decode_walkplay_filter_response(resp)
                if filter_dict and not filter_dict.get("disabled", False):
                    bands.append({
                        "index": idx + 1,
                        "type": filter_dict.get("type", "PK"),
                        "freq": filter_dict.get("freq", 1000.0),
                        "gain": filter_dict.get("gain", 0.0),
                        "q": filter_dict.get("q", 1.0),
                    })

        # Read global preamp
        preamp = 0.0
        req_gain = [self.REPORT_ID, self.CMD_READ, self.CMD_GLOBAL_GAIN, 0x00, self.END_BYTE]
        req_gain_padded = req_gain + [0x00] * (64 - len(req_gain))
        self._dev.write(req_gain_padded)
        time.sleep(0.01)
        resp_gain = _safe_read(64, timeout_ms=200)
        if resp_gain:
            payload = resp_gain[1:] if resp_gain[0] == self.REPORT_ID else resp_gain
            if len(payload) >= 5 and payload[1] == self.CMD_GLOBAL_GAIN:
                gain_val = payload[4]
                if gain_val > 127:
                    gain_val -= 256
                preamp = float(gain_val)

        default_slot = 1 if self.product_id in (self.TRUTHEAR_KEYX_PID, 0x4307, 0x431D, self.TANCHJIM_STARGATE2_PID) else 101
        return {
            "bands": bands,
            "preamp": preamp,
            "slot_id": default_slot,
        }
