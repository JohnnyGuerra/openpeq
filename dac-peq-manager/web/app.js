/**
 * dac-peq-manager Web Flasher & Host PEQ Suite
 * Modular UI Controller & Interactive SVG Curve Renderer.
 *
 * Imports DSP math, Host Exporters, WebHID Transport, and AutoEq Client
 * from `./modules/*.js`.
 */

import {
  computeCompositeCurve,
  generateLogFrequencies,
  calculatePeakCompositeGain,
  calculateRecommendedPreamp,
  calculateHeadroomStatus,
  normalizeHeadroom,
  lintAcousticBands,
  decimateBands,
  applyMacroAdjustments,
  smoothCouplerBiquads,
} from "./modules/biquad_math.js";

import { BLOCKED_ARCHITECTURES, entryFor, guardWrite, loadTable, matchDevice, setTable } from "./modules/safety_guard.js";

import {
  formatPipeWireConf,
  formatEqualizerApo,
  formatWaveletGraphicEq,
  formatQudelixJson,
  parseParametricEq,
  encodePresetToUrlParams,
  decodePresetFromUrlParams,
} from "./modules/exporters.js";

import {
  KTMICRO_FILTERS,
  isMoondropFreeDsp,
  isWalkplayDsp,
  getFlashStats,
  recordFlashCommit,
  detectFirmwareQuirks,
  encodeKtMicroBandPackets,
  encodeMoondropReport,
  encodeWalkplayFilterPacket,
  encodeWalkplayGlobalGain,
  getWalkplayCommitSequence,
  waitForUsbReenumeration,
  readKtMicroPeq,
  readMoondropReport,
  readWalkplayPeq,
  sendKtMicroFilter,
  sendKtMicroClearFlash,
  getStockBackup,
  saveStockBackup,
  hasStockBackup,
} from "./modules/hid_transport.js";

import {
  loadAutoEqDatabase,
  searchAutoEqEntries,
  fetchAndParseAutoEqPreset,
} from "./modules/autoeq_client.js";

import {
  initWasmEngine,
  isWasmReady,
  getWasmEngine,
  computeCompositeResponseWasm,
  wasm,
} from "./modules/wasm_engine.js";

export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Built-in Presets Catalog ──────────────────────────────────────────────────
export const PRESETS = {
  bmasterx6: {
    name: "BASN BmasterX 6",
    slug: "bmasterx6",
    description: "1DD + 3BA + 2PZT - Tighten 8mm mid-bass warmth, pull vocals forward, tame 9.8kHz ceramic peak.",
    slot_id: 3,
    preamp: -2.5,
    bands: [
      { type: "LSQ", freq: 50.0, gain: 2.2, q: 0.71 },
      { type: "PK", freq: 195.0, gain: -2.4, q: 1.10 },
      { type: "PK", freq: 2200.0, gain: 1.6, q: 1.30 },
      { type: "PK", freq: 4500.0, gain: -1.8, q: 2.50 },
      { type: "PK", freq: 9800.0, gain: -3.2, q: 3.00 },
    ],
  },
  "ew300-silver": {
    name: "SIMGOT EW300 (Silver)",
    slug: "ew300_silver",
    description: "Silver Steel Nozzle (Simgot-Golden2023) - Add sub-bass punch and smooth upper-mid/PZT energy.",
    preamp: -2.8,
    bands: [
      { type: "LSQ", freq: 55.0, gain: 2.5, q: 0.71 },
      { type: "PK", freq: 220.0, gain: -1.2, q: 1.40 },
      { type: "PK", freq: 2800.0, gain: -1.8, q: 2.00 },
      { type: "PK", freq: 5200.0, gain: -2.2, q: 2.80 },
      { type: "HSQ", freq: 10500.0, gain: -1.5, q: 0.71 },
    ],
  },
  "ew300-gold": {
    name: "SIMGOT EW300 (Gold)",
    slug: "ew300_gold",
    description: "Gold Copper Nozzle (H-2019) - De-mud lower mids and restore top-end air and micro-detail.",
    preamp: -2.2,
    bands: [
      { type: "LSQ", freq: 45.0, gain: 1.5, q: 0.71 },
      { type: "PK", freq: 180.0, gain: -2.2, q: 1.20 },
      { type: "PK", freq: 2000.0, gain: 1.8, q: 1.40 },
      { type: "PK", freq: 4200.0, gain: -1.0, q: 2.20 },
      { type: "HSQ", freq: 9500.0, gain: 2.0, q: 0.71 },
    ],
  },
  flat: {
    name: "Flat Bypass (0 dB)",
    slug: "flat",
    description: "Hardware bypass / flat reset - Sets all bands to 0 dB gain across logarithmic centers.",
    preamp: 0.0,
    bands: [
      { type: "LSQ", freq: 60.0, gain: 0.0, q: 0.71 },
      { type: "PK", freq: 250.0, gain: 0.0, q: 1.00 },
      { type: "PK", freq: 1000.0, gain: 0.0, q: 1.00 },
      { type: "PK", freq: 3500.0, gain: 0.0, q: 1.00 },
      { type: "HSQ", freq: 10000.0, gain: 0.0, q: 0.71 },
    ],
  },
  "jm-1": {
    name: "JM-1 Modern Target (Jaytiss)",
    slug: "jm_1",
    description: "Modern psychoacoustic target matching real human ear canal impedance. Warm sub-bass punch with a softened 3kHz pinna.",
    preamp: -3.5,
    bands: [
      { type: "LSQ", freq: 65.0, gain: 3.0, q: 0.71 },
      { type: "PK", freq: 220.0, gain: -1.2, q: 1.20 },
      { type: "PK", freq: 2700.0, gain: 1.8, q: 1.30 },
      { type: "PK", freq: 5200.0, gain: -1.5, q: 2.20 },
      { type: "HSQ", freq: 10500.0, gain: 1.0, q: 0.71 },
    ],
  },
  "ief-neutral": {
    name: "IEF Neutral Target (Crinacle)",
    slug: "ief_neutral",
    description: "Crinacle studio reference target curve. Linear bass with a non-fatiguing 2.8kHz ear gain peak.",
    preamp: -1.5,
    bands: [
      { type: "LSQ", freq: 80.0, gain: 0.0, q: 0.71 },
      { type: "PK", freq: 250.0, gain: 0.0, q: 1.00 },
      { type: "PK", freq: 2800.0, gain: 1.5, q: 1.50 },
      { type: "PK", freq: 5000.0, gain: -1.2, q: 2.00 },
      { type: "HSQ", freq: 10000.0, gain: 0.0, q: 0.71 },
    ],
  },
  "harman-2019v2": {
    name: "Harman In-Ear Target (2019 v2)",
    slug: "harman_in_ear_2019v2",
    description: "Samsung / Harman reference target by Dr. Sean Olive. Prominent +9dB sub-bass shelf and forward +12dB ear gain.",
    preamp: -3.5,
    bands: [
      { type: "LSQ", freq: 105.0, gain: 4.5, q: 0.71 },
      { type: "PK", freq: 200.0, gain: -1.5, q: 1.10 },
      { type: "PK", freq: 2850.0, gain: 2.5, q: 1.40 },
      { type: "PK", freq: 4800.0, gain: -1.0, q: 2.20 },
      { type: "HSQ", freq: 10000.0, gain: 0.0, q: 0.71 },
    ],
  },
  "bk-5128-df": {
    name: "B&K 5128 Diffuse Field (-10 dB Tilt)",
    slug: "bk_5128_df",
    description: "Brüel & Kjær 5128 HRTF diffuse field target with a -1 dB/oct warm tilt. Preserves natural lower-midrange body with airy 11kHz extension.",
    preamp: -2.2,
    bands: [
      { type: "LSQ", freq: 85.0, gain: 2.0, q: 0.71 },
      { type: "PK", freq: 280.0, gain: 0.6, q: 1.10 },
      { type: "PK", freq: 2650.0, gain: 1.4, q: 1.35 },
      { type: "PK", freq: 4600.0, gain: -1.6, q: 2.10 },
      { type: "HSQ", freq: 11000.0, gain: 0.8, q: 0.71 },
    ],
  },
  "oratory-usound": {
    name: "Oratory1990 Optimum HiFi (USound)",
    slug: "oratory_usound",
    description: "Oratory1990 / USound audiophile preference target. Rich bass warmth, lush vocal density without Harman mid-bass scoop, and smooth 2.75kHz ear gain.",
    preamp: -3.2,
    bands: [
      { type: "LSQ", freq: 100.0, gain: 3.2, q: 0.71 },
      { type: "PK", freq: 240.0, gain: 0.8, q: 1.15 },
      { type: "PK", freq: 2750.0, gain: 1.2, q: 1.40 },
      { type: "PK", freq: 5400.0, gain: -1.4, q: 2.00 },
      { type: "HSQ", freq: 10000.0, gain: -0.8, q: 0.71 },
    ],
  },
  "iso-loudness": {
    name: "Late-Night Loudness (ISO 226 Contour)",
    slug: "iso_loudness",
    description: "ISO 226 / Fletcher-Munson equal-loudness contour for low-SPL listening (<65 dB). Restores perceived sub-bass weight and upper-treble air at quiet volumes.",
    preamp: -3.5,
    bands: [
      { type: "LSQ", freq: 60.0, gain: 3.5, q: 0.71 },
      { type: "PK", freq: 210.0, gain: -0.8, q: 1.25 },
      { type: "PK", freq: 3200.0, gain: -1.6, q: 1.60 },
      { type: "PK", freq: 6200.0, gain: -0.6, q: 2.00 },
      { type: "HSQ", freq: 10500.0, gain: 2.2, q: 0.71 },
    ],
  },
};

// ── State ─────────────────────────────────────────────────────────────────────
let currentPreset = JSON.parse(JSON.stringify(PRESETS.bmasterx6));
currentPreset.fullBands = PRESETS.bmasterx6.bands.map((b) => ({ ...b }));
let referenceTargetCurve = null;
let showTargetOverlay = true;
let connectedHidDevice = null;
let connectedDeviceProfile = null;
let isDemoMode = false;
let isConexantBlocked = false;
let guardTable = null; // the single source of truth; null until it can be read
let isRebootingPostCommit = false;
let autoApplyTimer = null;
let activeDragIndex = null;
let activeHardwareBands = 5; // 5 for KTMicro KT02H20, 9 for Moondrop FreeDSP
let macroState = { bass: 0.0, earGain: 0.0, treble: 0.0 };
let macroBaselineBands = null;

function resetMacroControls(newBaselineBands = null) {
  macroState = { bass: 0.0, earGain: 0.0, treble: 0.0 };
  macroBaselineBands = Array.isArray(newBaselineBands)
    ? newBaselineBands.map((b) => ({ ...b }))
    : (currentPreset && Array.isArray(currentPreset.bands) ? currentPreset.bands.map((b) => ({ ...b })) : null);
  const sBass = document.getElementById("sliderMacroBass");
  const sEar = document.getElementById("sliderMacroEar");
  const sTreb = document.getElementById("sliderMacroTreble");
  const lBass = document.getElementById("lblMacroBass");
  const lEar = document.getElementById("lblMacroEar");
  const lTreb = document.getElementById("lblMacroTreble");
  if (sBass) sBass.value = "0";
  if (sEar) sEar.value = "0";
  if (sTreb) sTreb.value = "0";
  if (lBass) lBass.textContent = "0.0 dB";
  if (lEar) lEar.textContent = "0.0 dB";
  if (lTreb) lTreb.textContent = "0.0 dB";
}

function updateEqCapsBadge(dev = null) {
  const badge = document.getElementById("eqCapsBadge");
  const activeDev = dev || connectedHidDevice;
  const activeEntry = entryFor(activeDev);
  const isJa11 = Boolean(activeEntry && (activeEntry.quirks || []).includes("fiio_dac_filter"));
  const isKiwiMini = Boolean(activeEntry && (activeEntry.quirks || []).includes("noPregain")) && activeHardwareBands === 5;
  const isWalkplay = activeHardwareBands === 8 || activeHardwareBands === 10 || (activeDev && isWalkplayDsp(activeDev));
  const isMoondrop = activeHardwareBands === 9 || (activeDev && isMoondropFreeDsp(activeDev));

  if (badge) {
    if (isWalkplay) {
      badge.textContent = `${activeHardwareBands} Bands (WalkPlay) | Step 0.1 dB | Preamp Supported`;
    } else if (isMoondrop) {
      badge.textContent = `9 Bands (Moondrop DSP) | Step 0.1 dB | Preamp Supported`;
    } else if (isJa11) {
      badge.textContent = `5 Bands (JA11 KT02H20) | Step 0.1 dB | Reg 0x11/0x66 Supported`;
    } else {
      badge.textContent = `5 Bands (KT02H20 Safe Mode) | Step 0.1 dB | Reg 0x11/0x66 Guarded`;
    }
  }

  // Register 0x11 (DAC Filter) & 0x66 (Preamp) Visual Guardrails
  const selDacFilter = document.getElementById("selDacFilter");
  const lblDacGuard = document.getElementById("lblDacFilterGuard");
  const lblPreampGuard = document.getElementById("lblPreampGuard");

  if (selDacFilter && lblDacGuard) {
    if (isJa11) {
      selDacFilter.disabled = false;
      lblDacGuard.textContent = "JA11 Active";
      lblDacGuard.className = "guard-pill active";
    } else if (activeDev && !isDemoMode) {
      selDacFilter.disabled = true;
      lblDacGuard.textContent = "Guarded (0x11 Blocked)";
      lblDacGuard.className = "guard-pill guarded";
    } else {
      selDacFilter.disabled = false;
      lblDacGuard.textContent = "JA11 Only";
      lblDacGuard.className = "guard-pill";
    }
  }

  if (lblPreampGuard) {
    if (isKiwiMini && !isDemoMode) {
      lblPreampGuard.style.display = "inline-flex";
      lblPreampGuard.textContent = "Unity on 0x31B2 (Host Only)";
      lblPreampGuard.className = "guard-pill guarded";
    } else {
      lblPreampGuard.style.display = "none";
    }
  }
}

// ── SVG Curve Renderer ────────────────────────────────────────────────────────
const FREQ_TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
const DB_TICKS = [6, 3, 0, -3, -6, -9, -12];
const F_MIN = 20.0, F_MAX = 20000.0;
const DB_TOP = 8.0, DB_BOTTOM = -14.0;

function xForFreq(f, width) {
  return ((Math.log10(f) - Math.log10(F_MIN)) / (Math.log10(F_MAX) - Math.log10(F_MIN))) * width;
}

function freqForX(x, width) {
  const norm = Math.max(0, Math.min(1, x / width));
  return Math.pow(10.0, Math.log10(F_MIN) + norm * (Math.log10(F_MAX) - Math.log10(F_MIN)));
}

function yForDb(db, height) {
  return ((DB_TOP - db) / (DB_TOP - DB_BOTTOM)) * height;
}

function dbForY(y, height) {
  const norm = Math.max(0, Math.min(1, y / height));
  return DB_TOP - norm * (DB_TOP - DB_BOTTOM);
}

