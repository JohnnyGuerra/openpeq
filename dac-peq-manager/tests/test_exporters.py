"""Tests for PipeWire, EqualizerAPO, and Wavelet configuration exporters."""

import json
from pathlib import Path
from dac_peq.exporters import (
    DEFAULT_CX31993_SINK,
    decode_preset_from_url_params,
    encode_preset_to_url_params,
    export_apo_suite,
    export_pipewire_conf,
    export_qudelix,
    format_equalizer_apo,
    format_pipewire_filter_chain,
    format_qudelix_json,
    format_qudelix_text,
    format_wavelet_graphiceq,
    format_wavelet_json,
    parse_parametric_eq,
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


def test_parse_parametric_eq_graphworks_format():
    """Verify parsing standard GraphWorks / Equalizer APO export formats."""
    raw_graphworks = """# Preset: Simgot SuperMix 4 Diffuse Field Target
# Description: GraphWorks 5128 Target Compensation
Preamp: -3.8 dB
Filter 1: ON LSQ Fc 85.0 Hz Gain +4.2 dB Q 0.71
Filter 2: ON PK Fc 220.0 Hz Gain -1.8 dB Q 1.40
Filter 3: ON PK Fc 2800.0 Hz Gain +2.5 dB Q 2.00
Filter 4: ON PK Fc 5600.0 Hz Gain -3.0 dB Q 3.20
Filter 5: ON HSQ Fc 11500.0 Hz Gain -1.5 dB Q 0.70
Filter 6: OFF PK Fc 1000.0 Hz Gain 0.0 dB Q 1.00
"""
    parsed = parse_parametric_eq(raw_graphworks)
    assert parsed["name"] == "Simgot SuperMix 4 Diffuse Field Target"
    assert parsed["preamp"] == -3.8
    assert len(parsed["bands"]) == 5  # Disabled 0.0 dB filter excluded
    assert parsed["bands"][0]["type"] == "LSQ"
    assert parsed["bands"][0]["freq"] == 85.0
    assert parsed["bands"][0]["gain"] == 4.2
    assert parsed["bands"][0]["q"] == 0.71
    assert parsed["bands"][4]["type"] == "HSQ"
    assert parsed["bands"][4]["freq"] == 11500.0


def test_parse_parametric_eq_no_index_and_csv():
    """Verify parsing unindexed filters and CSV tabular formats."""
    # Unindexed filter lines
    apo_unindexed = """
Pre-amp: -2.0 dB
Filter: ON PK Fc 150.0 Hz Gain -3.0 dB Q 1.5
Filter: ON PK Fc 3200 Hz Gain 2.0 Q 2.5
"""
    parsed = parse_parametric_eq(apo_unindexed)
    assert parsed["preamp"] == -2.0
    assert len(parsed["bands"]) == 2
    assert parsed["bands"][0]["freq"] == 150.0
    assert parsed["bands"][0]["gain"] == -3.0
    assert parsed["bands"][1]["freq"] == 3200.0
    assert parsed["bands"][1]["gain"] == 2.0

    # CSV format
    csv_text = """Type, Frequency, Gain, Q
LSQ, 60.0, 5.0, 0.71
PK, 1200.0, -2.5, 1.41
HSQ, 8000.0, -1.0, 0.71
"""
    parsed_csv = parse_parametric_eq(csv_text)
    assert len(parsed_csv["bands"]) == 3
    assert parsed_csv["bands"][0]["type"] == "LSQ"
    assert parsed_csv["bands"][1]["freq"] == 1200.0
    assert parsed_csv["bands"][2]["type"] == "HSQ"


def test_parse_parametric_eq_invalid():
    """Verify appropriate error on invalid or empty configs."""
    import pytest
    with pytest.raises(ValueError, match="Cannot parse empty"):
        parse_parametric_eq("   ")

    with pytest.raises(ValueError, match="No valid parametric EQ filters"):
        parse_parametric_eq("# Only comments\n# Nothing else here\n")


def test_url_params_encode_decode_roundtrip():
    """Verify encoding and decoding PEQ presets via URL query parameters and squig.link format."""
    import pytest

    encoded = encode_preset_to_url_params(SAMPLE_PRESET, hw_bands=5)
    assert "name=bmasterx6" in encoded
    assert "preamp=-2.5" in encoded
    assert "hw=5" in encoded
    assert "b1=LSQ%2C50%2C2.2%2C0.71" in encoded

    decoded = decode_preset_from_url_params(f"https://johnnyguerra.github.io/dac-peq-manager/?{encoded}")
    assert decoded["name"] == "bmasterx6"
    assert decoded["preamp"] == -2.5
    assert decoded["hw_bands"] == 5
    assert len(decoded["bands"]) == 5
    assert decoded["bands"][0]["type"] == "LSQ"
    assert decoded["bands"][0]["freq"] == 50.0
    assert decoded["bands"][0]["gain"] == 2.2
    assert decoded["bands"][0]["q"] == 0.71

    # Also test squig.link / semicolon eq= format
    squig_url = "https://silicagel.squig.link/?share=SilicaGel_Target&preamp=-3.2&eq=LSQ,105,4.5,0.71;PK,2800,2.1,1.50;HSQ,10000,-1.5,0.71"
    decoded_squig = decode_preset_from_url_params(squig_url)
    assert decoded_squig["name"] == "SilicaGel_Target"
    assert decoded_squig["preamp"] == -3.2
    assert len(decoded_squig["bands"]) == 3
    assert decoded_squig["bands"][0]["type"] == "LSQ"
    assert decoded_squig["bands"][1]["freq"] == 2800.0
    assert decoded_squig["bands"][2]["type"] == "HSQ"

    with pytest.raises(ValueError):
        decode_preset_from_url_params("https://example.com/?foo=bar")


def test_parse_parametric_eq_lsc_hsc():
    """Verify that EqualizerAPO LSC and HSC filter types parse as LSQ and HSQ."""
    apo_text = """Preamp: -3.0 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.71
Filter 2: ON HSC Fc 10000 Hz Gain -3.0 dB Q 0.71
Filter 3: ON PK Fc 2500 Hz Gain 2.0 dB Q 1.50
Filter 4: OFF PK Fc 4000 Hz Gain -1.5 dB Q 2.00
"""
    preset = parse_parametric_eq(apo_text)
    assert preset["preamp"] == -3.0
    assert len(preset["bands"]) == 4
    assert preset["bands"][0]["type"] == "LSQ"
    assert preset["bands"][0]["freq"] == 105.0
    assert preset["bands"][0]["gain"] == 5.5
    assert preset["bands"][0]["enabled"] is True

    assert preset["bands"][1]["type"] == "HSQ"
    assert preset["bands"][1]["freq"] == 10000.0
    assert preset["bands"][1]["gain"] == -3.0
    assert preset["bands"][1]["enabled"] is True

    assert preset["bands"][2]["type"] == "PK"
    assert preset["bands"][2]["enabled"] is True

    assert preset["bands"][3]["type"] == "PK"
    assert preset["bands"][3]["enabled"] is False


def test_exporters_disabled_bands():
    """Verify disabled bands handling across EqualizerAPO, PipeWire, and URL encoding/decoding."""
    preset = {
        "name": "disabled_demo",
        "preamp": -1.5,
        "bands": [
            {"index": 1, "type": "LSQ", "freq": 100.0, "gain": 4.0, "q": 0.71, "enabled": True},
            {"index": 2, "type": "PK", "freq": 1000.0, "gain": 2.5, "q": 1.41, "enabled": False},
        ],
    }

    # 1. EqualizerAPO format
    apo = format_equalizer_apo(preset)
    assert "Filter 1: ON LSQ Fc 100.0 Hz Gain +4.0 dB Q 0.71" in apo
    assert "Filter 2: OFF PK Fc 1000.0 Hz Gain +2.5 dB Q 1.41" in apo

    # 2. PipeWire format: disabled band has Gain = 0.00
    pw = format_pipewire_filter_chain(preset)
    assert '"Gain" = 4.00' in pw
    assert '"Gain" = 0.00' in pw

    # 3. URL encoding / decoding
    encoded = encode_preset_to_url_params(preset)
    assert "b1=LSQ%2C100%2C4.0%2C0.71" in encoded
    assert "b2=PK%2C1000%2C2.5%2C1.41%2C0" in encoded

    decoded = decode_preset_from_url_params(f"https://example.com/?{encoded}")
    assert len(decoded["bands"]) == 2
    assert decoded["bands"][0]["enabled"] is True
    assert decoded["bands"][1]["enabled"] is False
    assert decoded["bands"][1]["gain"] == 2.5




