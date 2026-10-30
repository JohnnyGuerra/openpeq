"""Tests for KTMicro HID protocol, Allegro Mini GEMINI.md Rule 1 guardrails, and Conexant safety."""

import pytest
from dac_peq.ktmicro_hid import (
    CONEXANT_VID,
    DeviceSecurityException,
    KTMicroDSPDevice,
    MockKTDevice,
    is_conexant_cx31993,
    is_ktmicro_candidate,
)
from dac_peq.transport import get_dsp_device


def test_allegro_mini_guardrail_properties():
    """Verify is_allegro_mini_or_no_pregain on 0x31B2 devices and JA11."""
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    assert dev_allegro.is_allegro_mini_or_no_pregain() is True
    assert dev_allegro._vid == 0x31B2

    dev_ja11 = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    assert dev_ja11.is_allegro_mini_or_no_pregain() is False
    assert dev_ja11._vid == 0x2972

    dev_custom_nopregain = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True, no_pregain=True)
    assert dev_custom_nopregain.is_allegro_mini_or_no_pregain() is True


def test_allegro_mini_skips_register_0x66_in_apply_preset():
    """Verify that apply_preset on Allegro Mini (0x31B2) strictly avoids writing register 0x66."""
    preset = {
        "name": "test_preset",
        "preamp": -3.5,
        "bands": [
            {"index": 1, "type": "LSQ", "freq": 60.0, "gain": 2.0, "q": 0.71},
            {"index": 2, "type": "PK", "freq": 200.0, "gain": -1.0, "q": 1.0},
            {"index": 3, "type": "PK", "freq": 1000.0, "gain": 1.5, "q": 1.2},
            {"index": 4, "type": "PK", "freq": 4000.0, "gain": -2.0, "q": 2.0},
            {"index": 5, "type": "HSQ", "freq": 9000.0, "gain": 1.0, "q": 0.71},
        ],
    }

    # Allegro Mini (0x31B2)
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    with dev_allegro:
        # Clear mock RAM
        dev_allegro._dev.ram_registers.clear()
        dev_allegro.apply_preset(preset, commit_flash=False)
        # Register 0x66 (preamp) MUST NOT be written
        assert dev_allegro.REG_PREAMP not in dev_allegro._dev.ram_registers
        # Slot and 5 bands (10 registers) must be written
        assert dev_allegro.REG_SLOT in dev_allegro._dev.ram_registers
        for i in range(5):
            reg_gf = dev_allegro.BASE_REG_OFFSET + i * 2
            assert reg_gf in dev_allegro._dev.ram_registers
            assert reg_gf + 1 in dev_allegro._dev.ram_registers

    # FiiO JA11 (0x2972) DOES write register 0x66
    dev_ja11 = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    with dev_ja11:
        dev_ja11._dev.ram_registers.clear()
        dev_ja11.apply_preset(preset, commit_flash=False)
        assert dev_ja11.REG_PREAMP in dev_ja11._dev.ram_registers


def test_allegro_mini_skips_registers_in_read_current_peq():
    """Verify that read_current_peq on Allegro Mini skips 0x66 and 0x11, defaulting preamp=0.0 and filter=None."""
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    with dev_allegro:
        # Populate RAM with non-zero preamp and filter
        dev_allegro._dev.ram_registers[0x66] = [0x66, 0, 0, 0, 0x57, 0, 0xF8, 0, 0, 0]  # -4 dB
        dev_allegro._dev.ram_registers[0x11] = [0x11, 0, 0, 0, 0x57, 0, 0x03, 0, 0, 0]

        state = dev_allegro.read_current_peq()
        # Per GEMINI.md Rule 1: registers 0x66 and 0x11 are skipped
        assert state["preamp"] == 0.0
        assert state["dac_filter"] is None
        assert len(state["bands"]) == 5


def test_allegro_mini_raises_value_error_on_set_dac_filter():
    """Verify set_dac_filter raises ValueError on 0x31B2 to prevent volume lockout."""
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    with dev_allegro:
        with pytest.raises(ValueError) as excinfo:
            dev_allegro.set_dac_filter("FAST-LL")
        msg = str(excinfo.value)
        assert "0x11" in msg
        assert "JA11" in msg
        assert "volume" in msg.lower()


def test_conexant_cx31993_blocked_in_ktmicro_and_transport():
    """Verify Conexant CX31993 devices (0x0572:0xC319 and 0x3302:0x3365) are blocked."""
    # 0x0572:0xC319 in get_dsp_device
    with pytest.raises(ValueError) as exc_t1:
        get_dsp_device(vendor_id=0x0572, product_id=0xC319)
    assert "Conexant CX31993" in str(exc_t1.value)
    assert "GEMINI.md Rule 2" in str(exc_t1.value)

    # 0x3302:0x3365 in get_dsp_device
    with pytest.raises(ValueError) as exc_t2:
        get_dsp_device(vendor_id=0x3302, product_id=0x3365)
    assert "Conexant CX31993" in str(exc_t2.value)

    # In KTMicroDSPDevice.connect()
    for vid, pid in [(0x0572, 0xC319), (0x3302, 0x3365)]:
        dev = KTMicroDSPDevice(vendor_id=vid, product_id=pid)
        with pytest.raises((RuntimeError, DeviceSecurityException)) as exc_k:
            dev.connect()
        assert "SAFETY GUARD" in str(exc_k.value)
        assert "CX31993" in str(exc_k.value)


def test_scan_candidate_exclusions():
    """Verify is_ktmicro_candidate excludes FreeDSP, WalkPlay, Conexant, and non-flashable FiiO."""
    # Supported KTMicro devices
    assert is_ktmicro_candidate({"vendor_id": 0x31B2, "product_id": 0x0111})  # Allegro Mini
    assert is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0102})  # FiiO JA11
    assert is_ktmicro_candidate({"vendor_id": 0x1908, "product_id": 0x0111})  # JCALLY JM12

    # Excluded: Moondrop FreeDSP
    assert not is_ktmicro_candidate({"vendor_id": 0x31B2, "product_id": 0x0112})

    # Excluded: WalkPlay PIDs under 0x3302
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x4307})  # SPACE Pro Rev 1
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x431D})  # SPACE Pro Rev 2
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0xC20F})  # Protocol Micro
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x43CC})  # Protocol Max
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x4362})  # KEYX
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x4353})  # STARGATE II

    # Excluded: Conexant CX31993
    assert not is_ktmicro_candidate({"vendor_id": 0x0572, "product_id": 0x1B08})
    assert not is_ktmicro_candidate({"vendor_id": 0x3302, "product_id": 0x3365})
    assert not is_ktmicro_candidate({"vendor_id": 0x1234, "product_string": "CX31993 HiFi DAC"})

    # Excluded: Non-flashable FiiO
    assert not is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0047})  # KA13
    assert not is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0066})  # KA11
    assert not is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0104})  # KA15
    assert not is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0105})  # KA17
    assert not is_ktmicro_candidate({"vendor_id": 0x2972, "product_id": 0x0107})  # BTR13