function renderCurve() {
  const svg = document.getElementById("eqSvg");
  if (!svg) return;
  const width = svg.clientWidth || 800;
  const height = svg.clientHeight || 280;

  svg.innerHTML = "";

  // 1. Grid Lines (Horizontal dB)
  DB_TICKS.forEach((db) => {
    const y = yForDb(db, height);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", 0);
    line.setAttribute("x2", width);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("class", db === 0 ? "zero-line" : "grid-line");
    svg.appendChild(line);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", 8);
    text.setAttribute("y", y - 4);
    text.setAttribute("class", "axis-text");
    text.textContent = (db > 0 ? "+" : "") + db + " dB";
    svg.appendChild(text);
  });

  // 2. Grid Lines (Vertical Frequency)
  const isCompactGraph = width < 460;
  const COMPACT_OMIT_LABELS = new Set([50, 200, 2000, 5000]);

  FREQ_TICKS.forEach((f) => {
    const x = xForFreq(f, width);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x);
    line.setAttribute("x2", x);
    line.setAttribute("y1", 0);
    line.setAttribute("y2", height);
    line.setAttribute("class", "grid-line");
    svg.appendChild(line);

    if (isCompactGraph && COMPACT_OMIT_LABELS.has(f)) return;

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", x);
    text.setAttribute("y", height - 8);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("class", "axis-text");
    text.textContent = f >= 1000 ? f / 1000 + "k" : f;
    svg.appendChild(text);
  });

  // 3. Composite EQ Curve Path & Reference Target Overlay
  const frequencies = generateLogFrequencies(220);
  const baseResponses = computeCompositeResponseWasm(currentPreset.bands, frequencies);
  const responses = baseResponses.map((v) => v + Number(currentPreset.preamp || 0.0));

  let rmsDiff = 0.0;
  let maxDelta = 0.0;
  let maxDeltaFreq = 1000.0;
  const selTolerance = document.getElementById("selPreferenceTolerance");
  const preferenceToleranceDb = selTolerance ? parseFloat(selTolerance.value) || 2.0 : 2.0;

  if (referenceTargetCurve && referenceTargetCurve.bands && referenceTargetCurve.bands.length > 0) {
    const refPreamp = referenceTargetCurve.preamp !== undefined ? referenceTargetCurve.preamp : currentPreset.preamp;
    const baseRefResponses = computeCompositeResponseWasm(referenceTargetCurve.bands, frequencies);
    const refResponses = baseRefResponses.map((v) => v + Number(refPreamp || 0.0));

    let sumSq = 0.0;
    let inBoundsCount = 0;
    for (let i = 0; i < frequencies.length; i++) {
      const delta = responses[i] - refResponses[i];
      sumSq += delta * delta;
      if (Math.abs(delta) <= preferenceToleranceDb) {
        inBoundsCount++;
      }
      if (Math.abs(delta) > Math.abs(maxDelta)) {
        maxDelta = delta;
        maxDeltaFreq = frequencies[i];
      }
    }
    rmsDiff = Math.sqrt(sumSq / frequencies.length);
    const inBoundsPct = Math.round((inBoundsCount / frequencies.length) * 100);

    if (showTargetOverlay) {
      // 1. Preference Tolerance Envelope Shading (Polygon)
      let envPathD = "";
      frequencies.forEach((f, i) => {
        const x = xForFreq(f, width);
        const yTop = yForDb(refResponses[i] + preferenceToleranceDb, height);
        envPathD += (i === 0 ? "M " : "L ") + x.toFixed(1) + " " + yTop.toFixed(1) + " ";
      });
      for (let i = frequencies.length - 1; i >= 0; i--) {
        const x = xForFreq(frequencies[i], width);
        const yBot = yForDb(refResponses[i] - preferenceToleranceDb, height);
        envPathD += "L " + x.toFixed(1) + " " + yBot.toFixed(1) + " ";
      }
      envPathD += "Z";

      const envCurvePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      envCurvePath.setAttribute("d", envPathD);
      envCurvePath.setAttribute("class", "preference-envelope-path");
      svg.appendChild(envCurvePath);

      // 2.Target Difference Fill Shading (modernGraphTool / silicagel.squig.link style)
      let diffFillD = "";
      frequencies.forEach((f, i) => {
        const x = xForFreq(f, width);
        const yAct = yForDb(responses[i], height);
        diffFillD += (i === 0 ? "M " : "L ") + x.toFixed(1) + " " + yAct.toFixed(1) + " ";
      });
      for (let i = frequencies.length - 1; i >= 0; i--) {
        const x = xForFreq(frequencies[i], width);
        const yRef = yForDb(refResponses[i], height);
        diffFillD += "L " + x.toFixed(1) + " " + yRef.toFixed(1) + " ";
      }
      diffFillD += "Z";

      const diffFillPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      diffFillPath.setAttribute("d", diffFillD);
      diffFillPath.setAttribute("class", "curve-diff-fill");
      svg.appendChild(diffFillPath);

      // 3. Reference Target Line
      let refPathD = "";
      frequencies.forEach((f, i) => {
        const x = xForFreq(f, width);
        const y = yForDb(refResponses[i], height);
        refPathD += (i === 0 ? "M " : "L ") + x.toFixed(1) + " " + y.toFixed(1) + " ";
      });

      const refCurvePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      refCurvePath.setAttribute("d", refPathD);
      refCurvePath.setAttribute("class", "reference-curve-path");
      svg.appendChild(refCurvePath);
    }
  }

  // Update Target Legend Header
  const targetLegend = document.getElementById("targetLegend");
  const lblTargetName = document.getElementById("lblTargetName");
  const lblTargetRms = document.getElementById("lblTargetRms");
  const lblToggleTarget = document.getElementById("lblToggleTarget");
  const chkShowTarget = document.getElementById("chkShowTarget");

  if (targetLegend && lblTargetName && lblTargetRms && lblToggleTarget) {
    if (referenceTargetCurve) {
      targetLegend.style.display = "inline-flex";
      lblToggleTarget.style.display = "inline-flex";
      lblTargetName.textContent = referenceTargetCurve.name || "Target Reference";
      if (showTargetOverlay) {
        const freqText = maxDeltaFreq >= 1000 ? (maxDeltaFreq / 1000).toFixed(1) + " kHz" : Math.round(maxDeltaFreq) + " Hz";
        lblTargetRms.textContent = `(RMS: ±${rmsDiff.toFixed(1)} dB | Envelope ±${preferenceToleranceDb.toFixed(1)} dB | Peak Δ: ${maxDelta > 0 ? "+" : ""}${maxDelta.toFixed(1)} dB @ ${freqText})`;
      } else {
        lblTargetRms.textContent = "(Overlay Hidden)";
      }
      if (chkShowTarget) chkShowTarget.checked = showTargetOverlay;
    } else {
      targetLegend.style.display = "none";
      lblToggleTarget.style.display = "none";
    }
  }

  // Headroom Clipping Guard Check
  const btnNormalize = document.getElementById("btnNormalizeHeadroom");
  const headroom = calculateHeadroomStatus(currentPreset.bands);
  if (btnNormalize) {
    if (headroom.is_clipping_risk) {
      btnNormalize.style.display = "inline-flex";
      btnNormalize.textContent = `⚠️ Peak +${headroom.peak_db.toFixed(1)} dB (Normalize)`;
    } else {
      btnNormalize.style.display = "none";
    }
  }

  // Active Hardware Composite EQ Curve Path
  let pathD = "";
  frequencies.forEach((f, i) => {
    const x = xForFreq(f, width);
    const y = yForDb(responses[i], height);
    pathD += (i === 0 ? "M " : "L ") + x.toFixed(1) + " " + y.toFixed(1) + " ";
  });

  const curvePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  curvePath.setAttribute("d", pathD);
  curvePath.setAttribute("class", "curve-path");
  svg.appendChild(curvePath);

  // 3b. Active Tone / Sweep Playhead Vertical Line
  const activeToneFreq = parseFloat(document.getElementById("sliderToneFreq")?.value || "7000");
  const playheadLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  const playheadX = xForFreq(activeToneFreq, width);
  playheadLine.setAttribute("id", "svgTonePlayhead");
  playheadLine.setAttribute("x1", playheadX);
  playheadLine.setAttribute("x2", playheadX);
  playheadLine.setAttribute("y1", 0);
  playheadLine.setAttribute("y2", height);
  playheadLine.setAttribute("class", "tone-playhead-line");
  playheadLine.style.display = isToneActive ? "block" : "none";
  svg.appendChild(playheadLine);

  // 4. Band Control Nodes
  const prevFocusedBand = document.activeElement?.closest?.("g[data-index]")?.getAttribute("data-index");

  currentPreset.bands.forEach((b, i) => {
    const x = xForFreq(b.freq, width);
    const y = yForDb(b.gain + currentPreset.preamp, height);

    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("data-index", i);
    group.setAttribute("tabindex", "0");
    group.setAttribute("role", "slider");
    group.setAttribute("aria-label", `Band ${i + 1} (${b.type || "PK"} at ${Math.round(b.freq)} Hz)`);
    group.setAttribute("aria-valuemin", "-12");
    group.setAttribute("aria-valuemax", "12");
    group.setAttribute("aria-valuenow", String(b.gain));
    group.setAttribute("aria-valuetext", `${Math.round(b.freq)} Hz, ${b.gain > 0 ? "+" : ""}${b.gain.toFixed(1)} dB`);
    group.setAttribute("class", "band-node-group");

    const hitCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    hitCircle.setAttribute("cx", x);
    hitCircle.setAttribute("cy", y);
    hitCircle.setAttribute("r", 16);
    hitCircle.setAttribute("fill", "transparent");
    hitCircle.setAttribute("stroke", "none");

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", width < 480 ? 7.5 : 6);
    circle.setAttribute("fill", b.enabled === false ? "var(--bg-tertiary, #475569)" : "var(--accent-cyan)");
    circle.setAttribute("stroke", b.enabled === false ? "#94a3b8" : "#ffffff");
    circle.setAttribute("stroke-width", 2);
    if (b.enabled === false) {
      circle.setAttribute("opacity", "0.45");
      circle.setAttribute("stroke-dasharray", "2,2");
    }
    circle.setAttribute("class", "band-marker");

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", x);
    text.setAttribute("y", y - (width < 480 ? 11 : 10));
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "var(--text-primary)");
    text.setAttribute("font-size", "11px");
    text.setAttribute("font-weight", "bold");
    if (b.enabled === false) {
      text.setAttribute("opacity", "0.45");
    }
    text.textContent = i + 1;

    group.appendChild(hitCircle);
    group.appendChild(circle);
    group.appendChild(text);
    svg.appendChild(group);

    group.addEventListener("mousedown", (e) => startDrag(e, i));
    group.addEventListener("touchstart", (e) => startDragTouch(e, i), { passive: false });
    group.addEventListener("keydown", (e) => {
      const gainStep = e.shiftKey ? 1.0 : 0.2;
      const freqMultiplier = e.shiftKey ? 1.05 : 1.015;
      let handled = true;
      if (e.key === "ArrowUp") {
        currentPreset.bands[i].gain = Math.max(-12, Math.min(12, parseFloat((currentPreset.bands[i].gain + gainStep).toFixed(1))));
      } else if (e.key === "ArrowDown") {
        currentPreset.bands[i].gain = Math.max(-12, Math.min(12, parseFloat((currentPreset.bands[i].gain - gainStep).toFixed(1))));
      } else if (e.key === "ArrowRight") {
        const nextF = Math.max(currentPreset.bands[i].freq + 1, Math.round(currentPreset.bands[i].freq * freqMultiplier));
        currentPreset.bands[i].freq = Math.max(20, Math.min(20000, nextF));
      } else if (e.key === "ArrowLeft") {
        const prevF = Math.min(currentPreset.bands[i].freq - 1, Math.round(currentPreset.bands[i].freq / freqMultiplier));
        currentPreset.bands[i].freq = Math.max(20, Math.min(20000, prevF));
      } else {
        handled = false;
      }
      if (handled) {
        e.preventDefault();
        syncBandControls(i);
        renderCurve();
        triggerAutoApply();
      }
    });
  });

  if (prevFocusedBand !== null && prevFocusedBand !== undefined) {
    const restoredGroup = svg.querySelector(`g[data-index="${prevFocusedBand}"]`);
    if (restoredGroup) restoredGroup.focus();
  }

  updateStats();
  updateWebAudioFilters();
}

let dragRafId = null;

export function scheduleDragRender(index) {
  if (dragRafId !== null) return;
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (cb) => setTimeout(cb, 16);
  dragRafId = raf(() => {
    dragRafId = null;
    syncBandControls(index);
    renderCurve();
    triggerAutoApply();
  });
}

export function flushDragRender() {
  if (dragRafId !== null) {
    const caf = typeof cancelAnimationFrame === "function" ? cancelAnimationFrame : clearTimeout;
    caf(dragRafId);
    dragRafId = null;
  }
  if (activeDragIndex !== null) {
    syncBandControls(activeDragIndex);
    renderCurve();
    triggerAutoApply();
  }
}

function startDrag(e, index) {
  e.preventDefault();
  activeDragIndex = index;
  window.addEventListener("mousemove", onDragMove);
  window.addEventListener("mouseup", onDragEnd);
}

function startDragTouch(e, index) {
  e.preventDefault();
  activeDragIndex = index;
  window.addEventListener("touchmove", onDragTouchMove, { passive: false });
  window.addEventListener("touchend", onDragTouchEnd);
}

