/**
 * dac-peq-manager Rust WebAssembly Engine Bridge
 * Integrates compiled Rust core (crates/dac-peq-wasm) into the browser Web Flasher.
 */

import { computeCompositeCurve, generateLogFrequencies } from "./biquad_math.js";
import { loadTable } from "./safety_guard.js";
import { formatPipeWireConf, formatEqualizerApo } from "./exporters.js";

let wasmModule = null;
let wasmReady = false;

export const LOG_FREQS = generateLogFrequencies(127, 20.0, 20000.0);

export async function initWasmEngine() {
  if (wasmReady) return true;
  try {
    const wasmImport = await import("../wasm/dac_peq_wasm.js");
    const init = wasmImport.default;
    await init();
    wasmModule = wasmImport;
    wasmReady = true;
    // Rust cannot read a file in the browser, so hand it the same table the JS guard uses.
    wasmImport.set_device_table(JSON.stringify(await loadTable("dacs.json")));
    const version = typeof wasmImport.wasm_version === "function" ? wasmImport.wasm_version() : "0.2.0";
    console.log(`%c[WASM Engine] Rust Core v${version} active`, "color: #10b981; font-weight: bold;");
    return true;
  } catch (err) {
    console.warn("[WASM Engine] Could not load WASM module, falling back to pure JavaScript math:", err);
    wasmModule = null;
    wasmReady = false;
    return false;
  }
}

export function isWasmReady() {
  return wasmReady;
}

export function getWasmEngine() {
  return wasmReady ? wasmModule : null;
}

export function setWasmEngine(module) {
  wasmModule = module;
  wasmReady = Boolean(module);
}

export { wasmModule as wasm };

// Pure JS Fallbacks
export function computeCompositeResponse(bands, freqs, fs = 48000) {
  const normalized = (bands || []).map((b) => ({
    freq: Number(b.freq ?? b.f ?? 1000),
    gain: Number(b.gain ?? b.g ?? 0),
    q: Number(b.q ?? 1.0),
    type: String(b.type || "PK").toUpperCase(),
    enabled: b.enabled !== false,
  })).filter((b) => b.enabled);
  return computeCompositeCurve(normalized, 0.0, freqs, fs);
}

export function generatePipewireConfig(preset, freqs = LOG_FREQS) {
  const bands = Array.isArray(preset) ? preset : (preset?.bands || []);
  return formatPipeWireConf(preset || {}, bands);
}

export function generateApoConfig(preset, freqs = LOG_FREQS) {
  const bands = Array.isArray(preset) ? preset : (preset?.bands || []);
  return formatEqualizerApo(preset || {}, bands);
}

// WASM-accelerated helper functions with graceful fallbacks
export function computeCompositeResponseWasm(bands, freqs, fs = 48000) {
  const mod = getWasmEngine();
  if (mod) {
    try {
      const activeBands = (bands || []).filter((b) => b.enabled !== false);
      const rustBands = activeBands.map((b) => ({
        freq: Number(b.freq ?? b.f ?? 1000),
        gain: Number(b.gain ?? b.g ?? 0),
        q: Number(b.q ?? 1.0),
        type: String(b.type || "PK").toUpperCase(),
        enabled: true,
      }));
      const json = JSON.stringify(rustBands);
      let result;
      if (typeof mod.compute_composite_curve_at_freqs === "function") {
        result = mod.compute_composite_curve_at_freqs(json, 0.0, new Float64Array(freqs), fs);
      } else if (typeof mod.compute_composite_curve === "function") {
        // Handle both (bands_json, freqsArray, fs) and (bands_json, preamp, points, fs)
        if (mod.compute_composite_curve.length === 3) {
          result = mod.compute_composite_curve(json, new Float64Array(freqs), fs);
        } else {
          result = mod.compute_composite_curve(json, 0.0, Array.isArray(freqs) ? freqs.length : 127, fs);
        }
      }
      if (result) {
        const arr = Array.from(result);
        if (arr.length > 0 && !Number.isNaN(arr[0])) {
          return arr;
        }
      }
    } catch (err) {
      console.warn("[WASM Engine] compute_composite_curve error, falling back:", err);
    }
  }
  return computeCompositeResponse(bands, freqs, fs);
}

export function generatePipewireConfigWasm(preset) {
  const mod = getWasmEngine();
  if (mod && typeof mod.generate_pipewire_config === "function") {
    try {
      return mod.generate_pipewire_config(JSON.stringify(preset));
    } catch (err) {
      console.warn("[WASM Engine] generate_pipewire_config error:", err);
    }
  } else if (mod && typeof mod.export_pipewire_conf === "function") {
    try {
      return mod.export_pipewire_conf(JSON.stringify(preset));
    } catch (err) {
      console.warn("[WASM Engine] export_pipewire_conf error:", err);
    }
  }
  return generatePipewireConfig(preset, LOG_FREQS);
}

export function generateApoConfigWasm(preset) {
  const mod = getWasmEngine();
  if (mod && typeof mod.generate_apo_config === "function") {
    try {
      return mod.generate_apo_config(JSON.stringify(preset));
    } catch (err) {
      console.warn("[WASM Engine] generate_apo_config error:", err);
    }
  } else if (mod && typeof mod.export_apo_txt === "function") {
    try {
      return mod.export_apo_txt(JSON.stringify(preset));
    } catch (err) {
      console.warn("[WASM Engine] export_apo_txt error:", err);
    }
  }
  return generateApoConfig(preset, LOG_FREQS);
}
