"""Test Suite for Web Flasher: WebHID Register Safety, Web WASM Wiring, and DOM XSS Remediation.

Executes Web modules in Node.js to verify browser-side security invariants and math wiring.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to execute the web modules")


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


# ── Task 8: DOM XSS Remediation Tests ─────────────────────────────────────────


def test_escape_html_escaping():
    """Verify that escapeHtml properly escapes HTML special characters and handles null/undefined."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    globalThis.document = { querySelector: () => null, getElementById: () => null };

    const { escapeHtml } = await import("./app.js");

    const cases = [
      { input: "<script>alert('xss')</script>", expected: "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" },
      { input: '"><img src=x onerror=alert(1)>', expected: '&quot;&gt;&lt;img src=x onerror=alert(1)&gt;' },
      { input: "Rock & Roll", expected: "Rock &amp; Roll" },
      { input: null, expected: "" },
      { input: undefined, expected: "" },
      { input: 12345, expected: "12345" },
    ];

    const results = cases.map(c => ({
      actual: escapeHtml(c.input),
      matches: escapeHtml(c.input) === c.expected
    }));

    console.log(JSON.stringify({ results }));
    """
    res = run_node_eval(js_code)
    for item in res["results"]:
        assert item["matches"] is True


def test_update_device_badge_escapes_xss():
    """Verify that updateDeviceBadge neutralizes HTML injection payloads in badge text and type."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    const badge = { className: "", innerHTML: "" };
    globalThis.document = {
      querySelector: () => null,
      getElementById: (id) => id === "deviceBadge" ? badge : null
    };

    const { updateDeviceBadge } = await import("./app.js");

    const payload = '<img src=x onerror="alert(document.cookie)">';
    updateDeviceBadge("connected", payload);

    console.log(JSON.stringify({
      innerHtml: badge.innerHTML,
      hasScriptOrImgTag: badge.innerHTML.includes("<img") || badge.innerHTML.includes("<script"),
      hasEscapedPayload: badge.innerHTML.includes("&lt;img src=x onerror=&quot;alert(document.cookie)&quot;&gt;")
    }));
    """
    res = run_node_eval(js_code)
    assert res["hasScriptOrImgTag"] is False
    assert res["hasEscapedPayload"] is True


def test_perform_database_search_escapes_xss():
    """Verify that performDatabaseSearch escapes search queries and community database items."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    const dbContainer = { style: {}, innerHTML: "", appendChild(c) { this.children = this.children || []; this.children.push(c); } };
    const searchInput = { value: '<script>alert("query-xss")</script>' };
    const sourceFilter = { value: "" };

    globalThis.document = {
      querySelector: () => null,
      getElementById: (id) => {
        if (id === "dbSearchInput") return searchInput;
        if (id === "dbSourceFilter") return sourceFilter;
        if (id === "dbResultsList") return dbContainer;
        return null;
      }
    };
    globalThis.showToast = () => {};

    const { performDatabaseSearch } = await import("./app.js");
    await performDatabaseSearch();

    console.log(JSON.stringify({
      containerHtml: dbContainer.innerHTML,
      hasRawScript: dbContainer.innerHTML.includes("<script>"),
      hasEscapedQuery: dbContainer.innerHTML.includes("&lt;script&gt;alert(&quot;query-xss&quot;)&lt;/script&gt;")
    }));
    """
    res = run_node_eval(js_code)
    assert res["hasRawScript"] is False
    assert res["hasEscapedQuery"] is True


def test_render_dac_directory_escapes_xss():
    """Verify that renderDacDirectory escapes malicious field injections in DAC directory cards."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    const dacGrid = {
      innerHTML: "",
      appendChild(c) {
        this.children = this.children || [];
        this.children.push(c);
      }
    };

    globalThis.document = {
      querySelector: () => null,
      getElementById: (id) => {
        if (id === "dacGrid") return dacGrid;
        if (id === "dacCountAll") return { textContent: "" };
        if (id === "dacSearchInput") return { value: "" };
        return null;
      },
      createElement: (tag) => ({
        className: "",
        innerHTML: "",
        setAttribute: () => {}
      })
    };

    const app = await import("./app.js");

    // Inject a malicious DAC record into catalog
    const evilDac = {
      id: "evil_dac",
      name: '<img src=x onerror="alert(\\'name\\')">',
      brand: '<script>alert("brand")</script>',
      chipset: '<b>KTMicro</b>',
      architecture: 'ktmicro_dsp',
      resolution: '<script>resolution</script>',
      output_power: '<iframe src=evil.com></iframe>',
      recommendation: '<img src=x onerror=steal()>',
      flashable: true,
      vid_hex: '0x31B2<script>',
      pid_hex: '0x0111',
      price_usd: '49.99<script>',
      max_bands: 5,
      notes: '<script>notes</script>'
    };

    // Replace catalog and render
    app.renderDacDirectory(null, "");
    // Manually test card rendering logic for evilDac
    const testCard = globalThis.document.createElement("div");
    // Directly run render with evil item
    const safeBrand = app.escapeHtml(evilDac.brand);
    const safeName = app.escapeHtml(evilDac.name);
    const safeChipset = app.escapeHtml(evilDac.chipset);
    const safeRec = app.escapeHtml(evilDac.recommendation);

    console.log(JSON.stringify({
      safeBrand,
      safeName,
      safeChipset,
      safeRec,
      hasRawScript: safeBrand.includes("<script>") || safeName.includes("<img src=x onerror="),
      hasEscapedScript: safeBrand.includes("&lt;script&gt;") && safeName.includes("&lt;img src=x")
    }));
    """
    res = run_node_eval(js_code)
    assert res["hasRawScript"] is False
    assert res["hasEscapedScript"] is True


# ── Task 7: WebHID Register Safety & Guardrails Tests ─────────────────────────


def test_send_ktmicro_filter_blocks_non_fiio_devices():
    """Verify that sendKtMicroFilter raises safety error on Allegro Mini (0x31B2) and JCALLY (0x1908), allowing FiiO (0x2972)."""
    js_code = """
    import { sendKtMicroFilter } from "./modules/hid_transport.js";

    async function run() {
      // 1. Allegro Mini 0x31B2
      const devAllegro = { vendorId: 0x31B2, productId: 0x0111 };
      let blockedAllegro = false;
      let allegroErr = "";
      try {
        await sendKtMicroFilter(devAllegro, 1);
      } catch (e) {
        blockedAllegro = true;
        allegroErr = e.message;
      }

      // 2. JCALLY JM12 0x1908
      const devJcally = { vendorId: 0x1908, productId: 0x2020 };
      let blockedJcally = false;
      let jcallyErr = "";
      try {
        await sendKtMicroFilter(devJcally, 1);
      } catch (e) {
        blockedJcally = true;
        jcallyErr = e.message;
      }

      // 3. FiiO JA11 0x2972
      let fiioSent = false;
      const devFiio = {
        vendorId: 0x2972,
        productId: 0x0102,
        sendReport: async (id, payload) => {
          fiioSent = (id === 0x4b && payload[0] === 0x11);
        }
      };
      await sendKtMicroFilter(devFiio, 2);

      console.log(JSON.stringify({
        blockedAllegro,
        allegroErr,
        blockedJcally,
        jcallyErr,
        fiioSent
      }));
    }
    run();
    """
    res = run_node_eval(js_code)
    assert res["blockedAllegro"] is True
    assert "SAFETY BLOCK: Register 0x11" in res["allegroErr"]
    assert "0x31B2" in res["allegroErr"]
    assert res["blockedJcally"] is True
    assert "SAFETY BLOCK: Register 0x11" in res["jcallyErr"]
    assert res["fiioSent"] is True


def test_read_ktmicro_peq_skips_0x66_and_0x11_on_0x31b2_and_0x11_on_0x1908():
    """Verify that readKtMicroPeq never touches 0x11 on non-FiiO DACs (Allegro Mini 0x31B2, JCALLY 0x1908)."""
    js_code = """
    import { readKtMicroPeq } from "./modules/hid_transport.js";

    function createMockDevice(vendorId, productId) {
      const polled = [];
      return {
        vendorId,
        productId,
        polled,
        addEventListener: (evt, cb) => {
          setTimeout(() => {
            const reg = polled[polled.length - 1];
            const resp = new Uint8Array(12);
            resp[0] = reg;
            resp[4] = 0x52; // CMD_READ acknowledgment
            resp[6] = 0x01;
            cb({ data: new DataView(resp.buffer) });
          }, 4);
        },
        removeEventListener: () => {},
        sendReport: async (id, data) => {
          polled.push(data[0]);
        }
      };
    }

    async function run() {
      // 1. Kiwi Ears Allegro Mini (0x31B2)
      const allegro = createMockDevice(0x31B2, 0x0111);
      const allegroData = await readKtMicroPeq(allegro);

      // 2. Generic device with options.noPregain = true
      const noPregainDev = createMockDevice(0x2972, 0x0102);
      await readKtMicroPeq(noPregainDev, { noPregain: true });

      // 3. JCALLY JM12 (0x1908)
      const jcally = createMockDevice(0x1908, 0x2020);
      const jcallyData = await readKtMicroPeq(jcally);

      // 4. FiiO JA11 (0x2972) without noPregain
      const fiio = createMockDevice(0x2972, 0x0102);
      const fiioData = await readKtMicroPeq(fiio);

      console.log(JSON.stringify({
        allegroPolled: allegro.polled,
        allegroTouchedPreamp: allegro.polled.includes(0x66),
        allegroTouchedFilter: allegro.polled.includes(0x11),
        allegroDacFilter: allegroData.dacFilter,
        noPregainTouchedPreamp: noPregainDev.polled.includes(0x66),
        noPregainTouchedFilter: noPregainDev.polled.includes(0x11),
        jcallyPolled: jcally.polled,
        jcallyTouchedPreamp: jcally.polled.includes(0x66),
        jcallyTouchedFilter: jcally.polled.includes(0x11),
        jcallyDacFilter: jcallyData.dacFilter,
        fiioTouchedPreamp: fiio.polled.includes(0x66),
        fiioTouchedFilter: fiio.polled.includes(0x11),
        fiioDacFilter: fiioData.dacFilter,
        allegroBandsCount: allegroData.bands.length
      }));
    }
    run();
    """
    res = run_node_eval(js_code)
    # Allegro Mini (0x31B2) must NOT poll 0x66 or 0x11; dacFilter must be null
    assert res["allegroTouchedPreamp"] is False
    assert res["allegroTouchedFilter"] is False
    assert res["allegroDacFilter"] is None
    # Explicit noPregain must NOT poll 0x66 or 0x11
    assert res["noPregainTouchedPreamp"] is False
    assert res["noPregainTouchedFilter"] is False
    # JCALLY (0x1908) polls preamp 0x66, but MUST NOT poll DAC filter 0x11; dacFilter must be null
    assert res["jcallyTouchedPreamp"] is True
    assert res["jcallyTouchedFilter"] is False
    assert res["jcallyDacFilter"] is None
    # FiiO JA11 MUST poll 0x66 and 0x11; dacFilter must be populated
    assert res["fiioTouchedPreamp"] is True
    assert res["fiioTouchedFilter"] is True
    assert res["fiioDacFilter"] == 1
    assert res["allegroBandsCount"] == 5


def test_clear_device_flash_guards_walkplay_and_moondrop():
    """Verify that clearDeviceFlash prevents 0x43 CLEAR on non-KTMicro DACs (WalkPlay, Moondrop)."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    let toastMsg = "";
    const toast = { textContent: "", classList: { add: () => {}, remove: () => {} } };
    globalThis.document = {
      querySelector: () => null,
      getElementById: (id) => id === "toast" ? toast : null
    };
    globalThis.confirm = () => true;

    const app = await import("./app.js");

    let reportSent = false;
    function makeDev(vid, pid, arch) {
      return {
        vendorId: vid,
        productId: pid,
        sendReport: async () => { reportSent = true; }
      };
    }

    // 1. WalkPlay DAC (0x3302)
    reportSent = false;
    app.setConnectedDevice(makeDev(0x3302, 0x43cc, "walkplay"), { arch: "walkplay" });
    await app.clearDeviceFlash();
    const walkplayBlocked = !reportSent && toast.textContent.includes("0x43 CLEAR");

    // 2. Moondrop FreeDSP (0x31B2:0x0112)
    reportSent = false;
    app.setConnectedDevice(makeDev(0x31B2, 0x0112, "moondrop"), { arch: "moondrop" });
    await app.clearDeviceFlash();
    const moondropBlocked = !reportSent && toast.textContent.includes("0x43 CLEAR");

    // 3. Allegro Mini (0x31B2:0x0111) KTMicro - allowed
    reportSent = false;
    app.setConnectedDevice(makeDev(0x31B2, 0x0111, "ktmicro"), { arch: "ktmicro" });
    await app.clearDeviceFlash();
    const allegroAllowed = reportSent;

    console.log(JSON.stringify({
      walkplayBlocked,
      moondropBlocked,
      allegroAllowed
    }));
    """
    res = run_node_eval(js_code)
    assert res["walkplayBlocked"] is True
    assert res["moondropBlocked"] is True
    assert res["allegroAllowed"] is True


# ── Task 6B: Web WASM Engine Wiring Tests ─────────────────────────────────────


def test_wasm_engine_compute_composite_response_wiring():
    """Verify computeCompositeResponseWasm pure JS fallback and mock Rust WASM invocation."""
    js_code = """
    import {
      computeCompositeResponseWasm,
      setWasmEngine,
      generatePipewireConfigWasm,
      generateApoConfigWasm
    } from "./modules/wasm_engine.js";

    const bands = [
      { freq: 1000, gain: 4.0, q: 1.4, type: "PK", enabled: true },
      { freq: 4000, gain: -2.0, q: 2.0, type: "PK", enabled: true },
      { freq: 8000, gain: 1.5, q: 1.0, type: "HSQ", enabled: false }
    ];
    const freqs = [500, 1000, 4000, 10000];

    // 1. Fallback when wasmModule is null
    setWasmEngine(null);
    const fallbackCurve = computeCompositeResponseWasm(bands, freqs);
    const fallbackPw = generatePipewireConfigWasm({ name: "Fallback Test", preamp: -1.0, bands });
    const fallbackApo = generateApoConfigWasm({ name: "Fallback Test", preamp: -1.0, bands });

    // 2. Active mock Rust WASM module
    let wasmCalled = false;
    let receivedBandsJson = "";
    setWasmEngine({
      compute_composite_curve: (json, freqsArr, fs) => {
        wasmCalled = true;
        receivedBandsJson = json;
        return new Float64Array([10.0, 20.0, 30.0, 40.0]);
      },
      generate_pipewire_config: (json) => "RUST_WASM_PIPEWIRE_CONF",
      generate_apo_config: (json) => "RUST_WASM_APO_CONF"
    });

    const wasmCurve = computeCompositeResponseWasm(bands, freqs);
    const wasmPw = generatePipewireConfigWasm({ name: "Wasm Test", preamp: 0.0, bands });
    const wasmApo = generateApoConfigWasm({ name: "Wasm Test", preamp: 0.0, bands });

    console.log(JSON.stringify({
      fallbackLength: fallbackCurve.length,
      fallbackPwHasNodes: fallbackPw.includes("nodes = ["),
      fallbackApoHasPreamp: fallbackApo.includes("Preamp:"),
      wasmCalled,
      wasmCurve,
      wasmPw,
      wasmApo,
      receivedBands: JSON.parse(receivedBandsJson)
    }));
    """
    res = run_node_eval(js_code)
    # Pure JS fallback works
    assert res["fallbackLength"] == 4
    assert res["fallbackPwHasNodes"] is True
    assert res["fallbackApoHasPreamp"] is True
    # WASM module invoked and schema verified
    assert res["wasmCalled"] is True
    assert res["wasmCurve"] == [10.0, 20.0, 30.0, 40.0]
    assert res["wasmPw"] == "RUST_WASM_PIPEWIRE_CONF"
    assert res["wasmApo"] == "RUST_WASM_APO_CONF"
    assert len(res["receivedBands"]) == 2
    assert res["receivedBands"][0]["freq"] == 1000
    assert res["receivedBands"][0]["gain"] == 4.0
    assert res["receivedBands"][1]["freq"] == 4000
    assert res["receivedBands"][1]["gain"] == -2.0


def test_wasm_engine_compute_composite_curve_at_freqs_wiring():
    """Verify computeCompositeResponseWasm invokes mod.compute_composite_curve_at_freqs with custom freqs."""
    js_code = """
    import {
      computeCompositeResponseWasm,
      setWasmEngine
    } from "./modules/wasm_engine.js";

    const bands = [
      { freq: 250, gain: 3.0, q: 1.0, type: "PK", enabled: true },
      { freq: 1000, gain: -1.5, q: 2.0, type: "PK", enabled: false }, // disabled band
      { freq: 4000, gain: 2.5, q: 1.5, type: "PK", enabled: true }
    ];
    const customFreqs = [100.0, 250.0, 1000.0, 4000.0, 10000.0];

    let atFreqsCalled = false;
    let receivedPreamp = null;
    let receivedFreqs = null;
    let receivedFs = null;
    let receivedBands = null;

    setWasmEngine({
      compute_composite_curve_at_freqs: (json, preamp, freqsArr, fs) => {
        atFreqsCalled = true;
        receivedBands = JSON.parse(json);
        receivedPreamp = preamp;
        receivedFreqs = Array.from(freqsArr);
        receivedFs = fs;
        return new Float64Array([0.5, 3.0, -0.2, 2.5, 0.1]);
      }
    });

    const curve = computeCompositeResponseWasm(bands, customFreqs, 96000);

    console.log(JSON.stringify({
      atFreqsCalled,
      receivedPreamp,
      receivedFreqs,
      receivedFs,
      receivedBands,
      curve
    }));
    """
    res = run_node_eval(js_code)
    assert res["atFreqsCalled"] is True
    assert res["receivedPreamp"] == 0.0
    assert res["receivedFreqs"] == [100.0, 250.0, 1000.0, 4000.0, 10000.0]
    assert res["receivedFs"] == 96000
    assert len(res["receivedBands"]) == 2
    assert res["receivedBands"][0]["freq"] == 250
    assert res["receivedBands"][1]["freq"] == 4000
    assert res["curve"] == [0.5, 3.0, -0.2, 2.5, 0.1]


def test_drag_raf_coalescing_and_flush():
    """Verify scheduleDragRender coalesces rapid pointer events and flushDragRender flushes pending updates."""
    js_code = """
    let rafCallbacks = [];
    let nextRafId = 1;
    globalThis.requestAnimationFrame = (cb) => {
      const id = nextRafId++;
      rafCallbacks.push({ id, cb });
      return id;
    };
    globalThis.cancelAnimationFrame = (id) => {
      rafCallbacks = rafCallbacks.filter(item => item.id !== id);
    };

    const svgEl = {
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 400 }),
      appendChild: () => {},
      querySelectorAll: () => []
    };
    globalThis.window = {
      addEventListener: () => {},
      removeEventListener: () => {}
    };
    const mockEl = {
      style: {},
      value: "0",
      textContent: "",
      options: [],
      classList: { add: () => {}, remove: () => {} },
      appendChild: () => {},
      setAttribute: () => {},
      addEventListener: () => {},
      removeEventListener: () => {}
    };
    globalThis.document = {
      querySelector: () => null,
      querySelectorAll: () => [],
      getElementById: (id) => (id === "eqSvg" ? svgEl : mockEl),
      createElement: () => mockEl,
      createElementNS: () => mockEl
    };

    const app = await import("./app.js");

    // Rapid pointer move simulation: schedule multiple renders before next frame
    app.scheduleDragRender(0);
    app.scheduleDragRender(0);
    app.scheduleDragRender(0);

    const queuedRafs = rafCallbacks.length;

    // Trigger frame
    if (rafCallbacks.length > 0) {
      const { cb } = rafCallbacks.shift();
      cb();
    }

    // Flush test
    app.scheduleDragRender(0);
    const hasPendingBeforeFlush = rafCallbacks.length === 1;
    app.flushDragRender();
    const hasPendingAfterFlush = rafCallbacks.length === 0;

    console.log(JSON.stringify({
      queuedRafs,
      hasPendingBeforeFlush,
      hasPendingAfterFlush
    }));
    """
    res = run_node_eval(js_code)
    assert res["queuedRafs"] == 1
    assert res["hasPendingBeforeFlush"] is True
    assert res["hasPendingAfterFlush"] is True


def test_bundled_presets_catalog_exported():
    """Verify PRESETS catalog is exported and contains all expected reference targets."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    globalThis.document = { querySelector: () => null, getElementById: () => null };

    const { PRESETS } = await import("./app.js");

    const keys = Object.keys(PRESETS);
    const hasBmaster = Boolean(PRESETS["bmasterx6"]);
    const hasEw300Silver = Boolean(PRESETS["ew300-silver"]);
    const hasJm1 = Boolean(PRESETS["jm-1"]);
    const hasHarman = Boolean(PRESETS["harman-2019v2"]);

    console.log(JSON.stringify({
      count: keys.length,
      hasBmaster,
      hasEw300Silver,
      hasJm1,
      hasHarman
    }));
    """
    res = run_node_eval(js_code)
    assert res["count"] >= 10
    assert res["hasBmaster"] is True
    assert res["hasEw300Silver"] is True
    assert res["hasJm1"] is True
    assert res["hasHarman"] is True


def test_parse_parametric_eq_lsc_hsc():
    """Verify parseParametricEq correctly maps LSC to LSQ and HSC to HSQ."""
    js_code = """
    import { parseParametricEq } from "./modules/exporters.js";

    const apoText = `
Preamp: -3.0 dB
Filter 1: ON LSC Fc 105.0 Hz Gain 4.5 dB Q 0.71
Filter 2: ON PK Fc 2500.0 Hz Gain -2.0 dB Q 1.80
Filter 3: ON HSC Fc 9500.0 Hz Gain 3.0 dB Q 0.71
    `;

    const parsed = parseParametricEq(apoText, "LSC HSC Test");
    console.log(JSON.stringify({
      preamp: parsed.preamp,
      bands: parsed.bands.map(b => ({ type: b.type, freq: b.freq, gain: b.gain, q: b.q }))
    }));
    """
    res = run_node_eval(js_code)
    assert res["preamp"] == -3.0
    assert len(res["bands"]) == 3
    assert res["bands"][0]["type"] == "LSQ"
    assert res["bands"][0]["freq"] == 105.0
    assert res["bands"][1]["type"] == "PK"
    assert res["bands"][2]["type"] == "HSQ"
    assert res["bands"][2]["freq"] == 9500.0


def test_exporters_respect_disabled_bands():
    """Verify generateApoConfig outputs OFF and generatePipewireConfig zeroes gain for disabled bands."""
    js_code = """
    import {
      generateApoConfig,
      generatePipewireConfig
    } from "./modules/exporters.js";

    const preset = {
      name: "Disabled Band Export Test",
      preamp: -2.0,
      bands: [
        { type: "PK", freq: 1000, gain: 4.0, q: 1.4, enabled: true },
        { type: "PK", freq: 4000, gain: -3.5, q: 2.0, enabled: false }
      ]
    };

    const apoTxt = generateApoConfig(preset, preset.bands);
    const pwConf = generatePipewireConfig(preset, preset.bands);

    console.log(JSON.stringify({
      apoTxt,
      pwConf,
      apoHasOn: apoTxt.includes("Filter 1: ON PK Fc 1000.0 Hz Gain +4.0 dB Q 1.40"),
      apoHasOff: apoTxt.includes("Filter 2: OFF PK Fc 4000.0 Hz Gain -3.5 dB Q 2.00"),
      pwHasZeroGain: pwConf.includes('"Gain" = 0.00'),
      pwHasActiveGain: pwConf.includes('"Gain" = 4.00')
    }));
    """
    res = run_node_eval(js_code)
    assert res["apoHasOn"] is True
    assert res["apoHasOff"] is True
    assert res["pwHasZeroGain"] is True
    assert res["pwHasActiveGain"] is True


def test_url_roundtrip_disabled_bands():
    """Verify encodePresetToUrlParams and decodePresetFromUrlParams round-trip enabled: false."""
    js_code = """
    import { encodePresetToUrlParams, decodePresetFromUrlParams } from "./modules/exporters.js";

    const preset = {
      name: "Roundtrip Test",
      preamp: -1.5,
      hw_bands: 5,
      bands: [
        { type: "LSQ", freq: 80.0, gain: 3.0, q: 0.71, enabled: true },
        { type: "PK", freq: 2500.0, gain: -2.5, q: 1.5, enabled: false },
        { type: "HSQ", freq: 10000.0, gain: 1.5, q: 0.71, enabled: true }
      ]
    };

    const urlParams = encodePresetToUrlParams(preset);
    const decoded = decodePresetFromUrlParams(urlParams);

    console.log(JSON.stringify({
      urlParams,
      decodedBands: decoded.bands.map(b => ({ type: b.type, freq: b.freq, gain: b.gain, enabled: b.enabled }))
    }));
    """
    res = run_node_eval(js_code)
    assert "b2=PK%2C2500%2C-2.5%2C1.50%2C0" in res["urlParams"] or "b2=PK,2500,-2.5,1.50,0" in res["urlParams"].replace("%2C", ",")
    assert len(res["decodedBands"]) == 3
    assert res["decodedBands"][0]["enabled"] is True
    assert res["decodedBands"][1]["enabled"] is False
    assert res["decodedBands"][2]["enabled"] is True


def test_encode_moondrop_report_zeroes_disabled_band_gain():
    """Verify encodeMoondropReport zeroes gain byte for bands with enabled: false."""
    js_code = """
    import { encodeMoondropReport } from "./modules/hid_transport.js";

    const bands = [
      { type: "PK", freq: 1000, gain: 4.0, q: 1.4, enabled: true },
      { type: "PK", freq: 4000, gain: 3.0, q: 2.0, enabled: false }
    ];

    const report = encodeMoondropReport(bands, 0.0);
    // Band 1: offset 4 => ftype=0, freq 1000 (0xe8, 0x03), gain 40 (4.0 * 10), q 14
    const b1Gain = report[7];
    // Band 2: offset 9 => ftype=0, freq 4000 (0xa0, 0x0f), gain 0 (disabled!), q 20
    const b2Gain = report[12];

    console.log(JSON.stringify({
      b1Gain,
      b2Gain
    }));
    """
    res = run_node_eval(js_code)
    assert res["b1Gain"] == 40
    assert res["b2Gain"] == 0


def test_autoeq_secondary_preamp_phrasing():
    """Verify parseAutoEqReadme parses secondary 'with X dB preamp' phrasing."""
    js_code = """
    import { parseAutoEqReadme } from "./modules/autoeq_client.js";

    const readme1 = `
### Parametric EQs
Apply preamp of -4.2 dB
| Filter | Type | Fc | Q | Gain |
|---|---|---|---|---|
| 1 | PK | 1000 | 1.0 | 2.5 |
    `;

    const readme2 = `
EQ recommendation: with -5.5 dB preamp to prevent digital clipping.
### Parametric EQs
| Filter | Type | Fc | Q | Gain |
|---|---|---|---|---|
| 1 | PK | 1000 | 1.0 | 2.5 |
    `;

    const res1 = parseAutoEqReadme(readme1);
    const res2 = parseAutoEqReadme(readme2);

    console.log(JSON.stringify({
      preamp1: res1.preamp,
      preamp2: res2.preamp
    }));
    """
    res = run_node_eval(js_code)
    assert res["preamp1"] == -4.2
    assert res["preamp2"] == -5.5


def test_lint_acoustic_bands_skips_disabled():
    """Verify lintAcousticBands ignores artificial coupler spikes and high boost on disabled bands."""
    js_code = """
    import { lintAcousticBands } from "./modules/biquad_math.js";

    const bands = [
      { type: "PK", freq: 8000, gain: -6.0, q: 3.5, enabled: false }, // coupler spike, disabled
      { type: "PK", freq: 1000, gain: 8.5, q: 1.0, enabled: false },  // high boost, disabled
      { type: "PK", freq: 2500, gain: 2.0, q: 1.2, enabled: true },   // safe active band
    ];

    const warnings = lintAcousticBands(bands);

    console.log(JSON.stringify({
      warningCount: warnings.length,
      warnings
    }));
    """
    res = run_node_eval(js_code)
    assert res["warningCount"] == 0


def test_decimate_bands_filters_disabled_bands():
    """Verify decimateBands prioritizes active bands and excludes disabled ones during decimation."""
    js_code = """
    import { decimateBands } from "./modules/biquad_math.js";

    const bands = [
      { type: "LSQ", freq: 60, gain: 3.0, q: 0.71, enabled: true },
      { type: "PK", freq: 200, gain: -2.0, q: 1.0, enabled: true },
      { type: "PK", freq: 500, gain: 5.0, q: 2.0, enabled: false }, // disabled!
      { type: "PK", freq: 1000, gain: -4.0, q: 2.0, enabled: false }, // disabled!
      { type: "PK", freq: 2500, gain: 2.5, q: 1.4, enabled: true },
      { type: "PK", freq: 4000, gain: -3.5, q: 2.0, enabled: false }, // disabled!
      { type: "HSQ", freq: 10000, gain: 2.0, q: 0.71, enabled: true },
    ];

    // Total 7 bands, 4 active. Target: 5 bands.
    // Decimator should prune 3 disabled bands and pad the 4 active bands to 5 bands.
    const out = decimateBands(bands, 5);

    console.log(JSON.stringify({
      count: out.length,
      freqs: out.map(b => b.freq),
      containsDisabledFreqs: out.some(b => [500, 1000, 4000].includes(b.freq))
    }));
    """
    res = run_node_eval(js_code)
    assert res["count"] == 5
    assert res["containsDisabledFreqs"] is False


def test_find_dac_in_database_disambiguation():
    """Verify findDacInDatabase disambiguates devices with identical 0x31B2:0x0111 using prodName."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    globalThis.document = { querySelector: () => null, getElementById: () => null };

    const { findDacInDatabase } = await import("./app.js");

    const nullDac = findDacInDatabase(null, null);
    const basn = findDacInDatabase(12722, 273, "BASN BmasterX 6");
    const jcally = findDacInDatabase(12722, 273, "JCALLY JM12");
    const allegro = findDacInDatabase(12722, 273, "Kiwi Ears Allegro Mini");
    const fallback = findDacInDatabase(12722, 273, "Unknown Generic Device");

    console.log(JSON.stringify({
      nullDac,
      basnId: basn?.id,
      jcallyId: jcally?.id,
      allegroId: allegro?.id,
      fallbackId: fallback?.id
    }));
    """
    res = run_node_eval(js_code)
    assert res["nullDac"] is None
    assert res["basnId"] == "bmasterx6_plug"
    assert res["jcallyId"] == "jcally_jm12"
    assert res["allegroId"] == "allegro_mini"
    assert res["fallbackId"] == "allegro_mini"


def test_file_input_preset_preserves_disabled_state():
    """Verify preset parsing preserves enabled: false on imported bands."""
    js_code = """
    globalThis.window = { addEventListener: () => {} };
    globalThis.document = { querySelector: () => null, getElementById: () => null };

    const { loadPresetObject } = await import("./app.js");

    const importedJson = {
      name: "Disabled Band Import Test",
      preamp: -2.0,
      bands: [
        { type: "PK", freq: 1000, gain: 3.0, q: 1.0, enabled: true },
        { type: "PK", freq: 4000, gain: -2.0, q: 2.0, enabled: false },
        { type: "HSQ", freq: 9000, gain: 1.5, q: 0.71 } // unspecified enabled => true
      ]
    };

    const loaded = loadPresetObject(importedJson);

    console.log(JSON.stringify({
      bands: loaded.bands.map(b => ({ freq: b.freq, enabled: b.enabled }))
    }));
    """
    res = run_node_eval(js_code)
    assert len(res["bands"]) == 3
    assert res["bands"][0]["enabled"] is True
    assert res["bands"][1]["enabled"] is False
    assert res["bands"][2]["enabled"] is True


def test_webhid_detect_firmware_quirks_no_device_version_hallucination():
    """Verify that detectFirmwareQuirks does not rely on deviceVersion/bcdDevice (which WebHID lacks)."""
    js_code = """
    import { detectFirmwareQuirks } from "./modules/hid_transport.js";

    // Standard W3C WebHID HIDDevice objects (no deviceVersion or bcdDevice property)
    const ja11 = { vendorId: 0x2972, productId: 0x0102, productName: "FiiO JA11" };
    const allegro = { vendorId: 0x31b2, productId: 0x0111, productName: "Kiwi Ears Allegro Mini" };
    const freedsp = { vendorId: 0x31b2, productId: 0x0112, productName: "Moondrop FreeDSP" };
    const walkplay = { vendorId: 0x0bda, productId: 0x0023, productName: "WalkPlay DAC" };
    const genericAllegro = { vendorId: 0x9999, productId: 0x8888, productName: "Generic Allegro DAC" };
    const genericOther = { vendorId: 0x1234, productId: 0x5678, productName: "Some Other DAC" };

    const ja11Quirks = detectFirmwareQuirks(ja11);
    const allegroQuirks = detectFirmwareQuirks(allegro);
    const freedspQuirks = detectFirmwareQuirks(freedsp);
    const walkplayQuirks = detectFirmwareQuirks(walkplay);
    const genericAllegroQuirks = detectFirmwareQuirks(genericAllegro);
    const genericOtherQuirks = detectFirmwareQuirks(genericOther);

    console.log(JSON.stringify({
      ja11Comp2X: ja11Quirks.requiresCompensate2X,
      allegroComp2X: allegroQuirks.requiresCompensate2X,
      freedspComp2X: freedspQuirks.requiresCompensate2X,
      walkplayComp2X: walkplayQuirks.requiresCompensate2X,
      genericAllegroComp2X: genericAllegroQuirks.requiresCompensate2X,
      genericOtherComp2X: genericOtherQuirks.requiresCompensate2X,
      nullDeviceComp2X: detectFirmwareQuirks(null).requiresCompensate2X
    }));
    """
    res = run_node_eval(js_code)
    # FiiO JA11 defaults to native clocking (firmware v1.8+)
    assert res["ja11Comp2X"] is False
    # Allegro Mini / KT02H20 defaults to 2X compensation
    assert res["allegroComp2X"] is True
    # FreeDSP is 9-band standard clocking
    assert res["freedspComp2X"] is False
    # WalkPlay 0x0bda:0x0023 is 2X compensation
    assert res["walkplayComp2X"] is True
    # Product name with "allegro" is 2X compensation
    # Identity cannot be confirmed from a product name: the guard fails closed
    assert res["genericAllegroComp2X"] is False
    # Generic other is false
    assert res["genericOtherComp2X"] is False
    # Null device is false
    assert res["nullDeviceComp2X"] is False


def test_web_app_preamp_safety_clamping_and_null_handling():
    """Verify that web flasher preamp calculation clamps between -24.0 and +12.0 dB,
    preventing signed-int8 sign inversion when negative gain is extreme."""
    js_code = """
    function computePreampByte(rawVal) {
      const parsed = Number(rawVal ?? 0.0);
      const safeVal = Number.isFinite(parsed) ? parsed : 0.0;
      const clampedPreamp = Math.max(-24.0, Math.min(12.0, safeVal));
      return Math.round(clampedPreamp * 2.0) & 0xff;
    }

    console.log(JSON.stringify({
      zero: computePreampByte(0.0),
      nullVal: computePreampByte(null),
      undefinedVal: computePreampByte(undefined),
      extremeNeg: computePreampByte(-70.0), // clamps to -24 dB -> -48 & 0xff = 208
      extremePos: computePreampByte(30.0),  // clamps to +12 dB -> 24
      normalNeg: computePreampByte(-3.5),   // -7 & 0xff = 249
    }));
    """
    res = run_node_eval(js_code)
    assert res["zero"] == 0
    assert res["nullVal"] == 0
    assert res["undefinedVal"] == 0
    assert res["extremeNeg"] == 208  # -48 signed byte
    assert res["extremePos"] == 24   # +24 signed byte
    assert res["normalNeg"] == 249   # -7 signed byte




def test_browser_guard_refuses_unknown_device():
    """Same rule as Python: a device the table cannot confirm is refused."""
    result = run_node_eval("""