export function onDragMove(e) {
  if (activeDragIndex === null) return;
  const svg = document.getElementById("eqSvg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;

  const mouseX = Math.max(0, Math.min(width, e.clientX - rect.left));
  const mouseY = Math.max(0, Math.min(height, e.clientY - rect.top));

  const newFreq = Math.round(freqForX(mouseX, width));
  const newGain = parseFloat((dbForY(mouseY, height) - currentPreset.preamp).toFixed(1));

  currentPreset.bands[activeDragIndex].freq = Math.max(20, Math.min(20000, newFreq));
  currentPreset.bands[activeDragIndex].gain = Math.max(-12, Math.min(12, newGain));

  scheduleDragRender(activeDragIndex);
}

export function onDragTouchMove(e) {
  if (activeDragIndex === null || !e.touches[0]) return;
  e.preventDefault();
  const touch = e.touches[0];
  const svg = document.getElementById("eqSvg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;

  const touchX = Math.max(0, Math.min(width, touch.clientX - rect.left));
  const touchY = Math.max(0, Math.min(height, touch.clientY - rect.top));

  const newFreq = Math.round(freqForX(touchX, width));
  const newGain = parseFloat((dbForY(touchY, height) - currentPreset.preamp).toFixed(1));

  currentPreset.bands[activeDragIndex].freq = Math.max(20, Math.min(20000, newFreq));
  currentPreset.bands[activeDragIndex].gain = Math.max(-12, Math.min(12, newGain));

  scheduleDragRender(activeDragIndex);
}

export function onDragEnd() {
  flushDragRender();
  activeDragIndex = null;
  window.removeEventListener("mousemove", onDragMove);
  window.removeEventListener("mouseup", onDragEnd);
}

export function onDragTouchEnd() {
  flushDragRender();
  activeDragIndex = null;
  window.removeEventListener("touchmove", onDragTouchMove);
  window.removeEventListener("touchend", onDragTouchEnd);
}

// ── Flash Wear Levels (shared by the badge and the NVRAM confirm dialog) ──────
const WEAR_HIGH_TOTAL = 50;
const WEAR_HIGH_24H = 10;
const WEAR_MODERATE_24H = 5;

function wearLevel(stats) {
  const writes24h = stats.timestamps.filter((t) => t > Date.now() - 24 * 3600 * 1000).length;
  if (stats.total >= WEAR_HIGH_TOTAL || writes24h >= WEAR_HIGH_24H) return { level: "high", writes24h };
  if (writes24h >= WEAR_MODERATE_24H) return { level: "moderate", writes24h };
  return { level: "low", writes24h };
}

// ── Flash Counter UI Badge ────────────────────────────────────────────────────
function updateFlashCounterBadge(dev) {
  const badge = document.getElementById("nvramWearBadge") || document.getElementById("flashCounterBadge");
  const lbl = document.getElementById("lblFlashCount");
  if (!badge || !lbl) return;

  if (!dev && !isDemoMode) {
    badge.style.display = "none";
    return;
  }

  const stats = getFlashStats(dev);
  const wear = wearLevel(stats);
  const writes24h = wear.writes24h;

  lbl.textContent = stats.total;
  badge.style.display = "inline-flex";

  const wearDisclaimer = "Local browser estimated write counter; not read from hardware telemetry";
  if (wear.level === "high") {
    lbl.style.color = "var(--accent-red)";
    badge.style.borderColor = "var(--accent-red)";
    badge.title = `⚠️ HIGH NVRAM FLASH WEAR! ${writes24h} writes in last 24h, ${stats.total} total writes. EEPROM wear limit approaching. (${wearDisclaimer})`;
  } else if (wear.level === "moderate") {
    lbl.style.color = "var(--accent-yellow)";
    badge.style.borderColor = "var(--accent-yellow)";
    badge.title = `Moderate flash wear: ${writes24h} writes in last 24h, ${stats.total} total writes. (${wearDisclaimer})`;
  } else {
    lbl.style.color = "var(--accent-green)";
    badge.style.borderColor = "var(--border-color)";
    badge.title = `NVRAM writes: ${stats.total} total (${writes24h} in last 24h). (${wearDisclaimer})`;
  }
}

// ── WebHID Hardware Lifecycle ─────────────────────────────────────────────────
function setHardwareBandArchitecture(bandCount) {
  const count = parseInt(bandCount, 10);
  activeHardwareBands = [5, 8, 9, 10].includes(count) ? count : 5;
  const selHwBands = document.getElementById("selHardwareBandCount");
  if (selHwBands) selHwBands.value = String(activeHardwareBands);
  const lblTitle = document.getElementById("lblMatrixTitle");
  if (lblTitle) {
    lblTitle.textContent = `${activeHardwareBands}-Band Biquad Filter Matrix`;
  }

  if (!currentPreset.fullBands || currentPreset.fullBands.length === 0) {
    currentPreset.fullBands = currentPreset.bands.map((b) => ({ ...b }));
  }

  currentPreset.bands = decimateBands(currentPreset.fullBands, activeHardwareBands);
  resetMacroControls(currentPreset.bands);
  updateEqCapsBadge();
  buildControlsUI();
  renderCurve();
}

export function setConnectedDevice(dev, profile = null) {
  connectedHidDevice = dev;
  connectedDeviceProfile = profile;
}

export function getConnectedDevice() {
  return connectedHidDevice;
}

export function getConnectedDeviceProfile() {
  return connectedDeviceProfile;
}

export async function initializeDevice(dev, isSilent = false) {
  try {
    if (!dev.opened) {
      await dev.open();
    }
    connectedHidDevice = dev;

    const vidHex = "0x" + dev.vendorId.toString(16).toUpperCase().padStart(4, "0");
    const pidHex = "0x" + dev.productId.toString(16).toUpperCase().padStart(4, "0");
    const prodName = dev.productName || "USB Audio DSP";

    const dacMatch = findDacInDatabase(dev.vendorId, dev.productId, prodName);
    const dacDisplayName = dacMatch ? `${dacMatch.name} (${dacMatch.chipset})` : `${prodName} (${vidHex}:${pidHex})`;
    connectedDeviceProfile = dacMatch
      ? { ...dacMatch, arch: dacMatch.architecture || "ktmicro" }
      : { arch: isWalkplayDsp(dev) ? "walkplay" : (isMoondropFreeDsp(dev) ? "moondrop" : "ktmicro") };

    updateFlashCounterBadge(dev);

    // Switch hardware band architecture
    if (isWalkplayDsp(dev) || (dacMatch && dacMatch.architecture === "walkplay_dsp")) {
      const hwBands = (dacMatch && dacMatch.hardware_bands) ? dacMatch.hardware_bands : 8;
      setHardwareBandArchitecture(hwBands);
    } else if (isMoondropFreeDsp(dev) || (dacMatch && dacMatch.architecture === "moondrop_dsp")) {
      setHardwareBandArchitecture(9);
    } else if (activeHardwareBands !== 5) {
      setHardwareBandArchitecture(5);
    }

    const quirks = detectFirmwareQuirks(dev);
    const chkCompensate2X = document.getElementById("chkCompensate2X");
    if (chkCompensate2X) {
      chkCompensate2X.checked = quirks.requiresCompensate2X;
    }

    // Conexant Safety Check
    const isFixedMask = Boolean(
      (dacMatch && BLOCKED_ARCHITECTURES.has(dacMatch.architecture)) ||
      (dacMatch && dacMatch.dac_type === "fixed_mask_rom") ||
      prodName.toLowerCase().includes("cx31993") ||
      prodName.toLowerCase().includes("conexant")
    );
    if (isFixedMask) {
      isConexantBlocked = true;
      updateDeviceBadge("blocked", `${dacDisplayName} - Fixed Mask ROM`);
      document.getElementById("safetyAlert").classList.add("visible");
      document.getElementById("btnApply").disabled = true;
      document.getElementById("btnReadDac").disabled = true;
      document.getElementById("btnFlash").disabled = true;
      if (!isSilent) {
        showToast(`${dacMatch ? dacMatch.name : "Conexant CX31993"}: Hardware flashing blocked for safety.`);
      }
      return;
    }

    isConexantBlocked = false;
    document.getElementById("safetyAlert").classList.remove("visible");
    document.getElementById("btnApply").disabled = false;
    document.getElementById("btnReadDac").disabled = false;
    document.getElementById("btnFlash").disabled = false;
    updateDeviceBadge("connected", `${dacDisplayName} - Ready`);
    updateEqCapsBadge(dev);

    const slotId = parseInt(document.getElementById("selHardwareSlot")?.value || "3", 10);
    const btnRestore = document.getElementById("btnRestoreStock");
    if (btnRestore) {
      btnRestore.style.display = hasStockBackup(dev, slotId) ? "inline-flex" : "none";
    }

    if (!isSilent) {
      showToast(`Connected to ${dacMatch ? dacMatch.name : prodName}! (${quirks.reason})`);
    }
  } catch (err) {
    console.error("Device init error:", err);
    if (!isSilent) {
      showToast(`Device error: ${err.message}`);
    }
  }
}

function handleDeviceDisconnect(reason = "DAC disconnected.") {
  if (isRebootingPostCommit) {
    console.log("Microcontroller rebooting after NVRAM commit, awaiting re-enumeration...");
    showToast("NVRAM commit in progress. Microcontroller restarting...");
    return;
  }
  connectedHidDevice = null;
  connectedDeviceProfile = null;
  updateFlashCounterBadge(null);
  updateEqCapsBadge(null);
  const btnRestore = document.getElementById("btnRestoreStock");
  if (btnRestore) btnRestore.style.display = "none";
  if (!isDemoMode) {
    updateDeviceBadge("disconnected", "No DAC Connected");
    document.getElementById("safetyAlert").classList.remove("visible");
    document.getElementById("btnApply").disabled = true;
    document.getElementById("btnReadDac").disabled = true;
    document.getElementById("btnFlash").disabled = true;
    showToast(reason);
  }
}

async function connectDac() {
  if (!navigator.hid) {
    showToast("WebHID API is not supported in this browser. Use Desktop Chrome/Edge/Brave, or export Wavelet on Android.");
    return;
  }

  try {
    const devices = await navigator.hid.requestDevice({
      filters: [
        ...KTMICRO_FILTERS,
        { vendorId: 0x0572 }, // Allow user to pick CX31993 to demonstrate safety guard
      ],
    });

    if (!devices || devices.length === 0) return;
    await initializeDevice(devices[0], false);
  } catch (err) {
    console.error("HID connection error:", err);
    showToast(`Connection failed: ${err.message}`);
  }
}

export function updateDeviceBadge(type, text) {
  const badge = document.getElementById("deviceBadge");
  if (!badge) return;
  // Support both (type, text) and (text, state)
  const knownTypes = ["connected", "disconnected", "blocked", "warning", "ready", "error"];
  let finalType = type;
  let finalText = text;
  if (knownTypes.includes(String(text).toLowerCase()) && !knownTypes.includes(String(type).toLowerCase())) {
    finalType = text;
    finalText = type;
  }
  badge.className = `badge ${escapeHtml(finalType || "disconnected")}`;
  badge.innerHTML = `<span class="badge-dot"></span> <span>${escapeHtml(finalText || "")}</span>`;
}

async function sendHidReport(reportId, reg, cmd, d0 = 0, d1 = 0, d2 = 0, d3 = 0) {
  if (isDemoMode) {
    console.log(`[Demo Mode HID Tx] Report 0x${reportId.toString(16)}: Reg 0x${reg.toString(16)} CMD 0x${cmd.toString(16)} Data:`, [d0, d1, d2, d3]);
    return;
  }
  if (!connectedHidDevice) throw new Error("No DAC connected.");

  const payload = new Uint8Array([
    reg & 0xff, 0x00, 0x00, 0x00,
    cmd & 0xff, 0x00,
    d0 & 0xff, d1 & 0xff, d2 & 0xff, d3 & 0xff,
  ]);

  await connectedHidDevice.sendReport(reportId, payload);
  await new Promise((r) => setTimeout(r, 12));
}

async function applyToDevice(commitFlash = false) {
  if (isConexantBlocked) {
    showToast("Flash blocked: CX31993 has fixed mask ROM!");
    return;
  }
  if (!connectedHidDevice && !isDemoMode) {
    showToast("Please connect a USB DAC first (or enable Demo Mode).");
    return;
  }

  // The guard runs before anything is sent: unknown device, blocked architecture, or
  // an out-of-range coefficient aborts the whole write.
  // shortcut: demo mode sends nothing, so the guard does not apply there.
  if (!isDemoMode) {
    const guardDevice = matchDevice(guardTable, connectedHidDevice.vendorId, connectedHidDevice.productId, connectedHidDevice.productName);
    const guard = guardWrite(guardTable, guardDevice, currentPreset.bands);
    if (!guard.ok) {
      showToast(`Write refused: ${guard.problems.join("; ")}`);
      return;
    }
  }

  if (commitFlash && !isDemoMode) {
    const stats = getFlashStats(connectedHidDevice);
    const wear = wearLevel(stats);

    let wearWarning = "";
    if (wear.level === "high") {
      wearWarning =
        `⚠️ FLASH SILICON WEAR WARNING!\n` +
        `This DAC has received ${wear.writes24h} NVRAM writes in the last 24 hours (${stats.total} total writes).\n` +
        `Budget EEPROMs degrade after repeated writing. Writing too frequently can permanently wear out the DSP memory.\n` +
        `Nothing on the device enforces its endurance limit — this warning is informational.\n\n`;
    }

    const ok = confirm(
      wearWarning +
        "⚠️ Save to persistent hardware NVRAM?\n\n" +
        `Flash memory has an endurance limit (~10k-100k write cycles). This permanently saves the ${activeHardwareBands}-band PEQ into onboard persistent NVRAM so it persists across reboots and host swaps.\n\n` +
        "Do not disconnect the USB-C cable while saving to NVRAM. Proceed?"
    );
    if (!ok) {
      showToast("NVRAM save cancelled by user.");
      return;
    }
  }

  const compensate2X = document.getElementById("chkCompensate2X")?.checked || false;
  const selSlot = document.getElementById("selHardwareSlot");
  const parsedSlot = parseInt(selSlot?.value, 10);
  const slotId = Number.isNaN(parsedSlot) ? 3 : parsedSlot;

  // Automatic First-Commit Stock Safety Snapshot
  if (commitFlash && connectedHidDevice && !isDemoMode) {
    if (!hasStockBackup(connectedHidDevice, slotId)) {
      try {
        const quirks = detectFirmwareQuirks(connectedHidDevice);
        const isMoondrop = activeHardwareBands === 9 || isMoondropFreeDsp(connectedHidDevice);
        const isWalkplay = activeHardwareBands === 8 || activeHardwareBands === 10 || isWalkplayDsp(connectedHidDevice);
        let currentDacState;
        if (isWalkplay) {
          currentDacState = await readWalkplayPeq(connectedHidDevice, activeHardwareBands, 600);
        } else if (isMoondrop) {
          currentDacState = await readMoondropReport(connectedHidDevice, 300);
        } else {
          currentDacState = await readKtMicroPeq(connectedHidDevice, quirks.requiresCompensate2X);
        }
        if (currentDacState && currentDacState.bands && currentDacState.bands.length > 0) {
          saveStockBackup(connectedHidDevice, slotId, currentDacState);
          const btnRestore = document.getElementById("btnRestoreStock");
          if (btnRestore) btnRestore.style.display = "inline-flex";
          console.log(`[Safety Snapshot] Factory settings snapshotted for Slot ${slotId}`);
        }
      } catch (snapErr) {
        console.warn("Could not capture initial stock snapshot:", snapErr);
      }
    }
  }

  try {
    // Branch 1: WalkPlay Scheme 11 (8-Band) & Scheme 16 (10-Band) Protocol
    if (activeHardwareBands === 8 || activeHardwareBands === 10 || isWalkplayDsp(connectedHidDevice)) {
      const bandCount = activeHardwareBands;
      const slot = 101; // Walkplay default user preset slot
      for (let i = 0; i < bandCount; i++) {
        const b = currentPreset.bands[i] || { type: "PK", freq: 1000, gain: 0, q: 1.0 };
        const effGain = b.enabled === false ? 0.0 : b.gain;
        const pkt = encodeWalkplayFilterPacket(i, b.freq, effGain, b.q, b.type, slot);
        if (isDemoMode) {
          console.log(`[Demo Mode WalkPlay Filter ${i} Tx]:`, pkt);
        } else {
          await connectedHidDevice.sendReport(0x4b, pkt);
          await new Promise((r) => setTimeout(r, 20));
        }
      }

      // Write global preamp
      const gainPkt = encodeWalkplayGlobalGain(currentPreset.preamp || 0.0);
      if (isDemoMode) {
        console.log("[Demo Mode WalkPlay Preamp Tx]:", gainPkt);
      } else {
        await connectedHidDevice.sendReport(0x4b, gainPkt);
        await new Promise((r) => setTimeout(r, 30));
      }

      if (commitFlash) {
        const seq = getWalkplayCommitSequence();
        for (const cmd of seq) {
          if (!isDemoMode) {
            await connectedHidDevice.sendReport(0x4b, cmd);
            await new Promise((r) => setTimeout(r, 25));
          }
        }
        const stats = recordFlashCommit(connectedHidDevice);
        updateFlashCounterBadge(connectedHidDevice);
        showToast(`${bandCount}-Band PEQ saved to WalkPlay NVRAM (Commit #${stats.total})!`);
      } else {
        showToast(`${bandCount}-Band PEQ written to WalkPlay live DSP RAM!`);
      }
      return;
    }

    // Branch 2: Moondrop FreeDSP 9-Band Protocol
    if (activeHardwareBands === 9 || isMoondropFreeDsp(connectedHidDevice)) {
      const payload = encodeMoondropReport(currentPreset.bands, currentPreset.preamp, commitFlash);
      if (isDemoMode) {
        console.log("[Demo Mode Moondrop 9-Band Tx] 64-byte frame:", payload);
      } else {
        await connectedHidDevice.sendReport(0x00, payload);
      }
      if (commitFlash) {
        const stats = recordFlashCommit(connectedHidDevice);
        updateFlashCounterBadge(connectedHidDevice);
        showToast(`9-Band PEQ saved to Moondrop FreeDSP NVRAM (Commit #${stats.total})!`);
      } else {
        showToast("9-Band PEQ written to Moondrop FreeDSP live RAM!");
      }
      return;
    }

    // Branch 2: KTMicro KT02H20 5-Band Protocol
    const REPORT_ID = 0x4b;
    const CMD_WRITE = 0x57;
    const CMD_COMMIT = 0x53;

    // 1. Enable selected EQ slot (Register 0x24: Slot 0x01-0x04, default 0x03)
    await sendHidReport(REPORT_ID, 0x24, CMD_WRITE, slotId & 0xff, 0, 0, 0);

    // 2. Write 5 bands
    for (let i = 0; i < 5; i++) {
      const b = currentPreset.bands[i] || { type: "PK", freq: 1000, gain: 0, q: 1.0 };
      const effGain = b.enabled === false ? 0.0 : b.gain;
      const { regGf, regQ, gfData, qData } = encodeKtMicroBandPackets(i, { ...b, gain: effGain }, compensate2X);
      await sendHidReport(REPORT_ID, regGf, CMD_WRITE, ...gfData);
      await sendHidReport(REPORT_ID, regQ, CMD_WRITE, ...qData);
    }

    // 3. Preamp (Register 0x66 in 0.5 dB steps)
    // Only write 0x66 when the table says preamp is supported. The table records the noPregain
    // quirk for devices where writing 0x66 locks out volume control (e.g. Kiwi Ears Allegro Mini).
    // Note: Always write 0x66 even when preamp is 0.0 dB (preampByte = 0x00) to clear prior digital
    // attenuation from previous profiles (audit credit: Captain Ødegard, Head-Fi).
    // Preamp is clamped to [-24.0, +12.0] dB to prevent signed int8 sign inversion/acoustic clipping hazard.
    const entry = entryFor(connectedHidDevice);
    if (!(entry && (entry.quirks || []).includes("noPregain"))) {
      const rawVal = Number(currentPreset.preamp ?? 0.0);
      const safeVal = Number.isFinite(rawVal) ? rawVal : 0.0;
      const clampedPreamp = Math.max(-24.0, Math.min(12.0, safeVal));
      const preampByte = Math.round(clampedPreamp * 2.0) & 0xff;
      await sendHidReport(REPORT_ID, 0x66, CMD_WRITE, preampByte, 0, 0, 0);
    }

    // 3b. Hardware DAC reconstruction filter (Register 0x11)
    // Register 0x11 is a FiiO hardware-DSP feature; writing it on other hardware corrupts volume registers.
    const isFiio = Boolean(entry) && entry.architecture === "fiio_dsp";
    const selDac = document.getElementById("selDacFilter");
    if (selDac && isFiio) {
      const parsedFilter = parseInt(selDac.value, 10);
      const filterVal = Number.isNaN(parsedFilter) ? 1 : parsedFilter;
      await sendKtMicroFilter(connectedHidDevice, filterVal);
    }

    // 4. NVRAM Flash Commit & Event-Driven Re-Enumeration Watcher
    if (commitFlash) {
      if (isFiio && slotId !== 3) {
        showToast("Note: JA11 slots 1, 2, and 4 are read-only factory presets in firmware. Changes will only persist permanently in Slot 3 (USER1).", "warning");
      }
      const stats = recordFlashCommit(connectedHidDevice);
      updateFlashCounterBadge(connectedHidDevice);
      isRebootingPostCommit = true;
      try {
        await sendHidReport(REPORT_ID, 0x00, CMD_COMMIT, 0, 0, 0, 0);
      } catch (commitErr) {
        console.warn("Soft-reboot USB drop on commit:", commitErr);
      }
      showToast(`PEQ saved to Slot ${slotId} persistent NVRAM (Commit #${stats.total})! Awaiting USB re-enumeration...`);

      const reenumerated = await waitForUsbReenumeration(navigator.hid, KTMICRO_FILTERS, 4000, 200);
      isRebootingPostCommit = false;
      if (reenumerated) {
        await initializeDevice(reenumerated, true);
        showToast(`USB Re-enumeration Verified (Settings Committed to NVRAM). Full register verification is performed via "Read from DAC".`);
      }
    } else {
      showToast(`PEQ written to Slot ${slotId} live DSP RAM (Instant Audition)!`);
    }
  } catch (err) {
    isRebootingPostCommit = false;
    console.error("Apply error:", err);
    showToast(`Error communicating with DAC: ${err.message}`);
  }
}

async function readFromDevice(silent = false) {
  if (isConexantBlocked) {
    if (!silent) showToast("Read blocked: CX31993 has fixed mask ROM!");
    return;
  }
  if (!connectedHidDevice && !isDemoMode) {
    if (!silent) showToast("Please connect a USB DAC first (or enable Demo Mode).");
    return;
  }

  if (isDemoMode) {
    if (!silent) showToast("Demo Mode: Loaded active simulated DSP registers into editor.");
    buildControlsUI();
    renderCurve();
    return;
  }

  try {
    if (!silent) showToast("Reading registers from hardware DSP...");
    const isMoondrop = activeHardwareBands === 9 || isMoondropFreeDsp(connectedHidDevice);
    const isWalkplay = activeHardwareBands === 8 || activeHardwareBands === 10 || isWalkplayDsp(connectedHidDevice);

    if (isWalkplay) {
      const res = await readWalkplayPeq(connectedHidDevice, activeHardwareBands);
      if (res && res.bands && res.bands.length > 0) {
        currentPreset.preamp = res.preamp;
        currentPreset.bands = res.bands;
        saveStockBackup(connectedHidDevice, 101, res);
        const btnRestore = document.getElementById("btnRestoreStock");
        if (btnRestore) btnRestore.style.display = "inline-flex";
        buildControlsUI();
        renderCurve();
        if (!silent) showToast(`Successfully read ${res.bands.length} bands from WalkPlay DSP!`);
      }
    } else if (isMoondrop) {
      const res = await readMoondropReport(connectedHidDevice);
      if (res && res.bands && res.bands.length > 0) {
        currentPreset.preamp = res.preamp;
        currentPreset.bands = res.bands;
        activeHardwareBands = 9;
        saveStockBackup(connectedHidDevice, 1, res);
        const btnRestore = document.getElementById("btnRestoreStock");
        if (btnRestore) btnRestore.style.display = "inline-flex";
        buildControlsUI();
        renderCurve();
        if (!silent) showToast(`Successfully read ${res.bands.length} bands from Moondrop FreeDSP!`);
      }
    } else {
      const quirks = detectFirmwareQuirks(connectedHidDevice);
      const res = await readKtMicroPeq(connectedHidDevice, quirks.requiresCompensate2X);
      if (res && res.bands && res.bands.length > 0) {
        currentPreset.preamp = res.preamp;
        currentPreset.bands = res.bands;
        activeHardwareBands = 5;
        if (res.slotId) {
          const selSlot = document.getElementById("selHardwareSlot");
          if (selSlot) selSlot.value = String(res.slotId);
        }
        if (res.dacFilter) {
          const selDac = document.getElementById("selDacFilter");
          if (selDac) selDac.value = String(res.dacFilter);
        }
        saveStockBackup(connectedHidDevice, res.slotId || 3, res);
        const btnRestore = document.getElementById("btnRestoreStock");
        if (btnRestore) btnRestore.style.display = "inline-flex";
        buildControlsUI();
        renderCurve();
        if (!silent) {
          showToast(`Successfully read 5 bands from Slot ${res.slotId || 3} (Preamp: ${res.preamp > 0 ? "+" : ""}${res.preamp.toFixed(1)} dB)!`);
        }
      }
    }
  } catch (err) {
    console.error("Read error:", err);
    if (!silent) showToast(`Failed to read from DAC: ${err.message}`);
  }
}

function exportBackupPreset() {
  const slotId = parseInt(document.getElementById("selHardwareSlot")?.value || "3", 10);
  const out = {
    name: currentPreset.name || `Custom PEQ (Slot ${slotId})`,
    slug: (currentPreset.slug || "custom_peq").replace(/[^a-z0-9_-]/gi, "_"),
    description: currentPreset.description || `Hardware PEQ profile for Slot ${slotId}`,
    slot_id: slotId,
    preamp: Number(currentPreset.preamp) || 0.0,
    bands: currentPreset.bands.map((b, i) => ({
      index: i + 1,
      type: b.type || "PK",
      freq: Math.round(Number(b.freq) || 1000),
      gain: Math.round((Number(b.gain) || 0.0) * 10) / 10,
      q: Math.round((Number(b.q) || 1.0) * 100) / 100,
      enabled: b.enabled !== false,
    })),
  };
  const dacFilterEl = document.getElementById("selDacFilter");
  if (dacFilterEl) out.dac_filter = dacFilterEl.options[dacFilterEl.selectedIndex]?.text || "FAST-LL";

  const jsonStr = JSON.stringify(out, null, 2);
  downloadFile(`${out.slug}_slot${slotId}.json`, jsonStr, "application/json");
  showToast(`Backup preset saved as ${out.slug}_slot${slotId}.json!`);
}

async function sharePresetUrl() {
  try {
    const queryStr = encodePresetToUrlParams(currentPreset, currentPreset.bands, activeHardwareBands);
    const shareUrl = `${window.location.origin}${window.location.pathname}?${queryStr}`;
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", `?${queryStr}`);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(shareUrl);
      showToast("🔗 Shareable EQ link copied to clipboard!");
    } else {
      prompt("Copy your shareable EQ link:", shareUrl);
    }
  } catch (err) {
    console.error("Share URL error:", err);
    showToast(`Failed to generate share link: ${err.message}`);
  }
}

function tryLoadPresetFromUrl() {
  if (!window.location.search || window.location.search.length <= 1) return false;
  try {
    const decoded = decodePresetFromUrlParams(window.location.search);
    if (decoded && Array.isArray(decoded.bands) && decoded.bands.length > 0) {
      if (decoded.hw_bands && [5, 8, 9, 10].includes(decoded.hw_bands)) {
        activeHardwareBands = decoded.hw_bands;
        const selHwBands = document.getElementById("selHardwareBandCount");
        if (selHwBands) selHwBands.value = String(activeHardwareBands);
        const lblTitle = document.getElementById("lblMatrixTitle");
        if (lblTitle) lblTitle.textContent = `${activeHardwareBands}-Band Biquad Filter Matrix`;
      }
      const rawBands = decoded.bands.map((b, i) => ({
        index: i + 1,
        type: b.type || "PK",
        freq: Number(b.freq) || 1000.0,
        gain: Number(b.gain) || 0.0,
        q: Number(b.q) || 1.0,
        enabled: b.enabled !== false,
      }));
      const finalBands = rawBands.length > activeHardwareBands
        ? decimateBands(rawBands, activeHardwareBands)
        : decimateBands(rawBands, activeHardwareBands, false);

      currentPreset = {
        name: decoded.name || "Shared PEQ Profile",
        slug: decoded.slug || "shared_peq",
        description: decoded.description || "Loaded from URL share link",
        preamp: typeof decoded.preamp === "number" ? decoded.preamp : 0.0,
        bands: finalBands,
        fullBands: rawBands.length > activeHardwareBands ? rawBands : null,
      };
      if (rawBands.length > activeHardwareBands) {
        referenceTargetCurve = {
          name: `${currentPreset.name} (${rawBands.length}-Band Target)`,
          bands: rawBands,
          preamp: currentPreset.preamp,
        };
        showTargetOverlay = true;
      } else {
        referenceTargetCurve = null;
      }
      document.querySelectorAll(".preset-card").forEach((c) => c.classList.remove("active"));
      setTimeout(() => {
        showToast(`🔗 Loaded shared preset "${currentPreset.name}" (${currentPreset.bands.length} bands)`);
      }, 150);
      return true;
    }
  } catch (err) {
    console.warn("URL query did not contain a valid PEQ preset:", err.message);
  }
  return false;
}

function restoreStockBackup() {
  const slotId = parseInt(document.getElementById("selHardwareSlot")?.value || "3", 10);
  if (!connectedHidDevice && !isDemoMode) {
    showToast("Please connect your DAC to restore stock backup.");
    return;
  }
  const stock = getStockBackup(connectedHidDevice, slotId);
  if (!stock || !stock.bands || stock.bands.length === 0) {
    showToast(`No stock backup found for Slot ${slotId}.`);
    return;
  }

  currentPreset = {
    name: `Stock Factory Backup (Slot ${slotId})`,
    slug: `stock_backup_slot${slotId}`,
    description: `Original factory DSP tuning captured prior to NVRAM commit`,
    preamp: stock.preamp ?? 0.0,
    bands: stock.bands.map((b, i) => ({ ...b, index: i + 1 })),
  };

  buildControlsUI();
  renderCurve();
  triggerAutoApply();
  showToast(`Stock factory tuning for Slot ${slotId} restored into editor! Click 'Save to NVRAM' to make permanent.`);
}

export async function clearDeviceFlash() {
  if (!connectedHidDevice && !isDemoMode) {
    showToast("Please connect your DAC first.");
    return;
  }

  // Check connected device architecture before sending sendKtMicroClearFlash
  const isNonKtmicro = connectedDeviceProfile && connectedDeviceProfile.arch &&
    connectedDeviceProfile.arch !== "ktmicro" && connectedDeviceProfile.arch !== "ktmicro_dsp";
  const isMoondrop = connectedHidDevice && isMoondropFreeDsp(connectedHidDevice);
  const isWalkplay = connectedHidDevice && isWalkplayDsp(connectedHidDevice);

  if (isNonKtmicro || isMoondrop || isWalkplay) {
    showToast("⚠️ 0x43 CLEAR hardware factory reset is only supported on KTMicro DSP hardware. For WalkPlay / Moondrop devices, flatten PEQ bands and flash instead.");
    return;
  }

  const ok = confirm(
    "⚠️ Hardware Factory Reset (0x43 CLEAR)?\n\nThis will send the hardware CLEAR command to erase all custom NVRAM flash configurations and restore the Kiwi Ears factory default state.\n\nProceed?"
  );
  if (!ok) return;

  try {
    if (connectedHidDevice) {
      await sendKtMicroClearFlash(connectedHidDevice);
    } else {
      const REPORT_ID = 0x4b;
      const CMD_CLEAR = 0x43;
      await sendHidReport(REPORT_ID, 0x00, CMD_CLEAR, 0, 0, 0, 0);
    }
    showToast("Factory CLEAR sent! Microcontroller resetting...");
    isRebootingPostCommit = true;
    const reenumerated = await waitForUsbReenumeration(navigator.hid, KTMICRO_FILTERS, 4000, 200);
    isRebootingPostCommit = false;
    if (reenumerated) {
      await initializeDevice(reenumerated, true);
    }
    showToast("Factory reset complete! Allegro Mini restored to stock defaults.");
  } catch (err) {
    isRebootingPostCommit = false;
    console.error("Clear error:", err);
    showToast(`Reset failed: ${err.message}`);
  }
}

function triggerAutoApply() {
  const autoApply = document.getElementById("chkAutoApply")?.checked;
  if (!autoApply) return;
  clearTimeout(autoApplyTimer);
  autoApplyTimer = setTimeout(() => {
    applyToDevice(false);
  }, 75);
}

// ── UI Controls & Sync ────────────────────────────────────────────────────────
function buildControlsUI() {
  const container = document.getElementById("controlsContainer");
  if (!container) return;
  container.innerHTML = "";

  currentPreset.bands.forEach((b, i) => {
    const card = document.createElement("div");
    card.className = "band-control";
    card.innerHTML = `
      <div class="band-header">
        <div class="band-num">
          <span class="band-pill">${i + 1}</span> Band ${i + 1}
        </div>
        <label class="checkbox-label" style="font-size: 0.72rem; margin-left: auto; gap: 0.25rem;" title="Mute/unmute this band">
          <input type="checkbox" id="enable_${i}" ${b.enabled !== false ? "checked" : ""}>
          <span id="lblEnable_${i}">${b.enabled !== false ? "Active" : "Muted"}</span>
        </label>
        <select id="type_${i}" aria-label="Band ${i + 1} Filter Type" style="width: 100px;">
          <option value="PK" ${b.type === "PK" ? "selected" : ""}>Peaking</option>
          <option value="LSQ" ${b.type === "LSQ" ? "selected" : ""}>Low-Shelf</option>
          <option value="HSQ" ${b.type === "HSQ" ? "selected" : ""}>High-Shelf</option>
        </select>
      </div>

      <div class="control-row">
        <div class="control-label">
          <label for="freq_${i}">Freq</label>
          <span id="lblFreq_${i}">${Math.round(b.freq)} Hz</span>
        </div>
        <input type="range" id="freq_${i}" aria-label="Band ${i + 1} Frequency (Hz)" min="20" max="20000" step="1" value="${b.freq}">
      </div>

      <div class="control-row">
        <div class="control-label">
          <label for="gain_${i}">Gain</label>
          <span id="lblGain_${i}">${(b.gain > 0 ? "+" : "") + b.gain.toFixed(1)} dB</span>
        </div>
        <input type="range" id="gain_${i}" aria-label="Band ${i + 1} Gain (dB)" min="-12" max="12" step="0.1" value="${b.gain}">
      </div>

      <div class="control-row">
        <div class="control-label">
          <label for="q_${i}">Q Factor</label>
          <span id="lblQ_${i}">${b.q.toFixed(2)}</span>
        </div>
        <input type="range" id="q_${i}" aria-label="Band ${i + 1} Q Factor" min="0.1" max="10" step="0.05" value="${b.q}">
      </div>
    `;
    container.appendChild(card);

    document.getElementById(`enable_${i}`)?.addEventListener("change", (e) => {
      currentPreset.bands[i].enabled = e.target.checked;
      const lbl = document.getElementById(`lblEnable_${i}`) || e.target.parentElement?.querySelector("span");
      if (lbl) lbl.textContent = e.target.checked ? "Active" : "Muted";
      renderCurve();
      triggerAutoApply();
    });

    document.getElementById(`type_${i}`).addEventListener("change", (e) => {
      currentPreset.bands[i].type = e.target.value;
      renderCurve();
      triggerAutoApply();
    });

    document.getElementById(`freq_${i}`).addEventListener("input", (e) => {
      currentPreset.bands[i].freq = parseFloat(e.target.value);
      document.getElementById(`lblFreq_${i}`).textContent = `${Math.round(currentPreset.bands[i].freq)} Hz`;
      renderCurve();
      triggerAutoApply();
    });

    document.getElementById(`gain_${i}`).addEventListener("input", (e) => {
      currentPreset.bands[i].gain = parseFloat(e.target.value);
      const val = currentPreset.bands[i].gain;
      document.getElementById(`lblGain_${i}`).textContent = `${val > 0 ? "+" : ""}${val.toFixed(1)} dB`;
      renderCurve();
      triggerAutoApply();
    });

    document.getElementById(`q_${i}`).addEventListener("input", (e) => {
      currentPreset.bands[i].q = parseFloat(e.target.value);
      document.getElementById(`lblQ_${i}`).textContent = currentPreset.bands[i].q.toFixed(2);
      renderCurve();
      triggerAutoApply();
    });
  });

  const preampInput = document.getElementById("sliderPreamp");
  if (preampInput) {
    preampInput.value = currentPreset.preamp;
    document.getElementById("lblPreamp").textContent = `${currentPreset.preamp > 0 ? "+" : ""}${currentPreset.preamp.toFixed(1)} dB`;

    preampInput.oninput = (e) => {
      currentPreset.preamp = parseFloat(e.target.value);
      document.getElementById("lblPreamp").textContent = `${currentPreset.preamp > 0 ? "+" : ""}${currentPreset.preamp.toFixed(1)} dB`;
      renderCurve();
      triggerAutoApply();
    };
  }
}

function syncBandControls(i) {
  const b = currentPreset.bands[i];
  const freqEl = document.getElementById(`freq_${i}`);
  const gainEl = document.getElementById(`gain_${i}`);
  const qEl = document.getElementById(`q_${i}`);
  const typeEl = document.getElementById(`type_${i}`);

  if (freqEl) freqEl.value = b.freq;
  if (gainEl) gainEl.value = b.gain;
  if (qEl) qEl.value = b.q;
  if (typeEl) typeEl.value = b.type;

  const enEl = document.getElementById(`enable_${i}`);
  const lblEn = document.getElementById(`lblEnable_${i}`);
  if (enEl) enEl.checked = b.enabled !== false;
  if (lblEn) lblEn.textContent = b.enabled !== false ? "Active" : "Muted";

  const lblFreq = document.getElementById(`lblFreq_${i}`);
  const lblGain = document.getElementById(`lblGain_${i}`);
  const lblQ = document.getElementById(`lblQ_${i}`);

  if (lblFreq) lblFreq.textContent = `${Math.round(b.freq)} Hz`;
  if (lblGain) lblGain.textContent = `${b.gain > 0 ? "+" : ""}${b.gain.toFixed(1)} dB`;
  if (lblQ) lblQ.textContent = b.q.toFixed(2);
}

function updateStats() {
  const statsEl = document.getElementById("graphStats");
  if (!statsEl) return;

  const peakGain = calculatePeakCompositeGain(currentPreset.bands);
  const totalPeak = peakGain + currentPreset.preamp;

  let peakStatus = "";
  if (totalPeak > 0.05) {
    peakStatus = ` | <span style="color: var(--accent-red); font-weight: 700;">⚠️ Intersample Clip Risk (+${totalPeak.toFixed(1)} dBFS)</span>`;
  } else {
    peakStatus = ` | <span style="color: var(--accent-green); font-weight: 600;">Peak: ${totalPeak.toFixed(1)} dBFS</span>`;
  }

  statsEl.innerHTML = `Preamp: ${currentPreset.preamp > 0 ? "+" : ""}${currentPreset.preamp.toFixed(1)} dB${peakStatus} | RBJ 48/96kHz`;

  const alertEl = document.getElementById("acousticAlert");
  const alertText = document.getElementById("acousticAlertText");
  if (alertEl && alertText) {
    const warnings = lintAcousticBands(currentPreset.bands);
    if (warnings.length > 0) {
      alertText.innerHTML = `<strong>Acoustic Advisory Notice:</strong><br>${warnings.map(escapeHtml).join("<br>")}`;
      alertEl.classList.add("visible");
    } else {
      alertEl.classList.remove("visible");
    }
  }
}

function selectPreset(slug) {
  const p = PRESETS[slug];
  if (!p) return;
  currentPreset = JSON.parse(JSON.stringify(p));
  currentPreset.fullBands = p.bands.map((b) => ({ ...b }));
  currentPreset.bands = decimateBands(currentPreset.fullBands, activeHardwareBands);
  referenceTargetCurve = null;

  if (p.slot_id) {
    const selSlot = document.getElementById("selHardwareSlot");
    if (selSlot) selSlot.value = String(p.slot_id);
  }

  document.querySelectorAll(".preset-card").forEach((card) => {
    const isSelected = card.getAttribute("data-preset") === slug;
    card.classList.toggle("active", isSelected);
    card.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });

  buildControlsUI();
  renderCurve();
  showToast(`Loaded preset: ${p.name}`);
  triggerAutoApply();
}

// ── Host DSP File Exporters ───────────────────────────────────────────────────
function downloadFile(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function getBandsForExport() {
  const sel = document.getElementById("selExportFidelity");
  const fidelity = sel ? sel.value : "hardware";
  if (fidelity === "full" && currentPreset.fullBands && currentPreset.fullBands.length > currentPreset.bands.length) {
    return { bands: currentPreset.fullBands, tag: `${currentPreset.fullBands.length}band_target`, isFull: true };
  }
  return { bands: currentPreset.bands, tag: `${currentPreset.bands.length}band_hw`, isFull: false };
}

function exportPipeWireConf() {
  const preset = currentPreset;
  const slug = preset.slug || "custom";
  const { bands, tag, isFull } = getBandsForExport();
  const conf = formatPipeWireConf(preset, bands, isFull);
  downloadFile(`99-jm6pro-${slug}-${tag}.conf`, conf);
  showToast(`Downloaded PipeWire configuration (${bands.length} bands)!`);
}

function exportEqualizerApo() {
  const preset = currentPreset;
  const { bands, tag, isFull } = getBandsForExport();
  const txt = formatEqualizerApo(preset, bands, isFull);
  downloadFile(`${preset.slug || "preset"}_${tag}_equalizer_apo.txt`, txt);
  showToast(`Downloaded EqualizerAPO profile (${bands.length} bands)!`);
}

function exportWaveletGraphicEq() {
  const { bands, tag } = getBandsForExport();
  const txt = formatWaveletGraphicEq(bands, currentPreset.preamp, 127);
  downloadFile(`${currentPreset.slug || "preset"}_${tag}_wavelet_graphiceq.txt`, txt);
  showToast(`Downloaded Wavelet GraphicEQ profile (${bands.length} bands)!`);
}

function exportQudelixProfile() {
  const { bands, tag, isFull } = getBandsForExport();
  const jsonStr = formatQudelixJson(currentPreset, bands, isFull);
  downloadFile(`${currentPreset.slug || "preset"}_${tag}_qudelix.json`, jsonStr);
  showToast(`Downloaded Qudelix-5K profile (${bands.length} bands)!`);
}

// ── Web Audio Test Tone Generator & Real-Time DSP Chain ──────────────────────
let audioCtx = null;
let toneOsc = null;
let noiseNode = null;
let masterVolGainNode = null;
let preampGainNode = null;
let webAudioFiltNodes = [];
let isToneActive = false;
let isPlayingNoise = false;
let sweepInterval = null;

function initSharedAudioContext() {
  if (!audioCtx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    audioCtx = new AudioCtx();
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  return audioCtx;
}

function getWebAudioFilterType(ftype) {
  const t = String(ftype || "PK").toUpperCase();
  if (t === "LSQ" || t === "LOW_SHELF" || t === "LOWSHELF") return "lowshelf";
  if (t === "HSQ" || t === "HIGH_SHELF" || t === "HIGHSHELF") return "highshelf";
  return "peaking";
}

function connectSourceThroughDspChain(sourceNode, baseVolumeMultiplier = 1.0) {
  const ctx = initSharedAudioContext();
  masterVolGainNode = ctx.createGain();
  const sliderVol = document.getElementById("sliderToneVol");
  const vol = sliderVol ? parseFloat(sliderVol.value) || 0.03 : 0.03;
  masterVolGainNode.gain.setValueAtTime(0.0001, ctx.currentTime);
  masterVolGainNode.gain.exponentialRampToValueAtTime(vol * baseVolumeMultiplier, ctx.currentTime + 0.04);

  sourceNode.connect(masterVolGainNode);

  // Double-EQ Guard:
  // When a physical hardware DSP DAC is actively connected (and not in demo mode),
  // output flat signal directly so the hardware DSP performs the filtering.
  // In Demo Mode or Host-DSP mode, build the Web Audio BiquadFilterNode chain.
  if (connectedHidDevice && !isDemoMode) {
    masterVolGainNode.connect(ctx.destination);
    return false;
  }

  preampGainNode = ctx.createGain();
  const linearGain = Math.pow(10, (Number(currentPreset.preamp) || 0.0) / 20);
  preampGainNode.gain.setValueAtTime(linearGain, ctx.currentTime);

  masterVolGainNode.connect(preampGainNode);
  let lastNode = preampGainNode;

  webAudioFiltNodes = [];
  const bands = currentPreset.bands || [];
  for (let i = 0; i < bands.length; i++) {
    const b = bands[i];
    const filt = ctx.createBiquadFilter();
    filt.type = getWebAudioFilterType(b.type);
    filt.frequency.setValueAtTime(Math.max(20, Math.min(20000, Number(b.freq) || 1000)), ctx.currentTime);
    const effGain = b.enabled === false ? 0.0 : (Number(b.gain) || 0.0);
    filt.gain.setValueAtTime(effGain, ctx.currentTime);
    filt.Q.setValueAtTime(Math.max(0.1, Math.min(20, Number(b.q) || 1.0)), ctx.currentTime);
    lastNode.connect(filt);
    lastNode = filt;
    webAudioFiltNodes.push(filt);
  }

  lastNode.connect(ctx.destination);
  return true;
}

function updateWebAudioFilters() {
  if ((!isPlayingNoise && !isToneActive) || !audioCtx) return;
  if (connectedHidDevice && !isDemoMode) return;

  const now = audioCtx.currentTime;
  if (preampGainNode) {
    const linearGain = Math.pow(10, (Number(currentPreset.preamp) || 0.0) / 20);
    preampGainNode.gain.setValueAtTime(linearGain, now);
  }

  const bands = currentPreset.bands || [];
  for (let i = 0; i < webAudioFiltNodes.length; i++) {
    const filt = webAudioFiltNodes[i];
    const b = bands[i];
    if (!b) {
      filt.gain.setValueAtTime(0.0, now);
      continue;
    }
    const typeStr = getWebAudioFilterType(b.type);
    if (filt.type !== typeStr) filt.type = typeStr;
    filt.frequency.setValueAtTime(Math.max(20, Math.min(20000, Number(b.freq) || 1000)), now);
    const effGain = b.enabled === false ? 0.0 : (Number(b.gain) || 0.0);
    filt.gain.setValueAtTime(effGain, now);
    filt.Q.setValueAtTime(Math.max(0.1, Math.min(20, Number(b.q) || 1.0)), now);
  }
}

function updateTonePlayhead(freq = null) {
  const playhead = document.getElementById("svgTonePlayhead");
  const svg = document.getElementById("eqSvg");
  if (!playhead || !svg) return;
  if (!isToneActive) {
    playhead.style.display = "none";
    return;
  }
  const f = freq !== null ? freq : parseFloat(document.getElementById("sliderToneFreq")?.value || "7000");
  const width = svg.clientWidth || 800;
  const x = xForFreq(f, width);
  playhead.setAttribute("x1", x);
  playhead.setAttribute("x2", x);
  playhead.style.display = "block";
}

function stopAudioGenerators() {
  if (sweepInterval) {
    clearInterval(sweepInterval);
    sweepInterval = null;
    const btnSweep = document.getElementById("btnToneSweep");
    if (btnSweep) {
      btnSweep.textContent = "🔄 Run Sweep";
      btnSweep.classList.remove("active");
    }
  }

  if (masterVolGainNode && audioCtx) {
    try {
      masterVolGainNode.gain.linearRampToValueAtTime(0.0001, audioCtx.currentTime + 0.025);
    } catch (_) {}
  }

  if (toneOsc) {
    const oscToStop = toneOsc;
    toneOsc = null;
    try {
      oscToStop.stop();
      oscToStop.disconnect();
    } catch (_) {}
  }

  if (noiseNode) {
    const nodeToStop = noiseNode;
    noiseNode = null;
    try {
      nodeToStop.stop();
      nodeToStop.disconnect();
    } catch (_) {}
  }

  if (masterVolGainNode) {
    try { masterVolGainNode.disconnect(); } catch (_) {}
    masterVolGainNode = null;
  }
  if (preampGainNode) {
    try { preampGainNode.disconnect(); } catch (_) {}
    preampGainNode = null;
  }
  for (const f of webAudioFiltNodes) {
    try { f.disconnect(); } catch (_) {}
  }
  webAudioFiltNodes = [];

  isToneActive = false;
  isPlayingNoise = false;
  updateTonePlayhead();

  const btnPlay = document.getElementById("btnTonePlay");
  if (btnPlay) {
    btnPlay.textContent = "▶ Sine Tone";
    btnPlay.classList.remove("active");
  }

  const btnPink = document.getElementById("btnPinkNoise");
  if (btnPink) {
    btnPink.textContent = "📻 Pink Noise";
    btnPink.classList.remove("active");
  }

  const btnTest = document.getElementById("btnTestNoise");
  if (btnTest) {
    btnTest.textContent = "Play Pink Noise";
    btnTest.classList.remove("btn-burn");
  }
}

function startTone(freq = 7000, isSweep = false) {
  const ctx = initSharedAudioContext();
  stopAudioGenerators();

  toneOsc = ctx.createOscillator();
  toneOsc.type = "sine";
  toneOsc.frequency.setValueAtTime(freq, ctx.currentTime);

  connectSourceThroughDspChain(toneOsc, 1.0);
  toneOsc.start();
  isToneActive = true;
  updateTonePlayhead(freq);

  if (!isSweep) {
    const btnPlay = document.getElementById("btnTonePlay");
    if (btnPlay) {
      btnPlay.textContent = "⏹ Stop Sine";
      btnPlay.classList.add("active");
    }
  }
}

async function toggleTestNoise() {
  if (!isPlayingNoise) {
    const ctx = initSharedAudioContext();
    stopAudioGenerators();

    const bufferSize = ctx.sampleRate * 4;
    const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const output = noiseBuffer.getChannelData(0);

    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      output[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.08;
      b6 = white * 0.115926;
    }

    noiseNode = ctx.createBufferSource();
    noiseNode.buffer = noiseBuffer;
    noiseNode.loop = true;

    const usingSoftwareChain = connectSourceThroughDspChain(noiseNode, 1.2);
    if (usingSoftwareChain) {
      showToast("Live browser auditioning active via Web Audio PEQ filter chain!");
    } else {
      showToast("Live auditioning via connected hardware DSP DAC (hardware-filtered).");
    }

    noiseNode.start();
    isPlayingNoise = true;

    const btnPink = document.getElementById("btnPinkNoise");
    if (btnPink) {
      btnPink.textContent = "⏹ Stop Noise";
      btnPink.classList.add("active");
    }
    const btnTest = document.getElementById("btnTestNoise");
    if (btnTest) {
      btnTest.textContent = "Stop Pink Noise";
      btnTest.classList.add("btn-burn");
    }
  } else {
    stopAudioGenerators();
  }
}

// ── Community Database Search & Pull ──────────────────────────────────────────
export async function performDatabaseSearch() {
  const input = document.getElementById("dbSearchInput");
  const query = (input ? input.value : "").trim();
  const sourceFilter = document.getElementById("dbSourceFilter") ? document.getElementById("dbSourceFilter").value : "";
  const container = document.getElementById("dbResultsList");

  if (!query) {
    if (container) container.style.display = "none";
    return;
  }

  if (container) {
    container.style.display = "grid";
    container.innerHTML = `<div style="grid-column: 1/-1; padding: 0.8rem; text-align: center; color: var(--text-secondary); font-size: 0.85rem;">Searching community database...</div>`;
  }

  const entries = await loadAutoEqDatabase((msg) => showToast(msg));
  const matched = searchAutoEqEntries(entries, query, sourceFilter, 24);

  if (!container) return;

  if (matched.length === 0) {
    container.innerHTML = `<div style="grid-column: 1/-1; padding: 0.8rem; text-align: center; color: var(--accent-yellow); font-size: 0.85rem;">No matching models found for "${escapeHtml(query)}". Try broader search terms.</div>`;
    return;
  }

  container.innerHTML = "";
  matched.forEach((e) => {
    const card = document.createElement("div");
    card.className = "db-result-card";
    card.setAttribute("tabindex", "0");
    card.setAttribute("role", "button");
    const safeName = escapeHtml(e.name || "");
    const safeBrand = e.brand ? escapeHtml(e.brand) : "";
    const safeType = e.type ? escapeHtml(e.type) : "";
    const safeRig = e.rig ? escapeHtml(e.rig) : "";
    const safeSource = escapeHtml(e.source || "");
    card.setAttribute("aria-label", `Load ${safeName} from ${safeSource}`);
    card.innerHTML = `
      <div class="db-result-name">${safeName}</div>
      <div class="db-result-meta">
        <span style="color: var(--accent-cyan);">${safeSource}</span>
        ${safeBrand ? `<span style="color: var(--text-secondary); font-size: 0.75rem;">${safeBrand}</span>` : ""}
        ${safeType ? `<span style="color: var(--text-secondary); font-size: 0.75rem;">${safeType}</span>` : ""}
        ${safeRig ? `<span style="color: var(--text-muted); font-size: 0.7rem;">(${safeRig})</span>` : ""}
        <span style="color: var(--text-muted); font-family: var(--font-mono); font-size: 0.7rem;">AutoEq ${escapeHtml(activeHardwareBands)}-Band</span>
      </div>
    `;
    card.addEventListener("click", () => pullCommunityPreset(e));
    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        pullCommunityPreset(e);
      }
    });
    container.appendChild(card);
  });
}

