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
    """Verify is_allegro_mini_or_no_pregain and supports_dac_filter on 0x31B2 devices and JA11."""
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    assert dev_allegro.is_allegro_mini_or_no_pregain() is True
    assert dev_allegro.supports_dac_filter() is False
    assert dev_allegro._vid == 0x31B2

    dev_ja11 = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    assert dev_ja11.is_allegro_mini_or_no_pregain() is False
    assert dev_ja11.supports_dac_filter() is True
    assert dev_ja11._vid == 0x2972

    dev_custom_nopregain = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True, no_pregain=True)
    assert dev_custom_nopregain.is_allegro_mini_or_no_pregain() is True
    assert dev_custom_nopregain.supports_dac_filter() is False


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


def test_non_fiio_ktmicro_allows_preamp_blocks_dac_filter():
    """Verify non-FiiO KTMicro (e.g. JCALLY 0x1908:0x2070) can read/write preamp 0x66,
    is blocked from writing 0x11 in set_dac_filter, and skips reading 0x11 in read_current_peq,
    while FiiO JA11 (0x2972:0x0102) reads and writes 0x11 normally."""
    preset = {
        "name": "test_preset",
        "preamp": -2.5,
        "bands": [
            {"index": 1, "type": "PK", "freq": 100.0, "gain": 1.0, "q": 1.0},
            {"index": 2, "type": "PK", "freq": 250.0, "gain": 0.0, "q": 1.0},
            {"index": 3, "type": "PK", "freq": 1000.0, "gain": -1.0, "q": 1.0},
            {"index": 4, "type": "PK", "freq": 4000.0, "gain": 2.0, "q": 1.0},
            {"index": 5, "type": "PK", "freq": 8000.0, "gain": 0.0, "q": 1.0},
        ],
    }

    # 1. Non-FiiO KTMicro device: JCALLY JM20 (0x1908:0x2070)
    dev_jcally = KTMicroDSPDevice(vendor_id=0x1908, product_id=0x2070, use_mock=True)
    assert dev_jcally.supports_dac_filter() is False
    assert dev_jcally.is_allegro_mini_or_no_pregain() is False

    with dev_jcally:
        # Preamp 0x66 write succeeds on non-Allegro KTMicro hardware
        dev_jcally._dev.ram_registers.clear()
        dev_jcally.apply_preset(preset, commit_flash=False)
        assert dev_jcally.REG_PREAMP in dev_jcally._dev.ram_registers
        # Encoded: round(-2.5 * 2) = -5 -> 0xFB (251)
        assert dev_jcally._dev.ram_registers[dev_jcally.REG_PREAMP][6] == 0xFB

        # DAC filter write 0x11 is strictly blocked
        with pytest.raises(ValueError) as excinfo:
            dev_jcally.set_dac_filter("SLOW-LL")
        msg = str(excinfo.value)
        assert "0x11" in msg
        assert "JA11" in msg
        assert "0x2972" in msg
        assert "volume" in msg.lower()
        assert dev_jcally.REG_DAC_FILTER not in dev_jcally._dev.ram_registers

        # Preamp 0x66 read succeeds, while DAC filter 0x11 read is skipped
        dev_jcally._dev.ram_registers[0x66] = [0x66, 0, 0, 0, 0x57, 0, 0xF6, 0, 0, 0]  # -5.0 dB
        dev_jcally._dev.ram_registers[0x11] = [0x11, 0, 0, 0, 0x57, 0, 0x03, 0, 0, 0]  # SLOW-LL

        sent_regs = []
        orig_send = dev_jcally._send_packet

        def spy_send(reg, cmd, d0=0, d1=0, d2=0, d3=0):
            sent_regs.append(reg)
            return orig_send(reg, cmd, d0, d1, d2, d3)

        dev_jcally._send_packet = spy_send

        state_jcally = dev_jcally.read_current_peq()
        assert state_jcally["preamp"] == -5.0
        assert state_jcally["dac_filter"] is None
        # Register 0x11 must not have been polled
        assert dev_jcally.REG_DAC_FILTER not in sent_regs
        # Register 0x66 must have been polled
        assert dev_jcally.REG_PREAMP in sent_regs

    # 2. FiiO JA11 (0x2972:0x0102) supports both preamp 0x66 and DAC filter 0x11
    dev_ja11 = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    assert dev_ja11.supports_dac_filter() is True
    assert dev_ja11.is_allegro_mini_or_no_pregain() is False

    with dev_ja11:
        dev_ja11._dev.ram_registers.clear()
        dev_ja11.apply_preset(preset, commit_flash=False)
        assert dev_ja11.REG_PREAMP in dev_ja11._dev.ram_registers

        dev_ja11.set_dac_filter("SLOW-PC", commit_flash=False)
        assert dev_ja11.REG_DAC_FILTER in dev_ja11._dev.ram_registers
        assert dev_ja11._dev.ram_registers[dev_ja11.REG_DAC_FILTER][6] == dev_ja11.DAC_FILTERS["SLOW-PC"]

        state_ja11 = dev_ja11.read_current_peq()
        assert state_ja11["dac_filter"] == "SLOW-PC"
        assert state_ja11["preamp"] == -2.5