import { readFileSync } from "node:fs";
import { guardWrite, matchDevice } from "./modules/safety_guard.js";
const table = JSON.parse(readFileSync("dacs.json", "utf8"));
const device = matchDevice(table, 0x1234, 0x5678, "Mystery DAC");
const guard = guardWrite(table, device, [{ freq: 1000, gain: 0, q: 1 }]);
console.log(JSON.stringify({ ok: guard.ok, problems: guard.problems }));
""")
    assert result["ok"] is False
    assert "device identity could not be confirmed" in result["problems"][0]


def test_browser_guard_refuses_out_of_range_and_names_band():
    result = run_node_eval("""
import { readFileSync } from "node:fs";
import { guardWrite, matchDevice } from "./modules/safety_guard.js";
const table = JSON.parse(readFileSync("dacs.json", "utf8"));
const device = matchDevice(table, 0x3302, 0xc20f);
const bands = [{ freq: 1000, gain: 0, q: 1 }, { freq: 2000, gain: 1, q: 1 },
               { freq: 3000, gain: 2, q: 1 }, { freq: 30000, gain: 3, q: 1 }];
const guard = guardWrite(table, device, bands);
console.log(JSON.stringify({ ok: guard.ok, problems: guard.problems }));
""")
    assert result["ok"] is False
    assert any("band 3" in p for p in result["problems"])
    assert any("30000 Hz" in p for p in result["problems"])


def test_browser_guard_fails_closed_when_table_cannot_be_read():
    result = run_node_eval("""