async function pullCommunityPreset(entry) {
  showToast(`Fetching ${activeHardwareBands}-band PEQ profile for ${entry.name}...`);
  try {
    const { preamp, bands, isOfflineFallback } = await fetchAndParseAutoEqPreset(entry);
    const optimizedBands = decimateBands(bands, activeHardwareBands);

    currentPreset = {
      name: `${entry.name} (${entry.source})`,
      slug: entry.name.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
      description: `AutoEq target optimization (source: ${entry.source}${isOfflineFallback ? " - Offline Snapshot" : ""})`,
      preamp: Math.round(preamp * 10) / 10,
      bands: optimizedBands,
      fullBands: JSON.parse(JSON.stringify(bands)),
    };

    referenceTargetCurve = {
      name: `${entry.name} (${bands.length}-Band Target)`,
      preamp: Math.round(preamp * 10) / 10,
      bands: JSON.parse(JSON.stringify(bands)),
    };

    document.querySelectorAll(".preset-card").forEach((c) => c.classList.remove("active"));

    resetMacroControls(currentPreset.bands);
    buildControlsUI();
    renderCurve();
    triggerAutoApply();
    showToast(`Loaded ${entry.name}${isOfflineFallback ? " (Offline Snapshot)" : ""}! Ready to audition or flash.`);
  } catch (err) {
    console.error("Error pulling community preset:", err);
    showToast(`Failed to pull ${entry.name}: ${err.message}`);
  }
}

