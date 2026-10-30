"""End-to-end tests for CLI preset loading, safety guardrails, reset, and udev rules."""

import pytest
from typer.testing import CliRunner

from dac_peq.cli import app, load_preset, load_preset_data

runner = CliRunner()

PRESET_NAMES = [
    "blessing3",
    "bmasterx6",
    "cadenza",
    "chu2",
    "ew300_gold",
    "ew300_silver",
    "flat",
    "hd600",
    "hexa",
    "supermix4",
    "test_export",
    "waner",
    "zero2",
    "zero_red",
]


@pytest.mark.parametrize("preset_name", PRESET_NAMES)
def test_all_14_presets_loadable(preset_name: str):
    """Verify that all 14 presets load successfully through load_preset."""
    data = load_preset(preset_name)
    assert isinstance(data, dict)
    assert "name" in data
    assert "bands" in data
    assert len(data["bands"]) == 5
    assert "preamp" in data

    # Also test CLI show command
    res = runner.invoke(app, ["show", preset_name])
    assert res.exit_code == 0
    assert "Hardware PEQ Preset" in res.output or preset_name in res.output.lower()


def test_cli_filter_allegro_mini_safety_block():
    """Verify that attempting to set DAC reconstruction filter on Allegro Mini exits with code 1 and prints [SAFETY BLOCK]."""
    res = runner.invoke(app, ["filter", "FAST-LL", "--vid", "0x31B2", "--pid", "0x0111", "--mock"])
    assert res.exit_code != 0
    assert "[SAFETY BLOCK]" in res.output
    assert "0x11" in res.output


def test_cli_reset_ktmicro_vs_walkplay_and_conexant():
    """Verify CLI reset handles KTMicro, WalkPlay, and Conexant appropriately."""
    # KTMicro (supported)
    res_kt = runner.invoke(app, ["reset", "--vid", "0x31B2", "--pid", "0x0111", "--mock", "-y"])
    assert res_kt.exit_code == 0
    assert "Factory reset successful" in res_kt.output

    # WalkPlay (unsupported 0x43 CLEAR)
    res_wp = runner.invoke(app, ["reset", "--vid", "0x3302", "--pid", "0xC20F", "--mock", "-y"])
    assert res_wp.exit_code == 1
    assert "[UNSUPPORTED]" in res_wp.output

    # Conexant CX31993 (blocked by safety guardrail)
    res_cx = runner.invoke(app, ["reset", "--vid", "0x0572", "--pid", "0x1B08", "--mock", "-y"])
    assert res_cx.exit_code == 2
    assert "[BLOCKED]" in res_cx.output


def test_cli_udev_unified_rules():
    """Verify udev output contains all required hardware VIDs and both usb/hidraw rules."""
    res = runner.invoke(app, ["udev", "--print"])
    assert res.exit_code == 0
    output = res.output

    # Verify VIDs covered
    assert 'ATTRS{idVendor}=="31b2"' in output
    assert 'ATTRS{idVendor}=="3302"' in output
    assert 'ATTRS{idVendor}=="2972"' in output
    assert 'ATTRS{idVendor}=="1908"' in output
    assert 'ATTRS{idVendor}=="0a12"' in output

    # Verify KERNEL=="hidraw*" and SUBSYSTEM=="usb"
    assert 'KERNEL=="hidraw*"' in output
    assert 'SUBSYSTEM=="usb"' in output