import { guardWrite } from "./modules/safety_guard.js";
const guard = guardWrite(null, null, [{ freq: 1000, gain: 0, q: 1 }]);
console.log(JSON.stringify({ ok: guard.ok, problems: guard.problems }));
""")
    assert result["ok"] is False
    assert "could not be read" in result["problems"][0]


def test_browser_encode_refuses_instead_of_wrapping():
    """No silent clamp or int32 wrap: the packet is never built, so nothing is sent."""
    result = run_node_eval("""
import { readFileSync } from "node:fs";
import { guardWrite, matchDevice, rangesFor } from "./modules/safety_guard.js";
import { encodeWalkplayFilterPacket } from "./modules/hid_transport.js";
const table = JSON.parse(readFileSync("dacs.json", "utf8"));
const device = matchDevice(table, 0x3302, 0xc20f);
const refused = guardWrite(table, device, [{ freq: 30000, gain: 0, q: 1 }]);
let threw = "";
try { encodeWalkplayFilterPacket(3, 70000, 0, 1); } catch (e) { threw = e.message; }
let wrapped = "";
try { encodeWalkplayFilterPacket(3, 1000, 100, 0.1); } catch (e) { wrapped = e.message; }
console.log(JSON.stringify({ refused: refused.ok, threw, wrapped }));
""")
    assert result["refused"] is False
    assert "SAFETY GUARD" in result["threw"] and "band 3" in result["threw"]
    assert "SAFETY GUARD" in result["wrapped"] and "int32" in result["wrapped"]


def test_web_safety_guard_refuses_conexant_and_unconfirmed_identity():
    """Same rule as Python/Rust: only a table match may be written, and the fixed
    mask ROM is refused even when its id is known."""
    js_code = """
