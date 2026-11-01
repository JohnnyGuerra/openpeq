"""Safety guard tests: one rule, one table (issue #8 acceptance criteria)."""

from __future__ import annotations

import pytest

from dac_peq import safety
from dac_peq.moondrop import MoondropFreeDSPDevice
from dac_peq.transport import get_dsp_device
from dac_peq.walkplay_hid import WalkPlayDSPDevice


def test_path_only_open_is_refused(monkeypatch):
    """A path names a node, not a device: an unconfirmed path is refused before any write."""
    monkeypatch.setattr(safety, "resolve_path_identity", lambda table, path: None)
    with pytest.raises(safety.DeviceSecurityException) as exc:
        get_dsp_device(path="/dev/hidraw0")
    assert "SAFETY GUARD" in str(exc.value)
    assert "/dev/hidraw0" in str(exc.value)


def test_path_identity_mismatch_is_refused(monkeypatch):
    """The device behind the path must be the device the caller asked for."""
    resolved = {
        "name": "CrinEar Protocol Micro",
        "architecture": "walkplay_dsp",
        "chipset": "WalkPlay",
        "vid": 0x3302,
        "pid": 0xC20F,
    }
    monkeypatch.setattr(safety, "resolve_path_identity", lambda table, path: resolved)
    with pytest.raises(safety.DeviceSecurityException, match="mismatch"):
        get_dsp_device(0x3302, 0x43CC, path="/dev/hidraw0")


def test_resolve_path_identity_uses_enumerate():
    table = safety.load_table()
    items = [{"path": "/dev/hidraw3", "vendor_id": 0x3302, "product_id": 0xC20F, "product_string": "CrinEar Protocol Micro"}]
    entry = safety.resolve_path_identity(table, b"/dev/hidraw3", enumerate_fn=lambda: items)
    assert entry is not None and entry["architecture"] == "walkplay_dsp"
    assert safety.resolve_path_identity(table, b"/dev/hidraw9", enumerate_fn=lambda: items) is None


def test_unknown_device_is_refused():
    with pytest.raises(safety.DeviceSecurityException, match="not in the device table"):
        get_dsp_device(0x1234, 0x5678)


def test_blocked_architecture_is_refused():
    with pytest.raises(safety.DeviceSecurityException, match="mask ROM"):
        get_dsp_device(0x0572, 0x1B08)


def test_out_of_range_is_rejected_before_any_packet():
    dev = WalkPlayDSPDevice(0x3302, 0xC20F, use_mock=True)
    dev.connect()
    with pytest.raises(safety.CoefficientRangeError, match="band 0"):
        dev.apply_preset({"bands": [{"freq": 30000.0, "gain": 2.0, "q": 0.7}], "preamp": 0.0})
    assert dev._dev.written_reports == []


def test_rejected_write_is_not_partially_applied():
    dev = MoondropFreeDSPDevice(use_mock=True)
    dev.connect()
    bands = [{"index": i + 1, "type": "PK", "freq": 100.0 * (i + 1), "gain": 1.0, "q": 1.0} for i in range(6)]
    bands[3] = {"index": 4, "type": "PK", "freq": 800.0, "gain": 25.0, "q": 1.0}
    with pytest.raises(safety.CoefficientRangeError, match="band 3"):
        dev.apply_preset({"bands": bands, "preamp": 0.0}, commit_flash=False)
    assert dev._dev.written_reports == []
    assert dev._dev.commit_count == 0  # nothing mutated before the refusal either


def test_ranges_come_from_the_table():
    table = safety.load_table()
    for arch in table["ranges"]:
        assert safety.ranges_for(arch) is table["ranges"][arch]


def test_accepted_write_sends_the_exact_bytes():
    """The guard validates the values that actually reach the wire."""
    dev = WalkPlayDSPDevice(0x3302, 0xC20F, use_mock=True)
    dev.connect()
    dev.apply_preset({"bands": [{"freq": 1000.0, "gain": 0.0, "q": 1.0}], "preamp": 0.0}, commit_flash=False)
    pkt = bytes(dev._dev.written_reports[0])
    assert pkt[0] == 0x4B
    assert pkt[1:8] == bytes([0x01, 0x09, 0x18, 0x00, 0, 0, 0])  # header, filter index 0
    assert pkt[-10:] == bytes([0xE8, 0x03, 0x00, 0x01, 0x00, 0x00, 2, 0x00, 101, 0])  # freq 1000, Q 1.0, gain 0.0, PK, slot 101