// ── Hardware DAC Directory & Compatibility Engine ─────────────────────────────
let dacCatalog = [];
let currentDacFilter = "all";

const DEFAULT_DACS = [
  {
    id: "allegro_mini",
    name: "Kiwi Ears Allegro Mini",
    brand: "Kiwi Ears",
    chipset: "KTMicro KT02H20 / CB1200AU",
    architecture: "ktmicro_dsp",
    dac_type: "hardware_dsp",
    flashable: true,
    vid: 12722, pid: 273,
    resolution: "32-bit / 384 kHz, DSD128",
    output_power: "30mW @ 32Ω (3.5mm) / 60mW @ 32Ω (4.4mm)",
    recommendation: "Direct hardware flash via WebHID. Settings persist across reboots and mobile devices.",
  },
  {
    id: "bmasterx6_plug",
    name: "BASN BmasterX 6 Modular Type-C DSP Plug",
    brand: "BASN",
    chipset: "KTMicro / WalkPlay OEM DSP",
    architecture: "ktmicro_dsp",
    dac_type: "hardware_dsp",
    flashable: true,
    vid: 12722, pid: 273,
    resolution: "32-bit / 384 kHz",
    output_power: "28mW @ 32Ω",
    recommendation: "Direct hardware flash into cable termination. Aligns the 1DD+3BA+2PZT acoustic profile.",
  },
  {
    id: "fiio_ja11",
    name: "FiiO / JadeAudio JA11",
    brand: "FiiO",
    chipset: "KTMicro KT02H20",
    architecture: "ktmicro_dsp",
    dac_type: "hardware_dsp",
    flashable: true,
    vid: 10610, pid: 258,
    resolution: "32-bit / 384 kHz, DSD128",
    output_power: "30mW @ 32Ω",
    recommendation: "Direct hardware flash via WebHID. Supports digital reconstruction filter customization.",
  },
  {
    id: "moondrop_freedsp",
    name: "Moondrop FreeDSP / May / Chu II DSP",
    brand: "Moondrop",
    chipset: "Moondrop Custom 9-Band DSP",
    architecture: "moondrop_dsp",
    dac_type: "hardware_dsp",
    flashable: true,
    vid: 12722, pid: 274,
    resolution: "24-bit / 96 kHz",
    output_power: "30mW @ 32Ω",
    recommendation: "Direct 9-Band hardware flash via WebHID.",
  },
  {
    id: "jcally_jm12",
    name: "JCALLY JM12",
    brand: "JCALLY",
    chipset: "KTMicro KT02H20",
    architecture: "ktmicro_dsp",
    dac_type: "hardware_dsp",
    flashable: true,
    vid: 12722, pid: 273,
    resolution: "32-bit / 384 kHz",
    output_power: "30mW @ 32Ω",
    recommendation: "Direct hardware flash via WebHID.",
  },
  {
    id: "jcally_jm6_pro",
    name: "JCALLY JM6 Pro",
    brand: "JCALLY",
    chipset: "Conexant CX31993 + Maxim MAX97220",
    architecture: "conexant_fixed",
    dac_type: "fixed_mask_rom",
    flashable: false,
    vid: 1394, pid: 6920,
    resolution: "32-bit / 384 kHz, DSD256",
    output_power: "60mW @ 32Ω",
    recommendation: "DO NOT FLASH. Fixed mask ROM with OTP registers. Use PipeWire or Wavelet export below.",
  },
  {
    id: "apple_dongle",
    name: "Apple USB-C to 3.5mm Adapter (A2049 / A2155)",
    brand: "Apple",
    chipset: "Cirrus Logic Custom",
    architecture: "generic_uac2",
    dac_type: "host_dsp_only",
    flashable: false,
    vid: 1452, pid: 4362,
    resolution: "24-bit / 48 kHz",
    output_power: "31mW @ 32Ω (US) / 15mW (EU)",
    recommendation: "Fixed-function UAC2. Clean measurements. Use host-side DSP (PipeWire/Wavelet).",
  },
  {
    id: "moondrop_dawn_pro",
    name: "Moondrop Dawn Pro",
    brand: "Moondrop",
    chipset: "Dual Cirrus Logic CS43131",
    architecture: "generic_uac2",
    dac_type: "host_dsp_only",
    flashable: false,
    vid: 12230, pid: 1,
    resolution: "32-bit / 384 kHz, DSD256",
    output_power: "120mW @ 32Ω (4.4mm)",
    recommendation: "Audiophile dual CS43131 flagship. High dynamic range. Use host-side PipeWire/EqualizerAPO.",
  },
  {
    id: "cablecreation_2in1",
    name: "CableCreation 2-in-1 USB-C Audio & PD 100W",
    brand: "CableCreation",
    chipset: "Generic UAC1 Codec + VIA Labs PD Switch",
    architecture: "generic_uac1_pd",
    dac_type: "host_dsp_only",
    flashable: false,
    vid: 3034, pid: 16448,
    resolution: "16-bit / 48 kHz",
    output_power: "20mW @ 32Ω",
    recommendation: "100W PD charging splitter. 16-bit/48kHz fixed codec. No hardware PEQ flash. Use host DSP.",
  },
];