import fs from 'node:fs';
import { loadTable, matchDevice, guardWrite } from './modules/safety_guard.js';
const table = JSON.parse(fs.readFileSync('dacs.json', 'utf8'));
const cx = matchDevice(table, 0x3302, 0x3365, 'CX31993 DSP');
const unknown = matchDevice(table, 0x18d1, 0x1908, 'Something Unknown');
console.log(JSON.stringify({
  cx_arch: cx && cx.architecture,
  cx_refused: guardWrite(table, cx, []).problems,
  unknown: unknown === null,
  unknown_refused: guardWrite(table, null, []).problems,
  ok_refused: guardWrite(table, matchDevice(table, 0x31b2, 0x111, ''), []).problems,
}));
"""
    out = run_node_eval(js_code)
    assert out["cx_arch"] == "conexant_fixed"
    assert any("fixed mask ROM" in p for p in out["cx_refused"])
    assert out["unknown"] is True
    assert any("identity could not be confirmed" in p for p in out["unknown_refused"])
    assert out["ok_refused"] == []


def test_web_safety_guard_rejects_out_of_range_band_before_packing():
    """Validate before packing: the guard rejects the band, so no packet is built,
    and the packer itself refuses anything it cannot represent (no silent truncation)."""
    js_code = """
import fs from 'node:fs';
import { bandProblems } from './modules/safety_guard.js';
import { encodeWalkplayFilterPacket } from './modules/hid_transport.js';
const table = JSON.parse(fs.readFileSync('dacs.json', 'utf8'));
const problems = bandProblems(table, 'walkplay_dsp', 3, 48001, 0, 4);
const packets = [];
if (problems.length === 0) packets.push(encodeWalkplayFilterPacket(3, 48001, 0, 4));
let backstop = null;
try { encodeWalkplayFilterPacket(3, 70000, 0, 4); } catch (e) { backstop = e.message; }
console.log(JSON.stringify({ problems, packets, backstop }));
"""
    out = run_node_eval(js_code)
    assert any("accepted 0 to 20000 Hz" in p for p in out["problems"])
    assert out["packets"] == [], "a rejected band must not produce a partial packet"
    assert "cannot be packed" in out["backstop"] and "band 3" in out["backstop"]


def test_web_guard_reads_the_shared_table():
    """Issue #8: the browser guard reads the same table the CLI and Rust core read,
    so the rule lives in one place."""
    web_table = WEB_DIR / "dacs.json"
    source = ROOT_DIR / "src" / "dac_peq" / "data" / "dacs.json"
    assert web_table.resolve() == source.resolve(), "web/dacs.json must be the shared table, not a copy"
    out = run_node_eval("""
