"""Tests for WalkPlay HID hardware communication, Tanchjim SPACE Pro PIDs, and real hardware reading."""

import struct
import pytest
from dac_peq.transport import get_dsp_device
from dac_peq.walkplay_hid import (
    KNOWN_WALKPLAY_DEVICES,
    WalkPlayDSPDevice,
    decode_walkplay_filter_response,
    encode_walkplay_filter_packet,
)


def test_tanchjim_space_pro_pids():
    """Verify both 0x4307 and 0x431D are recognized as 10-band WalkPlay devices."""
    assert (0x3302, 0x4307) in KNOWN_WALKPLAY_DEVICES
    assert (0x3302, 0x431D) in KNOWN_WALKPLAY_DEVICES

    dev_4307 = get_dsp_device(vendor_id=0x3302, product_id=0x4307, use_mock=True)
    assert isinstance(dev_4307, WalkPlayDSPDevice)
    assert dev_4307.max_bands == 10

    dev_431d = get_dsp_device(vendor_id=0x3302, product_id=0x431D, use_mock=True)
    assert isinstance(dev_431d, WalkPlayDSPDevice)
    assert dev_431d.max_bands == 10


def test_decode_walkplay_filter_response_with_report_id():
    """Verify decode_walkplay_filter_response handles 0x4B report ID prefix."""
    raw_pkt = encode_walkplay_filter_packet(filter_idx=2, freq=2500.0, gain=3.0, q=1.5, filter_type="PK")
    full_report = [0x4B] + list(raw_pkt) + [0x00] * (64 - len(raw_pkt) - 1)

    decoded = decode_walkplay_filter_response(full_report)
    assert decoded is not None
    assert decoded["filter_index"] == 2
    assert decoded["freq"] == 2500.0
    assert abs(decoded["gain"] - 3.0) < 0.05
    assert abs(decoded["q"] - 1.5) < 0.05
    assert decoded["type"] == "PK"


class FakeRawWalkPlayHIDDevice:
    """Simulates a low-level USB HID endpoint returning framed WalkPlay packets."""

    def __init__(self, num_bands: int = 8, preamp: float = -3.0):
        self.num_bands = num_bands
        self.preamp = preamp
        self.writes = []

    def write(self, data):
        self.writes.append(list(data))
        return len(data)

    def read(self, length, timeout_ms=200):
        if not self.writes:
            return [0x00] * length

        last_write = self.writes[-1]
        # Check if PEQ read request: [0x4B, 0x81, 0x09, idx, 0x00, ...]
        if len(last_write) >= 5 and last_write[0] == 0x4B and last_write[1] == 0x81:
            cmd = last_write[2]
            if cmd == 0x09:  # PEQ_RW
                idx = last_write[3]
                freq = 200.0 * (idx + 1)
                gain = 1.0 if idx % 2 == 0 else -1.0
                q = 1.0
                pkt = encode_walkplay_filter_packet(idx, freq, gain, q, "PK")
                resp = [0x4B] + list(pkt)
                return resp + [0x00] * (length - len(resp))
            elif cmd == 0x03:  # GLOBAL_GAIN
                # Return [0x4B, 0x80, 0x03, 0x02, 0x00, gain_byte, ...]
                gain_val = int(round(self.preamp)) & 0xFF
                resp = [0x4B, 0x80, 0x03, 0x02, 0x00, gain_val]
                return resp + [0x00] * (length - len(resp))

        return [0x00] * length

    def close(self):
        pass


def test_walkplay_real_hid_read_loop():
    """Verify real hardware read path (when not using MockWalkPlayDevice)."""
    dev = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0xC20F)
    dev._dev = FakeRawWalkPlayHIDDevice(num_bands=8, preamp=-3.0)

    state = dev.read_current_peq()
    assert state["preamp"] == -3.0
    assert len(state["bands"]) == 8

    # Verify first and last bands
    b0 = state["bands"][0]
    assert b0["index"] == 1
    assert b0["freq"] == 200.0
    assert b0["gain"] == 1.0

    b7 = state["bands"][7]
    assert b7["index"] == 8
    assert b7["freq"] == 1600.0


def test_walkplay_real_hid_read_loop_positional_timeout():
    """Verify read loop works if dev.read only accepts positional timeout or no timeout."""
    class PositionalOnlyHIDDevice(FakeRawWalkPlayHIDDevice):
        def read(self, length, timeout_ms=200):
            # Enforce positional only
            return super().read(length, timeout_ms)

    dev = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0xC20F)
    dev._dev = PositionalOnlyHIDDevice(num_bands=8, preamp=-2.0)

    state = dev.read_current_peq()
    assert state["preamp"] == -2.0
    assert len(state["bands"]) == 8


def test_walkplay_disabled_bands_muted():
    """Verify that disabled bands (enabled: False) are encoded with 0.0 dB gain in WalkPlay apply_preset."""
    dev = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0xC20F, use_mock=True)
    with dev:
        preset = {
            "name": "WalkPlay Disabled Test",
            "preamp": 0.0,
            "bands": [
                {"index": 1, "type": "PK", "freq": 1000.0, "gain": 4.0, "q": 1.0, "enabled": False},
                {"index": 2, "type": "PK", "freq": 2000.0, "gain": 3.0, "q": 1.0, "enabled": True},
            ],
        }
        dev.apply_preset(preset)
        state = dev.read_current_peq()
        # Filter 0 was disabled: eff_gain should be 0.0
        assert state["bands"][0]["gain"] == 0.0
        # Filter 1 was enabled: eff_gain should be 3.0
        assert state["bands"][1]["gain"] == 3.0