def test_ktmicro_disabled_bands_muted():
    """Verify that disabled bands (enabled: False) are muted to 0.0 dB gain in KTMicro apply_preset."""
    dev = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    with dev:
        dev._dev.ram_registers.clear()
        preset = {
            "name": "disabled_test",
            "preamp": 0.0,
            "bands": [
                {"index": 1, "type": "PK", "freq": 100.0, "gain": 4.0, "q": 1.0, "enabled": False},
                {"index": 2, "type": "PK", "freq": 250.0, "gain": 2.0, "q": 1.0, "enabled": True},
                {"index": 3, "type": "PK", "freq": 1000.0, "gain": -3.0, "q": 1.0, "enabled": False},
                {"index": 4, "type": "PK", "freq": 4000.0, "gain": 1.5, "q": 1.0, "enabled": True},
                {"index": 5, "type": "PK", "freq": 8000.0, "gain": -2.0, "q": 1.0, "enabled": True},
            ],
        }
        dev.apply_preset(preset, commit_flash=False)
        # Band 1 (0x26): disabled, gain must be 0
        b1_raw = dev._dev.ram_registers[0x26]
        gain_b1 = b1_raw[6] | (b1_raw[7] << 8)
        assert gain_b1 == 0

        # Band 2 (0x28): enabled, gain must be 20 (+2.0 dB)
        b2_raw = dev._dev.ram_registers[0x28]
        gain_b2 = b2_raw[6] | (b2_raw[7] << 8)
        assert gain_b2 == 20

        # Band 3 (0x2A): disabled, gain must be 0
        b3_raw = dev._dev.ram_registers[0x2A]
        gain_b3 = b3_raw[6] | (b3_raw[7] << 8)
        assert gain_b3 == 0

        # Preamp 0.0 dB is written to register 0x66
        assert dev.REG_PREAMP in dev._dev.ram_registers
        assert dev._dev.ram_registers[dev.REG_PREAMP][6] == 0x00