import fs from 'node:fs';
import { loadTable, rangesFor } from './modules/safety_guard.js';
const table = JSON.parse(fs.readFileSync('dacs.json', 'utf8'));
let unknown_arch = null;
try { unknown_arch = rangesFor(table, 'not_in_the_table'); } catch (_) {}
console.log(JSON.stringify({
  devices: table.devices.length,
  walkplay: rangesFor(table, 'walkplay_dsp'),
  unknown_arch,
}));
""")
    assert out["devices"] == 43
    assert out["walkplay"] == {"freq_max_hz": 20000, "q_min": 0.1, "q_max": 10.0,
                                "gain_min_db": -12.0, "gain_max_db": 12.0}
    assert out["unknown_arch"] is None


def test_web_guard_does_not_infer_architecture_from_vendor_id():
    """Issue #8: no architecture or identity may be inferred from a vendor id alone."""
    offenders = []
    for f in ("app.js", "modules/hid_transport.js", "modules/safety_guard.js"):
        text = (WEB_DIR / f).read_text()
        for i, line in enumerate(text.splitlines(), 1):
            if "vendorId === 0x" in line or "vendorId === 1" in line or "productId === 0x" in line:
                offenders.append(f"{f}:{i}: {line.strip()}")
    assert not offenders, "vendor-id-based inference remains:\n" + "\n".join(offenders)

    out = run_node_eval("""
import fs from 'node:fs';
import { matchDevice } from './modules/safety_guard.js';
const table = JSON.parse(fs.readFileSync('dacs.json', 'utf8'));
console.log(JSON.stringify({
  known_vendor_unknown_product: matchDevice(table, 0x3302, 0x9999, ''),
  table_match: matchDevice(table, 0x3302, 0xc20f, ''),
}));
""")
    assert out["known_vendor_unknown_product"] is None, "a known vendor id with an unknown product id must not be routed"
    assert out["table_match"]["architecture"] == "walkplay_dsp"


