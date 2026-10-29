"""Unit tests for WalkPlay Scheme 11 & 16 hardware protocol adapter."""

from __future__ import annotations

import struct
import pytest

from dac_peq.walkplay_hid import (
    WalkPlayDSPDevice,
    compute_walkplay_biquad,
    decode_walkplay_filter_packet,
    encode_walkplay_filter_packet,
    encode_walkplay_global_gain,
)


def test_walkplay_biquad_exact_filter2_match():
    # Filter 2 from real Protocol Micro capture:
    # freq: 500, q: 1.5, gain: 8.0 dB
    biquad = compute_walkplay_biquad(500.0, 8.0, 1.5)
    expected = bytes([
        0x2C, 0x4B, 0xA9, 0x40, 0xEC, 0x5F, 0xF1, 0x80,
        0x94, 0xC1, 0x76, 0x3E, 0x14, 0xA0, 0x0E, 0x7F,
        0x41, 0xF3, 0xDF, 0xC0,
    ])
    assert biquad == expected


def test_walkplay_filter_packet_framing():
    # Filter 0 from real Protocol Micro capture:
    # freq: 100, q: 0.70, gain: 2.0 dB, type: LSQ, slot: 101
    pkt = encode_walkplay_filter_packet(0, 100.0, 2.0, 0.70, "LSQ", 101)
    assert len(pkt) == 37
    assert pkt[0] == 0x01
    assert pkt[1] == 0x09
    assert pkt[2] == 0x18  # payload len
    assert pkt[4] == 0     # filter index
    assert pkt[33] == 1    # LSQ type id
    assert pkt[35] == 101  # slot id


def test_walkplay_decode_filter_packet():
    pkt = encode_walkplay_filter_packet(3, 1700.0, -2.0, 1.4, "PK", 101)
    decoded = decode_walkplay_filter_packet(pkt)
    assert decoded is not None
    assert decoded["filter_index"] == 3
    assert decoded["freq"] == 1700.0
    assert abs(decoded["gain"] - (-2.0)) < 0.01
    assert abs(decoded["q"] - 1.4) < 0.01
    assert decoded["type"] == "PK"
    assert not decoded["disabled"]


def test_walkplay_global_gain():
    pkt = encode_walkplay_global_gain(-3.0)
    assert pkt == bytes([0x01, 0x03, 0x02, 0x00, 0xFD])


def test_walkplay_device_mock_preset_apply():
    # Test Protocol Micro (8 bands)
    dev_micro = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0xC20F, use_mock=True)
    with dev_micro:
        assert dev_micro.max_bands == 8
        preset = {
            "preamp": -2.5,
            "bands": [
                {"freq": 100, "gain": 3.0, "q": 1.0, "type": "LSQ"},
                {"freq": 1000, "gain": -1.5, "q": 2.0, "type": "PK"},
                {"freq": 8000, "gain": 2.0, "q": 0.7, "type": "HSQ"},
            ],
        }
        dev_micro.apply_preset(preset, commit_flash=True)
        assert dev_micro._dev.commit_count == 1
        assert dev_micro._dev.global_gain == -2  # Python banker's round(-2.5) == -2

    # Test Protocol Max (10 bands)
    dev_max = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0x43CC, use_mock=True)
    with dev_max:
        assert dev_max.max_bands == 10
        preset_10 = {
            "preamp": 0.0,
            "bands": [{"freq": 100 * (i + 1), "gain": float(i - 4), "q": 1.0, "type": "PK"} for i in range(10)],
        }
        dev_max.apply_preset(preset_10, commit_flash=False)
        assert dev_max._dev.commit_count == 0
        state = dev_max.read_current_peq()
        assert len(state["bands"]) == 10
        assert state["bands"][5]["gain"] == 1.0

    # Test Truthear KEYX (Scheme 15, 8 bands, slot 1)
    dev_keyx = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0x4362, use_mock=True)
    with dev_keyx:
        assert dev_keyx.max_bands == 8
        preset_keyx = {
            "preamp": -1.0,
            "bands": [{"freq": 200 * (i + 1), "gain": 1.0, "q": 1.0, "type": "PK"} for i in range(8)],
        }
        dev_keyx.apply_preset(preset_keyx, commit_flash=True)
        assert dev_keyx._dev.commit_count == 1

    # Test Tanchjim SPACE Pro (Scheme 15, 10 bands, slot 1)
    dev_space = WalkPlayDSPDevice(vendor_id=0x3302, product_id=0x431D, use_mock=True)
    with dev_space:
        assert dev_space.max_bands == 10
        preset_space = {
            "preamp": -2.0,
            "bands": [{"freq": 150 * (i + 1), "gain": -1.0, "q": 1.2, "type": "PK"} for i in range(10)],
        }
        dev_space.apply_preset(preset_space, commit_flash=True)
        assert dev_space._dev.commit_count == 1

