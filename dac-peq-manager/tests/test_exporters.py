"""Tests for PipeWire, EqualizerAPO, and Wavelet configuration exporters."""

import json
from pathlib import Path
from dac_peq.exporters import (
    DEFAULT_CX31993_SINK,
    export_apo_suite,
    export_pipewire_conf,
    export_qudelix,
    format_equalizer_apo,
    format_pipewire_filter_chain,
    format_qudelix_json,
    format_qudelix_text,
    format_wavelet_graphiceq,
    format_wavelet_json,
    parse_qudelix_profile,
)


SAMPLE_PRESET = {
    "name": "bmasterx6",
    "description": "BASN BmasterX 6 Custom Tuning",
    "preamp": -2.5,
    "bands": [
        {"index": 1, "type": "LSQ", "freq": 50.0, "gain": 2.2, "q": 0.71, "comment": "Sub-bass"},
        {"index": 2, "type": "PK", "freq": 195.0, "gain": -2.4, "q": 1.10, "comment": "Mid-bass"},
        {"index": 3, "type": "PK", "freq": 2200.0, "gain": 1.6, "q": 1.30, "comment": "Vocals"},
        {"index": 4, "type": "PK", "freq": 4500.0, "gain": -1.8, "q": 2.50, "comment": "Upper-mid"},
        {"index": 5, "type": "PK", "freq": 9800.0, "gain": -3.2, "q": 3.00, "comment": "Treble"},
    ],
}


def test_pipewire_conf_structure():
    """Verify PipeWire filter-chain syntax, stereo channels, and hardware target."""
    conf = format_pipewire_filter_chain(SAMPLE_PRESET)

    # Core module
    assert "libpipewire-module-filter-chain" in conf
    # Preamp linear nodes
    assert "preamp_fl" in conf
    assert "preamp_fr" in conf
    assert "label  = linear" in conf
    # Filter nodes for each band (FL and FR)
    assert "eq_band1_fl" in conf
    assert "eq_band1_fr" in conf
    assert "label  = bq_lowshelf" in conf
    assert "label  = bq_peaking" in conf
    # Routing and target
    assert f'node.target      = "{DEFAULT_CX31993_SINK}"' in conf
    assert 'inputs  = [ "preamp_fl:In", "preamp_fr:In" ]' in conf
    assert 'outputs = [ "eq_band5_fl:Out", "eq_band5_fr:Out" ]' in conf


def test_pipewire_export_file(tmp_path: Path):
    """Verify writing PipeWire config to disk."""
    out_file = tmp_path / "pipewire_test.conf"
    res = export_pipewire_conf(SAMPLE_PRESET, output_path=out_file)
    assert res == out_file
    assert out_file.is_file()
    assert "libpipewire-module-filter-chain" in out_file.read_text()


def test_equalizer_apo_format():
    """Verify EqualizerAPO format output."""
    txt = format_equalizer_apo(SAMPLE_PRESET)
    assert "Preamp: -2.5 dB" in txt
    assert "Filter 1: ON LSQ Fc 50.0 Hz Gain +2.2 dB Q 0.71" in txt
    assert "Filter 2: ON PK Fc 195.0 Hz Gain -2.4 dB Q 1.10" in txt
    assert "Filter 5: ON PK Fc 9800.0 Hz Gain -3.2 dB Q 3.00" in txt


def test_wavelet_graphiceq_format():
    """Verify Wavelet GraphicEQ format output."""
    geq = format_wavelet_graphiceq(SAMPLE_PRESET)
    assert geq.startswith("GraphicEQ: ")
    assert "; " in geq
    assert "20 " in geq
    assert "20000 " in geq


def test_wavelet_json_format():
    """Verify Wavelet JSON profile generation."""
    data = format_wavelet_json(SAMPLE_PRESET)
    assert data["name"] == "bmasterx6"
    assert data["preamp"] == -2.5
    assert "nine_band_gains" in data
    assert len(data["nine_band_gains"]) == 9
    assert "graphiceq" in data
    assert data["graphiceq"].startswith("GraphicEQ:")


def test_export_apo_suite(tmp_path: Path):
    """Verify batch export of APO, GraphicEQ, and Wavelet JSON files."""
    files = export_apo_suite(SAMPLE_PRESET, output_dir=tmp_path)
    assert files["equalizer_apo"].is_file()
    assert files["wavelet_txt"].is_file()
    assert files["wavelet_json"].is_file()

    # Verify JSON content is valid
    parsed = json.loads(files["wavelet_json"].read_text())
    assert parsed["name"] == "bmasterx6"


