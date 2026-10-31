"""Cross-Engine Mathematical Parity Test Suite (Python vs. ES6 JavaScript).

Executes `web/modules/biquad_math.js`, `web/modules/exporters.js`, and
`web/modules/hid_transport.js` directly inside Node.js and asserts bit-accurate /
IEEE-754 floating-point parity (< 1e-9 tolerance) against Python `dac_peq`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dac_peq.biquad import (
    apply_macro_adjustments,
    calculate_curve_difference,
    calculate_peak_composite_gain,
    calculate_rbj_biquad,
    calculate_recommended_preamp,
    compute_composite_response,
    decimate_bands,
    generate_log_frequencies,
    smooth_coupler_biquads,
)
from dac_peq.exporters import (
    decode_preset_from_url_params,
    encode_preset_to_url_params,
    format_wavelet_graphiceq,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
FIXTURES_FILE = Path(__file__).resolve().parent / "fixtures" / "dsp_test_vectors.json"


def run_node_eval(js_code: str) -> dict:
    """Run an ES6 module snippet in Node.js with working directory set to `web/`."""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", js_code],
        cwd=str(WEB_DIR),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


def test_rbj_biquad_coefficients_parity():
    """Verify Python `calculate_rbj_biquad` and JS `calculateRBJCoeffs` match within 1e-9."""
    vectors = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    cases = vectors["biquad_cases"]

    js_script = f"""
    import {{ calculateRBJCoeffs, evaluateBiquadAt }} from './modules/biquad_math.js';
    const cases = {json.dumps(cases)};
    const out = cases.map(c => {{
      const coeffs = calculateRBJCoeffs(c.type, c.freq, c.gain, c.q, c.fs);
      const resp1k = evaluateBiquadAt(coeffs, 1000.0, c.fs);
      const respFc = evaluateBiquadAt(coeffs, c.freq, c.fs);
      return {{ coeffs, resp1k, respFc }};
    }});
    console.log(JSON.stringify({{ results: out }}));
    """
    js_results = run_node_eval(js_script)["results"]

    for case, js_res in zip(cases, js_results):
        py_c = calculate_rbj_biquad(
            filter_type=case["type"],
            freq=case["freq"],
            gain_db=case["gain"],
            q=case["q"],
            fs=case["fs"],
        )
        js_c = js_res["coeffs"]

        assert abs(py_c.b0 - js_c["b0"]) < 1e-9
        assert abs(py_c.b1 - js_c["b1"]) < 1e-9
        assert abs(py_c.b2 - js_c["b2"]) < 1e-9
        assert abs(py_c.a1 - js_c["a1"]) < 1e-9
        assert abs(py_c.a2 - js_c["a2"]) < 1e-9
        assert abs(py_c.response_at(1000.0) - js_res["resp1k"]) < 1e-9
        assert abs(py_c.response_at(case["freq"]) - js_res["respFc"]) < 1e-9


def test_composite_curve_and_auto_preamp_parity():
    """Verify 127-point composite response curve and auto-preamp match identically."""
    vectors = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    preset = vectors["preset_10_band"]
    bands = preset["bands"]
    preamp = preset["preamp"]

    py_freqs = generate_log_frequencies(20.0, 20000.0, 127)
    py_curve = compute_composite_response(bands, preamp, py_freqs)
    py_peak = calculate_peak_composite_gain(bands)
    py_rec_preamp = calculate_recommended_preamp(bands)

    js_script = f"""
    import {{
      generateLogFrequencies,
      computeCompositeCurve,
      calculatePeakCompositeGain,
      calculateRecommendedPreamp
    }} from './modules/biquad_math.js';
    const bands = {json.dumps(bands)};
    const preamp = {json.dumps(preamp)};
    const freqs = generateLogFrequencies(127, 20.0, 20000.0);
    const curve = computeCompositeCurve(bands, preamp, freqs);
    const peak = calculatePeakCompositeGain(bands, 500);
    const recPreamp = calculateRecommendedPreamp(bands, 0.5);
    console.log(JSON.stringify({{ freqs, curve, peak, recPreamp }}));
    """
    js_out = run_node_eval(js_script)

    for pf, jf in zip(py_freqs, js_out["freqs"]):
        assert abs(pf - jf) < 1e-7

    for pc, jc in zip(py_curve, js_out["curve"]):
        assert abs(pc - jc) < 1e-9

    assert abs(py_peak - js_out["peak"]) < 1e-9
    assert py_rec_preamp == js_out["recPreamp"]


def test_landmark_decimation_and_rms_delta_parity():
    """Verify 10->5 and 10->9 landmark decimation and RMS delta metrics match identically."""
    vectors = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    bands_10 = vectors["preset_10_band"]["bands"]
    preamp = vectors["preset_10_band"]["preamp"]

    py_dec5 = decimate_bands(bands_10, target_bands=5)
    py_dec9 = decimate_bands(bands_10, target_bands=9)
    py_diff = calculate_curve_difference(py_dec5, preamp, bands_10, preamp)

    js_script = f"""
    import {{ decimateBands, calculateCurveDifference }} from './modules/biquad_math.js';
    const bands10 = {json.dumps(bands_10)};
    const preamp = {json.dumps(preamp)};
    const dec5 = decimateBands(bands10, 5);
    const dec9 = decimateBands(bands10, 9);
    const diff = calculateCurveDifference(dec5, preamp, bands10, preamp);
    console.log(JSON.stringify({{ dec5, dec9, diff }}));
    """
    js_out = run_node_eval(js_script)

    assert len(py_dec5) == len(js_out["dec5"]) == 5
    for pb, jb in zip(py_dec5, js_out["dec5"]):
        assert pb["index"] == jb["index"]
        assert pb["type"] == jb["type"]
        assert pb["freq"] == jb["freq"]
        assert pb["gain"] == jb["gain"]
        assert pb["q"] == jb["q"]

    assert len(py_dec9) == len(js_out["dec9"]) == 9
    for pb, jb in zip(py_dec9, js_out["dec9"]):
        assert pb["freq"] == jb["freq"]
        assert pb["gain"] == jb["gain"]

    assert py_diff["rms_db"] == js_out["diff"]["rms_db"]
    assert py_diff["max_diff_db"] == js_out["diff"]["max_diff_db"]
    assert py_diff["max_diff_freq"] == js_out["diff"]["max_diff_freq"]
    assert py_diff["pinna_rms_db"] == js_out["diff"]["pinna_rms_db"]


def test_wavelet_graphiceq_exporter_parity():
    """Verify Python `format_wavelet_graphiceq` and JS `formatWaveletGraphicEq` produce identical strings."""
    vectors = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    preset = vectors["preset_10_band"]

    py_geq = format_wavelet_graphiceq(preset, points=127)

    js_script = f"""
    import {{ formatWaveletGraphicEq }} from './modules/exporters.js';
    const bands = {json.dumps(preset["bands"])};
    const preamp = {json.dumps(preset["preamp"])};
    const geq = formatWaveletGraphicEq(bands, preamp, 127);
    console.log(JSON.stringify({{ geq }}));
    """
    js_out = run_node_eval(js_script)
    assert py_geq == js_out["geq"]


def test_dac_catalog_and_autoeq_fallback_parity():
    """Verify that Python and Web dacs.json catalogs and offline AutoEq fallbacks are in sync."""
    py_dacs = (ROOT_DIR / "src" / "dac_peq" / "data" / "dacs.json").read_text(encoding="utf-8")
    web_dacs = (ROOT_DIR / "web" / "dacs.json").read_text(encoding="utf-8")
    assert json.loads(py_dacs) == json.loads(web_dacs)

    py_fallback = json.loads((ROOT_DIR / "src" / "dac_peq" / "data" / "autoeq_fallback.json").read_text(encoding="utf-8"))
    js_script = """
    import { OFFLINE_AUTOEQ_FALLBACK } from './modules/autoeq_client.js';
    console.log(JSON.stringify({ fallback: OFFLINE_AUTOEQ_FALLBACK }));
    """
    js_fallback = run_node_eval(js_script)["fallback"]
    assert len(py_fallback) == len(js_fallback)
    py_names = [m["name"] for m in py_fallback]
    js_names = [m["name"] for m in js_fallback]
    assert py_names == js_names


def test_hid_register_decode_parity():
    """Verify that WebHID decoders match Python register framing for both KTMicro and Moondrop."""
    # 1. KTMicro band register decode
    # Gain: +3.5 dB -> 35 -> 0x0023
    # Freq: 2400 Hz -> 0x0960
    # Q: 1.4 -> 1400 -> 0x0578
    # Type: PK -> 0
    gf_resp = [0x26, 0x00, 0x00, 0x00, 0x52, 0x00, 0x23, 0x00, 0x60, 0x09]
    q_resp = [0x27, 0x00, 0x00, 0x00, 0x52, 0x00, 0x78, 0x05, 0x00, 0x00]

    js_script = f"""
    import {{ decodeKtMicroBandRegisters }} from './modules/hid_transport.js';
    const gfResp = {json.dumps(gf_resp)};
    const qResp = {json.dumps(q_resp)};
    const band = decodeKtMicroBandRegisters(gfResp, qResp, false);
    console.log(JSON.stringify({{ band }}));
    """
    js_band = run_node_eval(js_script)["band"]
    assert js_band["type"] == "PK"
    assert js_band["freq"] == 2400.0
    assert js_band["gain"] == 3.5
    assert js_band["q"] == 1.4

    # 2. Moondrop FreeDSP 64-byte payload decode
    from dac_peq.moondrop import MoondropFreeDSPDevice
    moondrop = MoondropFreeDSPDevice(use_mock=True)
    test_preset = {
        "preamp": -2.5,
        "bands": [
            {"index": 1, "type": "LSQ", "freq": 80.0, "gain": 4.0, "q": 0.7},
            {"index": 2, "type": "PK", "freq": 3200.0, "gain": -2.0, "q": 2.0},
        ],
    }
    with moondrop:
        moondrop.apply_preset(test_preset)
        raw_payload = list(moondrop._dev.last_payload)
        py_read = moondrop.read_current_peq()

    js_script_moon = f"""
    import {{ decodeMoondropReport }} from './modules/hid_transport.js';
    const raw = {json.dumps(raw_payload)};
    const decoded = decodeMoondropReport(raw);
    console.log(JSON.stringify({{ decoded }}));
    """
    js_moon = run_node_eval(js_script_moon)["decoded"]
    assert py_read["preamp"] == js_moon["preamp"]
    assert len(py_read["bands"]) == len(js_moon["bands"]) == 9
    for pb, jb in zip(py_read["bands"][:2], js_moon["bands"][:2]):
        assert pb["type"] == jb["type"]
        assert pb["freq"] == jb["freq"]
        assert pb["gain"] == jb["gain"]
        assert pb["q"] == jb["q"]


def test_stock_backup_storage_helpers():
    """Verify JavaScript stock backup helpers (save, get, has) in simulated localStorage."""
    js_script = """
    import { getStockBackupKey, saveStockBackup, getStockBackup, hasStockBackup } from './modules/hid_transport.js';

    const store = new Map();
    const mockStorage = {
      getItem: (k) => store.get(k) || null,
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };

    const dev = { vendorId: 0x31b2, productId: 0x0111 };
    const initialHas = hasStockBackup(dev, 3, mockStorage);

    const testPreset = {
      preamp: -2.0,
      bands: [{ index: 1, type: "PK", freq: 1000, gain: 2.5, q: 1.0 }],
    };

    const saved = saveStockBackup(dev, 3, testPreset, mockStorage);
    const postHas = hasStockBackup(dev, 3, mockStorage);
    const retrieved = getStockBackup(dev, 3, mockStorage);

    // Idempotent: should not overwrite first stock backup
    const overwriteAttempt = saveStockBackup(dev, 3, { preamp: 0.0, bands: [] }, mockStorage);
    const finalRetrieved = getStockBackup(dev, 3, mockStorage);

    console.log(JSON.stringify({
      initialHas,
      saved,
      postHas,
      retrieved,
      overwriteAttempt,
      finalRetrieved
    }));
    """
    res = run_node_eval(js_script)
    assert res["initialHas"] is False
    assert res["saved"] is True
    assert res["postHas"] is True
    assert res["retrieved"]["preamp"] == -2.0
    assert res["retrieved"]["bands"][0]["gain"] == 2.5
    assert res["overwriteAttempt"] is False  # Protected against overwriting factory state
    assert res["finalRetrieved"]["preamp"] == -2.0


def test_url_codec_and_macro_coupler_parity():
    """Verify Python and JS parity for URL share encoding/decoding, macro sliders, and coupler smoothing."""
    test_preset = {
        "name": "SilicaGel Benchmark",
        "preamp": -3.2,
        "bands": [
            {"index": 1, "type": "LSQ", "freq": 60.0, "gain": 2.5, "q": 0.71},
            {"index": 2, "type": "PK", "freq": 210.0, "gain": -1.4, "q": 1.25},
            {"index": 3, "type": "PK", "freq": 2850.0, "gain": 1.8, "q": 1.40},
            {"index": 4, "type": "PK", "freq": 8000.0, "gain": -4.4, "q": 3.60},
            {"index": 5, "type": "HSQ", "freq": 10500.0, "gain": 1.2, "q": 0.71},
        ],
    }

    py_encoded = encode_preset_to_url_params(test_preset, hw_bands=5)
    py_decoded = decode_preset_from_url_params(py_encoded)
    py_macro = apply_macro_adjustments(test_preset["bands"], bass_db=2.0, ear_gain_db=-1.0, treble_db=1.5)
    py_smoothed = smooth_coupler_biquads(test_preset["bands"])

    js_script = f"""
    import {{ encodePresetToUrlParams, decodePresetFromUrlParams }} from './modules/exporters.js';
    import {{ applyMacroAdjustments, smoothCouplerBiquads }} from './modules/biquad_math.js';
    const preset = {json.dumps(test_preset)};
    const encoded = encodePresetToUrlParams(preset, null, 5);
    const decoded = decodePresetFromUrlParams(encoded);
    const macro = applyMacroAdjustments(preset.bands, 2.0, -1.0, 1.5);
    const smoothed = smoothCouplerBiquads(preset.bands);
    console.log(JSON.stringify({{ encoded, decoded, macro, smoothed }}));
    """
    js_out = run_node_eval(js_script)

    assert py_encoded == js_out["encoded"]
    assert py_decoded["name"] == js_out["decoded"]["name"]
    assert py_decoded["preamp"] == js_out["decoded"]["preamp"]
    assert py_decoded["hw_bands"] == js_out["decoded"]["hw_bands"]
    assert py_decoded["bands"] == js_out["decoded"]["bands"]
    assert py_macro == js_out["macro"]
    assert py_smoothed == js_out["smoothed"]


def test_rust_wasm_three_way_parity():
    """Verify 3-way mathematical parity across Python, ES6 JavaScript, and compiled Rust WASM."""
    vectors = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    bands_10 = vectors["preset_10_band"]["bands"]
    py_freqs = generate_log_frequencies(20.0, 20000.0, 64)
    py_curve = compute_composite_response(bands_10, 0.0, py_freqs)
    py_dec5 = decimate_bands(bands_10, target_bands=5)
    py_exp10 = decimate_bands(py_dec5, target_bands=10)

    # Also test muting band 0 (enabled: False)
    bands_muted = [dict(b) for b in py_dec5]
    bands_muted[0]["enabled"] = False
    py_muted_curve = compute_composite_response([b for b in bands_muted if b.get("enabled", True)], 0.0, [50.0, 250.0, 1000.0, 4000.0, 12000.0])

    js_script = f"""
    import fs from 'node:fs';
    import initWasm, {{ compute_composite_curve, compute_composite_curve_at_freqs, decimate_bands_json }} from './wasm/dac_peq_wasm.js';
    import {{ decimateBands }} from './modules/biquad_math.js';

    const wasmBytes = fs.readFileSync('./wasm/dac_peq_wasm_bg.wasm');
    await initWasm(wasmBytes);

    const bands10 = {json.dumps(bands_10)};
    const freqs = {json.dumps(py_freqs)};
    const bandsMuted = {json.dumps(bands_muted)};
    const customFreqs = [50.0, 250.0, 1000.0, 4000.0, 12000.0];

    const wasmCurve = Array.from(compute_composite_curve(JSON.stringify(bands10), 0.0, freqs.length, 48000.0));
    const wasmDec5 = JSON.parse(decimate_bands_json(JSON.stringify(bands10), 5));
    const wasmExp10 = JSON.parse(decimate_bands_json(JSON.stringify(wasmDec5), 10));
    const jsExp10 = decimateBands(wasmDec5, 10);
    const wasmMutedCurve = Array.from(compute_composite_curve_at_freqs(JSON.stringify(bandsMuted), 0.0, new Float64Array(customFreqs), 48000.0));

    console.log(JSON.stringify({{ wasmCurve, wasmDec5, wasmExp10, jsExp10, wasmMutedCurve }}));
    """
    wasm_out = run_node_eval(js_script)

    for pc, wc in zip(py_curve, wasm_out["wasmCurve"]):
        assert abs(pc - wc) < 1e-6

    assert len(wasm_out["wasmDec5"]) == len(py_dec5) == 5
    for pb, wb in zip(py_dec5, wasm_out["wasmDec5"]):
        assert abs(pb["freq"] - wb["freq"]) < 1e-6
        assert abs(pb["gain"] - wb["gain"]) < 1e-6
        assert abs(pb["q"] - wb["q"]) < 1e-6

    # 3-way 5 -> 10 expansion parity (Python == JS == Rust WASM)
    assert len(py_exp10) == len(wasm_out["jsExp10"]) == len(wasm_out["wasmExp10"]) == 10
    for pb, jb, wb in zip(py_exp10, wasm_out["jsExp10"], wasm_out["wasmExp10"]):
        assert pb["type"] == jb["type"] == wb["type"]
        assert abs(pb["freq"] - jb["freq"]) < 1e-6
        assert abs(pb["freq"] - wb["freq"]) < 1e-6
        assert abs(pb["gain"] - wb["gain"]) < 1e-6
        assert abs(pb["q"] - wb["q"]) < 1e-6

    # Custom frequencies & enabled=false parity
    for pm, wm in zip(py_muted_curve, wasm_out["wasmMutedCurve"]):
        assert abs(pm - wm) < 1e-6