def test_ktmicro_zero_db_preamp_packet_included_for_ja11():
    """Verify that when preamp is 0.0 dB, register 0x66 is included in the output packets for JA11/KTMicro,
    and omitted for Kiwi Ears Allegro Mini."""
    preset = {
        "name": "zero_preamp_test",
        "preamp": 0.0,
        "bands": [
            {"index": i, "type": "PK", "freq": 1000.0, "gain": 0.0, "q": 1.0}
            for i in range(1, 6)
        ],
    }

    # 1. JA11 (0x2972)
    dev_ja11 = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    sent_packets_ja11 = []
    with dev_ja11:
        dev_ja11._dev.ram_registers.clear()
        orig_send = dev_ja11._send_packet

        def spy_send(reg, cmd, d0=0, d1=0, d2=0, d3=0):
            sent_packets_ja11.append((reg, cmd, d0, d1, d2, d3))
            return orig_send(reg, cmd, d0, d1, d2, d3)

        dev_ja11._send_packet = spy_send

        dev_ja11.apply_preset(preset, commit_flash=False)

        preamp_pkts = [p for p in sent_packets_ja11 if p[0] == dev_ja11.REG_PREAMP]
        assert len(preamp_pkts) == 1, "Register 0x66 packet was not sent for JA11 with 0.0 dB preamp"
        assert preamp_pkts[0][1] == dev_ja11.CMD_WRITE
        assert preamp_pkts[0][2] == 0x00, "Register 0x66 data byte must be 0x00 for 0.0 dB preamp"
        assert dev_ja11.REG_PREAMP in dev_ja11._dev.ram_registers
        assert dev_ja11._dev.ram_registers[dev_ja11.REG_PREAMP][6] == 0x00

    # 2. Allegro Mini (0x31B2)
    dev_allegro = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x0111, use_mock=True)
    sent_packets_allegro = []
    with dev_allegro:
        dev_allegro._dev.ram_registers.clear()
        orig_send_allegro = dev_allegro._send_packet

        def spy_send_allegro(reg, cmd, d0=0, d1=0, d2=0, d3=0):
            sent_packets_allegro.append((reg, cmd, d0, d1, d2, d3))
            return orig_send_allegro(reg, cmd, d0, d1, d2, d3)

        dev_allegro._send_packet = spy_send_allegro

        dev_allegro.apply_preset(preset, commit_flash=False)

        preamp_pkts_allegro = [p for p in sent_packets_allegro if p[0] == dev_allegro.REG_PREAMP]
        assert len(preamp_pkts_allegro) == 0, "Register 0x66 must NOT be sent for Allegro Mini"
        assert dev_allegro.REG_PREAMP not in dev_allegro._dev.ram_registers


def test_ktmicro_preamp_null_and_extreme_clamping():
    """Verify that null/None preamp safely defaults to 0.0 dB and extreme values clamp to [-24.0, +12.0] dB."""
    dev = KTMicroDSPDevice(vendor_id=0x2972, product_id=0x0102, use_mock=True)
    dummy_bands = [{"index": i, "type": "PK", "freq": 1000.0, "gain": 0.0, "q": 1.0} for i in range(1, 6)]

    # 1. Null / None preamp
    with dev:
        dev._dev.ram_registers.clear()
        preset_null = {
            "name": "null_preamp",
            "preamp": None,
            "bands": dummy_bands,
        }
        dev.apply_preset(preset_null, commit_flash=False)
        assert dev._dev.ram_registers[dev.REG_PREAMP][6] == 0x00

    # 2. Extreme negative attenuation (-70.0 dB) -> clamps to -24.0 dB (-48 byte = 208)
    with dev:
        dev._dev.ram_registers.clear()
        preset_neg = {
            "name": "extreme_neg",
            "preamp": -70.0,
            "bands": dummy_bands,
        }
        dev.apply_preset(preset_neg, commit_flash=False)
        assert dev._dev.ram_registers[dev.REG_PREAMP][6] == ((-48) & 0xFF)

    # 3. Extreme positive boost (+30.0 dB) -> clamps to +12.0 dB (+24 byte)
    with dev:
        dev._dev.ram_registers.clear()
        preset_pos = {
            "name": "extreme_pos",
            "preamp": 30.0,
            "bands": dummy_bands,
        }
        dev.apply_preset(preset_pos, commit_flash=False)
        assert dev._dev.ram_registers[dev.REG_PREAMP][6] == 24


def test_ktmicro_arbitrary_31b2_pid_guarded():
    """Verify any 0x31B2 device (e.g. 0x31B2:0x9999) omits register 0x66 to prevent volume lockout."""
    dev_oem = KTMicroDSPDevice(vendor_id=0x31B2, product_id=0x9999, use_mock=True)
    dummy_bands = [{"index": i, "type": "PK", "freq": 1000.0, "gain": 0.0, "q": 1.0} for i in range(1, 6)]
    with dev_oem:
        dev_oem._dev.ram_registers.clear()
        preset = {
            "name": "oem_test",
            "preamp": -3.0,
            "bands": dummy_bands,
        }
        dev_oem.apply_preset(preset, commit_flash=False)
        assert dev_oem.REG_PREAMP not in dev_oem._dev.ram_registers