async function loadDacDatabase() {
  dacCatalog = DEFAULT_DACS;
  guardTable = null;
  renderDacDirectory();

  try {
    guardTable = setTable(await loadTable("dacs.json"));
    dacCatalog = guardTable.devices;
    renderDacDirectory();
  } catch (err) {
    // Fail closed: the embedded catalog is enough to show the directory, but writes
    // are refused until the guard can read the table.
    console.warn("Could not read dacs.json; UI catalog only, writes are refused:", err);
  }
}

export function findDacInDatabase(vid, pid, prodName = "") {
  if (!vid) return null;
  const catalog = dacCatalog.length > 0 ? dacCatalog : DEFAULT_DACS;
  const pLower = (prodName || "").toLowerCase().trim();

  // Pass 1: exact VID + PID with matching prodName
  if (pLower) {
    for (const d of catalog) {
      if (d.vid === vid && d.pid === pid) {
        const dName = (d.name || "").toLowerCase();
        const dBrand = (d.brand || "").toLowerCase();
        if (pLower.includes(dName) || dName.includes(pLower) || (dBrand && pLower.includes(dBrand))) {
          return d;
        }
      }
    }
  }

  // Pass 2: exact VID + PID match
  for (const d of catalog) {
    if (d.vid === vid && d.pid === pid && d.pid !== null && d.pid !== undefined) {
      return d;
    }
  }

  // Pass 3: VID match with prodName substring match
  if (pLower) {
    for (const d of catalog) {
      if (d.vid === vid) {
        const dName = (d.name || "").toLowerCase();
        const dBrand = (d.brand || "").toLowerCase();
        if (pLower.includes(dName) || dName.includes(pLower) || (dBrand && pLower.includes(dBrand))) {
          return d;
        }
      }
    }
  }

  // Pass 4: Wildcard VID match (where d.pid is null or undefined)
  for (const d of catalog) {
    if (d.vid === vid && (d.pid === null || d.pid === undefined)) {
      return d;
    }
  }

  return null;
}