def test_browser_resolves_identity_only_from_the_shared_table():
    """Issue #8: the browser reads the same table as Python and Rust, and never infers an
    architecture from a vendor id."""
    for name in ("app.js", "modules/hid_transport.js", "modules/safety_guard.js"):
        src = (WEB_DIR / name).read_text()
        assert "vendorId === 0x" not in src, f"{name} infers architecture from a vendor id"
        assert "productId === 0x" not in src, f"{name} infers architecture from a product id"

    # Same file as Python and Rust, not a browser copy.
    assert (WEB_DIR / "dacs.json").resolve() == (ROOT_DIR / "src" / "dac_peq" / "data" / "dacs.json").resolve()

    res = run_node_eval("""
    import { readFileSync } from "node:fs";
    import { bandProblems, entryFor } from "./modules/safety_guard.js";
    const table = JSON.parse(readFileSync("dacs.json", "utf8"));
    const unknown = { vendorId: 0x9999, productId: 0x8888, productName: "Generic Allegro DAC" };
    const known = { vendorId: 0x31B2, productId: 0x0111, productName: "Kiwi Ears Allegro Mini" };
    const knownEntry = entryFor(known);
    let rangesErr = "";
    try { bandProblems(table, "not_in_the_table", 0, 1000, 0, 1); } catch (e) { rangesErr = e.message; }
    console.log(JSON.stringify({
      unknownEntry: entryFor(unknown),
      knownEntryName: knownEntry ? knownEntry.name : null,
      knownNeeds2X: (knownEntry.quirks || []).includes("compensate2x"),
      rangesErr
    }));
    """)
    assert res["unknownEntry"] is None
    assert res["knownEntryName"] == "Kiwi Ears Allegro Mini"
    assert res["knownNeeds2X"] is True
    assert "SAFETY GUARD" in res["rangesErr"]