def test_pipewire_export_10_bands():
    """Verify PipeWire filter-chain configuration generation with 10 bands."""
    ten_band_preset = {
        "name": "full_target_10",
        "preamp": -3.0,
        "bands": [
            {"index": i + 1, "type": "PK", "freq": 100.0 * (i + 1), "gain": 1.0, "q": 1.0}
            for i in range(10)
        ],
    }
    conf = format_pipewire_filter_chain(ten_band_preset)
    assert "eq_band1_fl" in conf
    assert "eq_band10_fl" in conf
    assert 'outputs = [ "eq_band10_fl:Out", "eq_band10_fr:Out" ]' in conf


def test_qudelix_text_format():
    """Verify Qudelix-5K 10-band text configuration."""
    txt = format_qudelix_text(SAMPLE_PRESET)
    assert "# Qudelix-5K PEQ Profile: bmasterx6" in txt
    assert "Preamp: -2.5 dB" in txt
    # Check 5 active bands
    assert "Filter 1: ON LSQ Fc 50.0 Hz Gain +2.2 dB Q 0.71" in txt
    assert "Filter 5: ON PK Fc 9800.0 Hz Gain -3.2 dB Q 3.00" in txt
    # Check bands 6-10 padded as OFF
    assert "Filter 6: OFF PK Fc 1000.0 Hz Gain +0.0 dB Q 1.00" in txt
    assert "Filter 10: OFF PK Fc 1000.0 Hz Gain +0.0 dB Q 1.00" in txt


def test_qudelix_json_format():
    """Verify Qudelix-5K Chrome App JSON preset profile."""
    data = format_qudelix_json(SAMPLE_PRESET)
    assert data["profile_name"] == "bmasterx6"
    assert data["preamp_db"] == -2.5
    assert len(data["eq_list"]) == 10
    # First band is LSQ (LOW_SHELF)
    assert data["eq_list"][0]["band"] == 0
    assert data["eq_list"][0]["enable"] == 1
    assert data["eq_list"][0]["type"] == "LOW_SHELF"
    assert data["eq_list"][0]["freq"] == 50.0
    # Padded 6th band is disabled
    assert data["eq_list"][5]["enable"] == 0


def test_export_qudelix_files(tmp_path: Path):
    """Verify writing Qudelix JSON and text to disk."""
    json_target = tmp_path / "q5k_profile.json"
    txt_target = tmp_path / "q5k_profile.txt"

    out_json = export_qudelix(SAMPLE_PRESET, output_path=json_target, as_json=True)
    out_txt = export_qudelix(SAMPLE_PRESET, output_path=txt_target, as_json=False)

    assert out_json.is_file()
    assert out_txt.is_file()

    parsed_json = json.loads(out_json.read_text())
    assert parsed_json["profile_name"] == "bmasterx6"
    assert "Preamp: -2.5 dB" in out_txt.read_text()


def test_parse_qudelix_profiles():
    """Verify parsing Qudelix profiles from JSON and text representations."""
    # From JSON
    json_data = format_qudelix_json(SAMPLE_PRESET)
    parsed_from_json = parse_qudelix_profile(json_data)
    assert parsed_from_json["name"] == "bmasterx6"
    assert parsed_from_json["preamp"] == -2.5
    assert len(parsed_from_json["bands"]) == 5
    assert parsed_from_json["bands"][0]["type"] == "LSQ"

    # From text
    text_data = format_qudelix_text(SAMPLE_PRESET)
    parsed_from_text = parse_qudelix_profile(text_data)
    assert parsed_from_text["preamp"] == -2.5
    assert len(parsed_from_text["bands"]) == 5
    assert parsed_from_text["bands"][0]["type"] == "LSQ"
    assert parsed_from_text["bands"][0]["freq"] == 50.0


def test_auto_preamp_anti_clipping_guard():
    """Verify auto-preamp applies negative gain headroom when positive boosts exist."""
    boost_preset = {
        "name": "bass_boost",
        "preamp": 0.0,
        "bands": [
            {"index": 1, "type": "LSQ", "freq": 60.0, "gain": 6.0, "q": 0.71},
        ],
    }

    # Without auto-preamp, preamp remains 0.0
    apo_normal = format_equalizer_apo(boost_preset, auto_preamp=False)
    assert "Preamp: +0.0 dB" in apo_normal

    # With auto-preamp, negative attenuation is applied
    apo_guarded = format_equalizer_apo(boost_preset, auto_preamp=True)
    assert "Preamp: -" in apo_guarded

    # Qudelix auto-preamp
    q5k_guarded = format_qudelix_json(boost_preset, auto_preamp=True)
    assert q5k_guarded["preamp_db"] < 0.0