export function renderDacDirectory(filter = null, query = null) {
  if (filter !== null) currentDacFilter = filter;
  const container = document.getElementById("dacGrid");
  if (!container) return;

  const searchInput = document.getElementById("dacSearchInput");
  const q = (query !== null ? query : (searchInput ? searchInput.value : "")).trim().toLowerCase();

  const filtered = dacCatalog.filter((d) => {
    if (currentDacFilter === "flashable" && !d.flashable) return false;
    if (currentDacFilter === "blocked" && d.dac_type !== "fixed_mask_rom") return false;
    if (currentDacFilter === "host" && d.dac_type !== "host_dsp_only") return false;
    if (currentDacFilter === "splitter" && d.architecture !== "generic_uac1_pd") return false;

    if (q) {
      const haystack = `${d.name} ${d.brand} ${d.chipset} ${d.architecture} ${d.resolution}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  const countAll = document.getElementById("dacCountAll");
  if (countAll) countAll.textContent = dacCatalog.length;

  container.innerHTML = "";
  if (filtered.length === 0) {
    container.innerHTML = `<div style="grid-column: 1/-1; padding: 1.5rem; text-align: center; color: var(--text-secondary); font-size: 0.9rem;">No DACs found matching your search.</div>`;
    return;
  }

  filtered.forEach((d) => {
    const card = document.createElement("div");
    card.className = "dac-card";

    let badgeHtml = "";
    if (d.flashable) {
      badgeHtml = `<span class="dac-badge-flash">Hardware Flashable</span>`;
    } else if (d.dac_type === "fixed_mask_rom") {
      badgeHtml = `<span class="dac-badge-blocked">Fixed Mask ROM</span>`;
    } else {
      badgeHtml = `<span class="dac-badge-host">Host DSP Only</span>`;
    }

    const safeName = escapeHtml(d.name || "");
    const safeBrand = escapeHtml(d.brand || "");
    const safeChipset = escapeHtml(d.chipset || "");
    const safeRes = escapeHtml(d.resolution || "");
    const safePower = escapeHtml(d.output_power || "");
    const safeRec = escapeHtml(d.recommendation || "");
    const safeVid = d.vid_hex ? escapeHtml(d.vid_hex) : "";
    const safePid = d.pid_hex ? escapeHtml(d.pid_hex) : "";
    const safePrice = d.price_usd !== undefined && d.price_usd !== null ? escapeHtml(d.price_usd) : "";
    const safeBands = (d.max_bands ?? d.hardware_bands) !== undefined ? escapeHtml(d.max_bands ?? d.hardware_bands) : "";
    const safeNotes = d.notes ? escapeHtml(d.notes) : "";

    card.innerHTML = `
      <div>
        <div class="dac-card-header">
          <div>
            <div class="dac-card-brand">${safeBrand}</div>
            <div class="dac-card-title">${safeName}</div>
          </div>
          ${badgeHtml}
        </div>
        <div class="dac-card-meta" style="margin-top: 0.5rem;">
          <div><span class="dac-chipset-tag">${safeChipset}</span></div>
          ${safeRes ? `<div style="margin-top: 0.35rem; font-size: 0.75rem;"><strong>Resolution:</strong> ${safeRes}</div>` : ""}
          ${safePower ? `<div style="font-size: 0.75rem;"><strong>Output Power:</strong> ${safePower}</div>` : ""}
          ${safeVid ? `<div style="font-size: 0.75rem;"><strong>VID/PID:</strong> ${safeVid}:${safePid}</div>` : ""}
          ${safePrice ? `<div style="font-size: 0.75rem;"><strong>Price:</strong> $${safePrice}</div>` : ""}
          ${safeBands ? `<div style="font-size: 0.75rem;"><strong>Max Bands:</strong> ${safeBands}</div>` : ""}
          ${safeNotes ? `<div style="font-size: 0.75rem;"><strong>Notes:</strong> ${safeNotes}</div>` : ""}
        </div>
      </div>
      <div class="dac-card-footer">
        ${safeRec}
      </div>
    `;
    container.appendChild(card);
  });
}

// ── Toast Notification ────────────────────────────────────────────────────────
function showToast(msg) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.remove("show");
  }, 3200);
}

// ── Preset Object Loader ──────────────────────────────────────────────────────
export function loadPresetObject(parsed, defaultName = "custom_preset") {
  if (!parsed || !Array.isArray(parsed.bands)) {
    throw new Error("Invalid preset format: missing 'bands' array.");
  }
  currentPreset = {
    name: parsed.name || defaultName,
    slug: (parsed.slug || defaultName.replace(/[^a-z0-9_-]/gi, "_")).toLowerCase(),
    description: parsed.description || "Imported custom PEQ preset",
    preamp: typeof parsed.preamp === "number" ? parsed.preamp : 0.0,
    bands: parsed.bands.map((b, i) => ({
      type: b.type || "PK",
      freq: Number(b.freq) || 1000,
      gain: Number(b.gain) || 0,
      q: Number(b.q) || 1.0,
      enabled: b.enabled !== false,
    })),
  };
  return currentPreset;
}

export function getCurrentPreset() {
  return currentPreset;
}

// ── Initialization ────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  // ── Light / Dark Theme Toggle (Modern Web Guidance Pattern) ───────────────
  const metaColorScheme = document.querySelector('meta[name="color-scheme"]');
  const btnThemeToggle = document.getElementById("btnThemeToggle");

  function getActiveRenderedScheme() {
    const content = metaColorScheme?.content || "light dark";
    if (content === "dark" || content === "light") return content;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function updateThemeButtonUI() {
    const active = getActiveRenderedScheme();
    if (btnThemeToggle) {
      btnThemeToggle.setAttribute(
        "aria-label",
        `Theme: Switch to ${active === "dark" ? "Light" : "Dark"} Mode`
      );
      btnThemeToggle.setAttribute(
        "title",
        `Theme: Switch to ${active === "dark" ? "Light" : "Dark"} Mode`
      );
    }
  }

  updateThemeButtonUI();

  btnThemeToggle?.addEventListener("click", () => {
    if (!metaColorScheme) return;
    const currentDark = getActiveRenderedScheme() === "dark";
    const nextScheme = currentDark ? "light" : "dark";
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    if ((systemDark && nextScheme === "dark") || (!systemDark && nextScheme === "light")) {
      metaColorScheme.content = "light dark";
      try {
        localStorage.removeItem("color-scheme");
      } catch (_) {}
    } else {
      metaColorScheme.content = nextScheme;
      try {
        localStorage.setItem("color-scheme", nextScheme);
      } catch (_) {}
    }
    updateThemeButtonUI();
    showToast(`Switched to ${nextScheme === "dark" ? "🌙 Dark" : "☀️ Light"} Mode`);
  });

  window.addEventListener("storage", (e) => {
    if (e.key === "color-scheme" && metaColorScheme) {
      metaColorScheme.content = e.newValue || "light dark";
      updateThemeButtonUI();
    }
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    updateThemeButtonUI();
  });

  // Initialize Rust WebAssembly DSP Core
  initWasmEngine().then((ready) => {
    if (ready) {
      const badge = document.getElementById("wasmBadge");
      if (badge) badge.classList.add("active");
    }
  });

  if (currentPreset.slot_id) {
    const selSlot = document.getElementById("selHardwareSlot");
    if (selSlot) selSlot.value = String(currentPreset.slot_id);
  }

  tryLoadPresetFromUrl();
  resetMacroControls(currentPreset.bands);
  updateEqCapsBadge();

  buildControlsUI();
  renderCurve();

  // Mobile Android WebHID Advisory Banner Check
  const mobileBanner = document.getElementById("mobileWebHidBanner");
  const isMobileUa = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || "");
  if (mobileBanner && !navigator.hid && isMobileUa) {
    mobileBanner.classList.add("visible");
  }
  const btnMobileWavelet = document.getElementById("btnMobileWaveletShortcut");
  if (btnMobileWavelet) {
    btnMobileWavelet.addEventListener("click", exportWaveletGraphicEq);
  }

  // Hardware Band Architecture Switcher (5-Band KT02H20 vs 9-Band Moondrop FreeDSP)
  const selHwBands = document.getElementById("selHardwareBandCount");
  if (selHwBands) {
    selHwBands.addEventListener("change", (e) => {
      const count = parseInt(e.target.value, 10) || 5;
      setHardwareBandArchitecture(count);
      showToast(`Switched DSP matrix to ${activeHardwareBands}-Band mode.`);
    });
  }

  // Preset clicks & keyboard activation
  document.querySelectorAll(".preset-card").forEach((card) => {
    const activatePreset = () => {
      selectPreset(card.getAttribute("data-preset"));
      resetMacroControls(currentPreset.bands);
    };
    card.addEventListener("click", activatePreset);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        activatePreset();
      }
    });
  });

  // Target Customizer Macro Sliders & Coupler Smoother
  function handleMacroSliderInput() {
    const sBass = document.getElementById("sliderMacroBass");
    const sEar = document.getElementById("sliderMacroEar");
    const sTreb = document.getElementById("sliderMacroTreble");
    const lBass = document.getElementById("lblMacroBass");
    const lEar = document.getElementById("lblMacroEar");
    const lTreb = document.getElementById("lblMacroTreble");

    macroState.bass = sBass ? parseFloat(sBass.value) || 0.0 : 0.0;
    macroState.earGain = sEar ? parseFloat(sEar.value) || 0.0 : 0.0;
    macroState.treble = sTreb ? parseFloat(sTreb.value) || 0.0 : 0.0;

    if (lBass) lBass.textContent = `${macroState.bass > 0 ? "+" : ""}${macroState.bass.toFixed(1)} dB`;
    if (lEar) lEar.textContent = `${macroState.earGain > 0 ? "+" : ""}${macroState.earGain.toFixed(1)} dB`;
    if (lTreb) lTreb.textContent = `${macroState.treble > 0 ? "+" : ""}${macroState.treble.toFixed(1)} dB`;

    if (!macroBaselineBands || macroBaselineBands.length !== currentPreset.bands.length) {
      macroBaselineBands = currentPreset.bands.map((b) => ({ ...b }));
    }

    currentPreset.bands = applyMacroAdjustments(
      macroBaselineBands,
      macroState.bass,
      macroState.earGain,
      macroState.treble
    );
    currentPreset.bands.forEach((_, idx) => syncBandControls(idx));
    renderCurve();
    triggerAutoApply();
  }

  document.getElementById("sliderMacroBass")?.addEventListener("input", handleMacroSliderInput);
  document.getElementById("sliderMacroEar")?.addEventListener("input", handleMacroSliderInput);
  document.getElementById("sliderMacroTreble")?.addEventListener("input", handleMacroSliderInput);

  document.getElementById("btnResetMacros")?.addEventListener("click", () => {
    if (macroBaselineBands && macroBaselineBands.length === currentPreset.bands.length) {
      currentPreset.bands = macroBaselineBands.map((b) => ({ ...b }));
    }
    resetMacroControls(currentPreset.bands);
    currentPreset.bands.forEach((_, idx) => syncBandControls(idx));
    renderCurve();
    triggerAutoApply();
    showToast("Macro offsets reset to 0.0 dB.");
  });

  document.getElementById("btnSmoothCoupler")?.addEventListener("click", () => {
    currentPreset.bands = smoothCouplerBiquads(currentPreset.bands);
    resetMacroControls(currentPreset.bands);
    currentPreset.bands.forEach((_, idx) => syncBandControls(idx));
    renderCurve();
    triggerAutoApply();
    showToast("✨ Smoothed 711 coupler resonance notch to Q=1.4 for natural treble!");
  });

  // Community Database Search
  const dbInput = document.getElementById("dbSearchInput");
  const btnDbSearch = document.getElementById("btnDbSearch");
  const dbSourceFilter = document.getElementById("dbSourceFilter");

  let dbSearchTimer = null;
  if (dbInput) {
    dbInput.addEventListener("input", () => {
      clearTimeout(dbSearchTimer);
      dbSearchTimer = setTimeout(performDatabaseSearch, 300);
    });
    dbInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(dbSearchTimer);
        performDatabaseSearch();
      }
    });
  }

  if (btnDbSearch) {
    btnDbSearch.addEventListener("click", performDatabaseSearch);
  }

  if (dbSourceFilter) {
    dbSourceFilter.addEventListener("change", performDatabaseSearch);
  }

  document.querySelectorAll(".quick-tag[data-query]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-query");
      if (dbInput && q) {
        dbInput.value = q;
        performDatabaseSearch();
      }
    });
  });

  // Action Buttons
  document.getElementById("btnConnect")?.addEventListener("click", connectDac);
  document.getElementById("btnApply")?.addEventListener("click", () => applyToDevice(false));
  document.getElementById("btnReadDac")?.addEventListener("click", () => readFromDevice(false));
  document.getElementById("btnSavePreset")?.addEventListener("click", exportBackupPreset);
  document.getElementById("btnShareUrl")?.addEventListener("click", sharePresetUrl);
  document.getElementById("btnRestoreStock")?.addEventListener("click", restoreStockBackup);
  document.getElementById("btnClearFlash")?.addEventListener("click", clearDeviceFlash);
  document.getElementById("btnFlash")?.addEventListener("click", () => applyToDevice(true));

  // Load Preset File (.json)
  const fileInput = document.getElementById("fileInputPreset");
  document.getElementById("btnLoadPreset")?.addEventListener("click", () => fileInput?.click());
  const lblLoadPreset = document.getElementById("lblLoadPreset");
  lblLoadPreset?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput?.click();
    }
  });
  fileInput?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (jsonErr) {
        // Fall back to GraphWorks / Equalizer APO / Peace / CSV parser
        parsed = parseParametricEq(text, file.name.replace(/\.[^/.]+$/, ""));
      }
      loadPresetObject(parsed, file.name.replace(/\.[^/.]+$/, ""));
      if (parsed.slot_id) {
        const selSlot = document.getElementById("selHardwareSlot");
        if (selSlot) selSlot.value = String(parsed.slot_id);
      }
      if (parsed.dac_filter) {
        const selDac = document.getElementById("selDacFilter");
        if (selDac) {
          for (let opt of selDac.options) {
            if (opt.text.toLowerCase().includes(String(parsed.dac_filter).toLowerCase()) || opt.value === String(parsed.dac_filter)) {
              selDac.value = opt.value;
              break;
            }
          }
        }
      }
      if (currentPreset.bands.length > activeHardwareBands) {
        currentPreset.fullBands = [...currentPreset.bands];
        referenceTargetCurve = {
          name: `${currentPreset.name} (${currentPreset.bands.length}-Band Target)`,
          bands: [...currentPreset.bands],
          preamp: currentPreset.preamp,
        };
        showTargetOverlay = true;
        currentPreset.bands = decimateBands(currentPreset.bands, activeHardwareBands);
        showToast(`Imported ${currentPreset.fullBands.length}-band curve: optimized into ${activeHardwareBands} hardware biquads.`);
      } else {
        referenceTargetCurve = null;
        showToast(`Loaded preset "${currentPreset.name}" (${currentPreset.bands.length} bands)`);
      }

      resetMacroControls(currentPreset.bands);
      buildControlsUI();
      renderCurve();
      triggerAutoApply();
    } catch (err) {
      console.error("Load preset error:", err);
      showToast(`Failed to load preset: ${err.message}`);
    } finally {
      e.target.value = "";
    }
  });

  document.getElementById("btnExportPw")?.addEventListener("click", exportPipeWireConf);
  document.getElementById("btnExportApo")?.addEventListener("click", exportEqualizerApo);
  document.getElementById("btnExportWavelet")?.addEventListener("click", exportWaveletGraphicEq);
  document.getElementById("btnExportQudelix")?.addEventListener("click", exportQudelixProfile);

  document.getElementById("btnTestNoise")?.addEventListener("click", toggleTestNoise);

  document.getElementById("selDacFilter")?.addEventListener("change", () => triggerAutoApply());
  document.getElementById("selHardwareSlot")?.addEventListener("change", async (e) => {
    const slotId = parseInt(e.target.value, 10) || 3;
    const btnRestore = document.getElementById("btnRestoreStock");
    if (btnRestore && connectedHidDevice) {
      btnRestore.style.display = hasStockBackup(connectedHidDevice, slotId) ? "inline-flex" : "none";
    }
    if (connectedHidDevice && !isDemoMode && !isMoondropFreeDsp(connectedHidDevice) && !isWalkplayDsp(connectedHidDevice)) {
      try {
        await sendHidReport(0x4b, 0x24, 0x57, slotId & 0xff, 0, 0, 0);
        showToast(`Hardware switched to Slot ${slotId}. Reading slot registers...`);
        await readFromDevice(true);
      } catch (err) {
        console.warn("Slot change error:", err);
      }
    } else {
      triggerAutoApply();
    }
  });

  // Auto Headroom Button
  const btnAutoPreamp = document.getElementById("btnAutoPreamp");
  if (btnAutoPreamp) {
    btnAutoPreamp.addEventListener("click", () => {
      const rec = calculateRecommendedPreamp(currentPreset.bands);
      currentPreset.preamp = rec;
      document.getElementById("sliderPreamp").value = rec;
      document.getElementById("lblPreamp").textContent = `${rec > 0 ? "+" : ""}${rec.toFixed(1)} dB`;
      renderCurve();
      triggerAutoApply();
      showToast(`Auto-Headroom set: ${rec > 0 ? "+" : ""}${rec.toFixed(1)} dB (0.5 dB intersample headroom)`);
    });
  }

  // Demo Mode Switch
  document.getElementById("chkDemoMode")?.addEventListener("change", (e) => {
    isDemoMode = e.target.checked;
    if (isDemoMode) {
      updateDeviceBadge("connected", "Virtual KT02H20 (Demo Simulation)");
      updateFlashCounterBadge(null);
      updateEqCapsBadge();
      document.getElementById("btnApply").disabled = false;
      document.getElementById("btnReadDac").disabled = false;
      document.getElementById("btnFlash").disabled = false;
      showToast("Demo Mode enabled: Simulated register writes active.");
    } else if (!connectedHidDevice) {
      updateDeviceBadge("disconnected", "No DAC Connected");
      updateFlashCounterBadge(null);
      updateEqCapsBadge();
      document.getElementById("btnApply").disabled = true;
      document.getElementById("btnReadDac").disabled = true;
      document.getElementById("btnFlash").disabled = true;
    } else {
      updateEqCapsBadge(connectedHidDevice);
    }
  });

  // Target Curve Overlay Toggle & Preference Bounds Controls
  const chkShowTarget = document.getElementById("chkShowTarget");
  if (chkShowTarget) {
    chkShowTarget.addEventListener("change", (e) => {
      showTargetOverlay = e.target.checked;
      renderCurve();
    });
  }

  const selTargetCurve = document.getElementById("selTargetCurve");
  if (selTargetCurve) {
    selTargetCurve.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val === "none" || !PRESETS[val]) {
        referenceTargetCurve = null;
      } else {
        referenceTargetCurve = PRESETS[val];
      }
      renderCurve();
    });
  }

  const selPreferenceTolerance = document.getElementById("selPreferenceTolerance");
  if (selPreferenceTolerance) {
    selPreferenceTolerance.addEventListener("change", () => renderCurve());
  }

  const btnNormalizeHeadroom = document.getElementById("btnNormalizeHeadroom");
  if (btnNormalizeHeadroom) {
    btnNormalizeHeadroom.addEventListener("click", () => {
      currentPreset.bands = normalizeHeadroom(currentPreset.bands, 0.0);
      buildControlsUI();
      renderCurve();
      triggerAutoApply();
      showToast("Headroom normalized: Positive boosts attenuated to 0 dBFS.");
    });
  }

  // ── Web Audio Tone Generator & Resonance Sweep Tool Handlers ────────────
  const SWEEP_RANGES = {
    full: { start: 20, end: 20000, steps: 220, label: "Full Spectrum (20 Hz – 20 kHz)" },
    canal: { start: 4000, end: 10000, steps: 120, label: "Canal Peak Finder (4 kHz – 10 kHz)" },
    bass: { start: 20, end: 300, steps: 120, label: "Sub-Bass & Mid-Bass (20 Hz – 300 Hz)" },
  };

  const sliderToneFreq = document.getElementById("sliderToneFreq");
  const lblToneFreq = document.getElementById("lblToneFreq");
  const selToneMode = document.getElementById("selToneMode");

  function startSweepWithRange(modeKey) {
    const btnSweep = document.getElementById("btnToneSweep");
    const cfg = SWEEP_RANGES[modeKey] || SWEEP_RANGES.canal;

    startTone(cfg.start, true);
    if (sliderToneFreq) sliderToneFreq.value = Math.round(cfg.start);
    if (lblToneFreq) lblToneFreq.textContent = `${Math.round(cfg.start)} Hz`;
    if (btnSweep) {
      btnSweep.textContent = "⏹ Stop Sweep";
      btnSweep.classList.add("active");
    }

    let currentSweepFreq = cfg.start;
    const stepRatio = Math.pow(cfg.end / cfg.start, 1 / cfg.steps);

    sweepInterval = setInterval(() => {
      currentSweepFreq *= stepRatio;
      if (currentSweepFreq >= cfg.end) {
        currentSweepFreq = cfg.start;
      }
      const rounded = Math.round(currentSweepFreq);
      if (sliderToneFreq) sliderToneFreq.value = rounded;
      if (lblToneFreq) lblToneFreq.textContent = `${rounded} Hz`;
      if (toneOsc && audioCtx && isToneActive) {
        toneOsc.frequency.setValueAtTime(currentSweepFreq, audioCtx.currentTime);
      }
      updateTonePlayhead(currentSweepFreq);
    }, 50);
  }

  if (sliderToneFreq) {
    sliderToneFreq.addEventListener("input", (e) => {
      const f = parseFloat(e.target.value);
      if (lblToneFreq) lblToneFreq.textContent = `${Math.round(f)} Hz`;
      if (toneOsc && audioCtx && isToneActive) {
        toneOsc.frequency.setValueAtTime(f, audioCtx.currentTime);
      }
      updateTonePlayhead(f);
    });
  }

  if (selToneMode) {
    selToneMode.addEventListener("change", (e) => {
      const mode = e.target.value;
      if (mode === "selected") {
        if (sweepInterval) {
          const f = sliderToneFreq ? parseFloat(sliderToneFreq.value) || 1000 : 1000;
          startTone(f);
          showToast(`Switched to manual Selected Frequency (${Math.round(f)} Hz)`);
        }
      } else if (SWEEP_RANGES[mode]) {
        const cfg = SWEEP_RANGES[mode];
        if (!isToneActive) {
          if (sliderToneFreq) sliderToneFreq.value = cfg.start;
          if (lblToneFreq) lblToneFreq.textContent = `${cfg.start} Hz`;
        } else if (sweepInterval) {
          startSweepWithRange(mode);
          showToast(`Switched sweep to ${cfg.label}`);
        }
      }
    });
  }

  const sliderToneVol = document.getElementById("sliderToneVol");
  const lblToneVol = document.getElementById("lblToneVol");
  if (sliderToneVol) {
    sliderToneVol.addEventListener("input", (e) => {
      const v = parseFloat(e.target.value);
      const db = 20 * Math.log10(v);
      if (lblToneVol) lblToneVol.textContent = `${db.toFixed(0)} dB`;
      if (masterVolGainNode && audioCtx && (isToneActive || isPlayingNoise)) {
        masterVolGainNode.gain.setValueAtTime(isPlayingNoise ? v * 1.2 : v, audioCtx.currentTime);
      }
    });
  }

  document.getElementById("btnTonePlay")?.addEventListener("click", () => {
    if (isToneActive && !sweepInterval) {
      stopAudioGenerators();
    } else {
      const f = sliderToneFreq ? parseFloat(sliderToneFreq.value) || 7000 : 7000;
      startTone(f);
    }
  });

  document.getElementById("btnPinkNoise")?.addEventListener("click", () => {
    toggleTestNoise();
  });

  document.getElementById("btnToneSweep")?.addEventListener("click", () => {
    if (sweepInterval) {
      stopAudioGenerators();
      return;
    }
    let mode = selToneMode ? selToneMode.value : "canal";
    if (mode === "selected") {
      mode = "full";
      if (selToneMode) selToneMode.value = "full";
    }
    startSweepWithRange(mode);
  });

  // Generator Guide Dialog Handlers
  const toneGuideDialog = document.getElementById("toneGuideDialog");
  document.getElementById("btnOpenToneGuide")?.addEventListener("click", () => {
    if (toneGuideDialog) {
      toneGuideDialog.showModal();
    }
  });

  document.getElementById("btnCloseToneGuide")?.addEventListener("click", () => {
    toneGuideDialog?.close();
  });

  document.getElementById("btnGotItToneGuide")?.addEventListener("click", () => {
    toneGuideDialog?.close();
  });

  document.getElementById("btnSnapBand")?.addEventListener("click", () => {
    const currentFreq = sliderToneFreq ? parseFloat(sliderToneFreq.value) || 7000 : 7000;
    if (!currentPreset.bands || currentPreset.bands.length === 0) return;

    let closestIdx = 0;
    let minDiff = Infinity;
    currentPreset.bands.forEach((b, i) => {
      const diff = Math.abs(b.freq - currentFreq);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = i;
      }
    });

    currentPreset.bands[closestIdx].freq = Math.round(currentFreq);
    buildControlsUI();
    renderCurve();
    triggerAutoApply();
    showToast(`Band ${closestIdx + 1} snapped to ${Math.round(currentFreq)} Hz`);
  });

  // DAC Hardware Database Directory
  loadDacDatabase();

  const dacSearchInput = document.getElementById("dacSearchInput");
  if (dacSearchInput) {
    dacSearchInput.addEventListener("input", () => {
      renderDacDirectory(null, dacSearchInput.value);
    });
  }

  document.querySelectorAll(".dac-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".dac-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      renderDacDirectory(pill.getAttribute("data-filter"));
    });
  });

  // ── WebHID Hotplug & "Remember Connected Devices" Lifecycle ───────────────
  const chkAutoReconnect = document.getElementById("chkAutoReconnect");
  if (chkAutoReconnect) {
    const savedPref = localStorage.getItem("dac_auto_reconnect");
    chkAutoReconnect.checked = savedPref === null ? true : savedPref === "true";
    chkAutoReconnect.addEventListener("change", (e) => {
      localStorage.setItem("dac_auto_reconnect", e.target.checked);
    });
  }

  if (navigator.hid) {
    const shouldAuto = localStorage.getItem("dac_auto_reconnect") !== "false";
    if (shouldAuto) {
      navigator.hid
        .getDevices()
        .then(async (paired) => {
          if (paired && paired.length > 0 && !connectedHidDevice) {
            const matched = paired.find(
              (d) => KTMICRO_FILTERS.some((f) => f.vendorId === d.vendorId) || Boolean(entryFor(d))
            );
            if (matched) {
              await initializeDevice(matched, true);
              showToast(`Auto-reconnected to ${matched.productName || "USB DAC"}`);
            }
          }
        })
        .catch((err) => {
          console.warn("Silent WebHID auto-connect error:", err);
        });
    }

    navigator.hid.addEventListener("connect", async (e) => {
      const allowAuto = localStorage.getItem("dac_auto_reconnect") !== "false";
      if (allowAuto && !connectedHidDevice && !isRebootingPostCommit) {
        await initializeDevice(e.device, false);
      }
    });

    navigator.hid.addEventListener("disconnect", (e) => {
      if (connectedHidDevice === e.device) {
        handleDeviceDisconnect("DAC unplugged from USB port.");
      }
    });
  }

  const svgEl = document.getElementById("eqSvg");
  if (window.ResizeObserver && svgEl) {
    let lastSvgWidth = svgEl.clientWidth;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.round(entry.contentRect.width);
        if (w > 0 && Math.abs(w - lastSvgWidth) >= 2) {
          lastSvgWidth = w;
          renderCurve();
        }
      }
    });
    ro.observe(svgEl);
  } else {
    window.addEventListener("resize", () => renderCurve());
  }
});
