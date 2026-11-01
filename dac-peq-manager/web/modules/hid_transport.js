/**
 * WebHID Transport, Register Framing (KTMicro KT02H20 & Moondrop FreeDSP),
 * Firmware Clock Quirk Detection, NVRAM Wear Tracker, and Event-Driven USB Re-Enumeration.
 */
import { entryFor } from "./safety_guard.js";

export const KTMICRO_FILTERS = [
  { vendorId: 0x31b2 }, // KTMicro / Kiwi Ears Allegro Mini / Moondrop FreeDSP
  { vendorId: 0x2972 }, // FiiO JA11
  { vendorId: 0x3302 }, // KTMicro / Kiwi Ears OEM Type-C DACs
  { vendorId: 0x0bda, productId: 0x0023 }, // WalkPlay OEM
  { vendorId: 0x0661 },
  { vendorId: 0x262a },
];

export function isMoondropFreeDsp(dev) {
  const entry = entryFor(dev);
  return Boolean(entry) && entry.architecture === "moondrop_dsp";
}

export function isWalkplayDsp(dev) {
  const entry = entryFor(dev);
  return Boolean(entry) && entry.architecture === "walkplay_dsp";
}

// ── NVRAM Flash Wear-Out Health Tracker ───────────────────────────────────────
export function getFlashWearKey(dev) {
  if (!dev) return "dac_flash_history_generic";
  const vid = (dev.vendorId || 0).toString(16).toLowerCase().padStart(4, "0");
  const pid = (dev.productId || 0).toString(16).toLowerCase().padStart(4, "0");
  return `dac_flash_history_${vid}_${pid}`;
}

export function getFlashStats(dev, storage = globalThis.localStorage) {
  if (!storage) return { total: 0, timestamps: [] };
  const key = getFlashWearKey(dev);
  try {
    const raw = storage.getItem(key);
    if (!raw) return { total: 0, timestamps: [] };
    const parsed = JSON.parse(raw);
    const total = typeof parsed.total === "number" ? parsed.total : (typeof parsed === "number" ? parsed : 0);
    const timestamps = Array.isArray(parsed.timestamps) ? parsed.timestamps : [];
    return { total, timestamps };
  } catch {
    return { total: 0, timestamps: [] };
  }
}

export function recordFlashCommit(dev, storage = globalThis.localStorage) {
  const key = getFlashWearKey(dev);
  const stats = getFlashStats(dev, storage);
  const now = Date.now();
  stats.total += 1;
  stats.timestamps.push(now);
  const oneDayAgo = now - 24 * 3600 * 1000;
  stats.timestamps = stats.timestamps.filter((t) => t > oneDayAgo);
  if (storage) {
    try {
      storage.setItem(key, JSON.stringify(stats));
    } catch (e) {
      console.warn("Could not save flash stats to localStorage:", e);
    }
  }
  return stats;
}

// ── Factory Stock Backup Tracker ──────────────────────────────────────────────
export function getStockBackupKey(dev, slotId = 3) {
  if (!dev) return `dac_stock_backup_generic_slot${slotId}`;
  const vid = (dev.vendorId || 0).toString(16).toLowerCase().padStart(4, "0");
  const pid = (dev.productId || 0).toString(16).toLowerCase().padStart(4, "0");
  return `dac_stock_backup_${vid}_${pid}_slot${slotId}`;
}

export function getStockBackup(dev, slotId = 3, storage = globalThis.localStorage) {
  if (!storage) return null;
  const key = getStockBackupKey(dev, slotId);
  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveStockBackup(dev, slotId = 3, preset, storage = globalThis.localStorage) {
  if (!storage || !preset) return false;
  const key = getStockBackupKey(dev, slotId);
  try {
    if (!storage.getItem(key)) {
      storage.setItem(key, JSON.stringify(preset));
      return true;
    }
  } catch (e) {
    console.warn("Could not save stock backup to localStorage:", e);
  }
  return false;
}

export function hasStockBackup(dev, slotId = 3, storage = globalThis.localStorage) {
  if (!storage) return false;
  const key = getStockBackupKey(dev, slotId);
  return Boolean(storage.getItem(key));
}

// ── Firmware Clock Divisor Quirk Prober ───────────────────────────────────────
// NOTE: The W3C WebHID standard HIDDevice interface exposes vendorId, productId,
// and productName, but does NOT expose bcdDevice or deviceVersion (audit credit: Captain Ødegard, Head-Fi).
// Therefore, WebHID cannot inspect the device firmware revision directly.
// We apply static heuristics based on VID/PID/product name:
//   - Moondrop FreeDSP (0x31b2:0x0112): Standard clocking (requiresCompensate2X = false).
//   - FiiO JA11 (0x2972): Production firmware (v1.8+) corrected the clock bug internally,
//     so default to native clocking (requiresCompensate2X = false).
//   - Kiwi Ears Allegro Mini / generic KT02H20 (0x31b2:0x0111, 0x0bda:0x0023, "allegro"):
//     Default to requiresCompensate2X = true.
// For all KT02H20 devices, the web UI provides an explicit "2X Clock Divisor (KT02H20)"
// checkbox (#chkCompensate2X) so the user can override this heuristic if their specific
// firmware revision behaves differently.
export function detectFirmwareQuirks(dev) {
  if (!dev) return { requiresCompensate2X: false, reason: "No device" };
  const entry = entryFor(dev);
  if (entry && (entry.quirks || []).includes("compensate2x")) {
    return { requiresCompensate2X: true, reason: `${entry.name}: 2X clock divisor compensation (toggleable via checkbox)` };
  }
  if (!entry) return { requiresCompensate2X: false, reason: "Device not in the table: no clocking assumption" };
  return { requiresCompensate2X: false, reason: `${entry.name}: standard clocking` };
}

// ── Packet Encoders ───────────────────────────────────────────────────────────
export function encodeKtMicroBandPackets(bandIndex, band, compensate2X = false) {
  const typeMap = { PK: 0, LSQ: 3, HSQ: 4 };
  let freq = Number(band.freq ?? 1000.0);
  if (compensate2X) freq = freq / 2.0;

  const effGain = band.enabled === false ? 0.0 : Number(band.gain ?? 0.0);
  let gainScaled = Math.round(effGain * 10);
  if (gainScaled < 0) gainScaled += 0x10000;
  const gainLo = gainScaled & 0xff;
  const gainHi = (gainScaled >> 8) & 0xff;

  const freqVal = Math.round(freq);
  const freqLo = freqVal & 0xff;
  const freqHi = (freqVal >> 8) & 0xff;

  const qScaled = Math.round(Number(band.q ?? 1.0) * 1000);
  const qLo = qScaled & 0xff;
  const qHi = (qScaled >> 8) & 0xff;

  const typeVal = typeMap[String(band.type || "PK").toUpperCase()] ?? 0;

  const regGf = 0x26 + bandIndex * 2;
  const regQ = regGf + 1;

  return {
    regGf,
    regQ,
    gfData: [gainLo, gainHi, freqLo, freqHi],
    qData: [qLo, qHi, typeVal, 0],
  };
}

export function encodeMoondropReport(bands, preampDb, commitFlash = false) {
  const typeMap = { PK: 0, LSQ: 1, HSQ: 2 };
  const cmdByte = commitFlash ? 0x21 : 0x20;
  const payload = new Uint8Array(64);
  const activeBands = bands.slice(0, 9);

  payload[0] = cmdByte;
  payload[1] = activeBands.length & 0xff;

  let preampScaled = Math.round(Number(preampDb ?? 0.0) * 100.0);
  if (preampScaled < 0) preampScaled += 0x10000;
  payload[2] = preampScaled & 0xff;
  payload[3] = (preampScaled >> 8) & 0xff;

  let offset = 4;
  for (const b of activeBands) {
    const ftype = typeMap[String(b.type || "PK").toUpperCase()] ?? 0;
    const freq = Math.round(Number(b.freq ?? 1000.0));
    const effGain = b.enabled === false ? 0.0 : Number(b.gain ?? 0.0);
    let gain = Math.round(effGain * 10.0);
    if (gain < 0) gain += 256;
    const qVal = Math.round(Number(b.q ?? 1.0) * 10.0) & 0xff;

    payload[offset] = ftype & 0xff;
    payload[offset + 1] = freq & 0xff;
    payload[offset + 2] = (freq >> 8) & 0xff;
    payload[offset + 3] = gain & 0xff;
    payload[offset + 4] = qVal & 0xff;
    offset += 5;
  }

  return payload;
}

// ── Event-Driven Post-Commit USB Re-Enumeration Watcher ───────────────────────
export function waitForUsbReenumeration(hidApi, filters = KTMICRO_FILTERS, timeoutMs = 4000, pollIntervalMs = 200) {
  if (!hidApi) return Promise.resolve(null);

  return new Promise((resolve) => {
    let settled = false;
    let pollTimer = null;
    let timeoutTimer = null;

    const cleanup = () => {
      settled = true;
      if (pollTimer) clearInterval(pollTimer);
      if (timeoutTimer) clearTimeout(timeoutTimer);
      if (typeof hidApi.removeEventListener === "function") {
        hidApi.removeEventListener("connect", onConnect);
      }
    };

    const onConnect = (e) => {
      if (settled) return;
      const dev = e && e.device;
      if (dev && filters.some((f) => f.vendorId === dev.vendorId)) {
        cleanup();
        resolve(dev);
      }
    };

    if (typeof hidApi.addEventListener === "function") {
      hidApi.addEventListener("connect", onConnect);
    }

    // Also poll getDevices() every 200ms after a 250ms initial reboot grace window
    setTimeout(() => {
      if (settled) return;
      pollTimer = setInterval(async () => {
        if (settled) return;
        try {
          const paired = await hidApi.getDevices();
          if (paired && paired.length > 0) {
            const matched = paired.find((d) => filters.some((f) => f.vendorId === d.vendorId));
            if (matched) {
              cleanup();
              resolve(matched);
            }
          }
        } catch {
          // Ignore transient USB bus enumeration errors during reboot
        }
      }, pollIntervalMs);
    }, 250);

    timeoutTimer = setTimeout(async () => {
      if (settled) return;
      let fallbackDevice = null;
      try {
        const paired = await hidApi.getDevices();
        if (paired && paired.length > 0) {
          fallbackDevice = paired.find((d) => filters.some((f) => f.vendorId === d.vendorId)) || null;
        }
      } catch {
        // Ignore
      }
      cleanup();
      resolve(fallbackDevice);
    }, timeoutMs);
  });
}

// ── Two-Way WebHID Register Readback ──────────────────────────────────────────

export async function sendKtMicroFilter(dev, filterVal = 1) {
  const entry = entryFor(dev);
  if (!entry || !(entry.quirks || []).includes("fiio_dac_filter")) {
    const vidHex = "0x" + ((dev && dev.vendorId) || 0).toString(16).toUpperCase();
    throw new Error(
      `SAFETY BLOCK: Register 0x11 (DAC Filter) is a FiiO hardware-DSP feature and is blocked on ${entry ? entry.name : "other hardware"} (${vidHex}) to prevent volume control lockout.`
    );
  }
  const REPORT_ID = 0x4b;
  const CMD_WRITE = 0x57;
  const payload = new Uint8Array([
    0x11, 0x00, 0x00, 0x00,
    CMD_WRITE, 0x00,
    filterVal & 0xff, 0x00, 0x00, 0x00,
  ]);
  return dev.sendReport(REPORT_ID, payload);
}

export async function sendKtMicroClearFlash(dev) {
  if (!dev) throw new Error("No device provided.");
  const REPORT_ID = 0x4b;
  const CMD_CLEAR = 0x43;
  const payload = new Uint8Array([
    0x00, 0x00, 0x00, 0x00,
    CMD_CLEAR, 0x00,
    0x00, 0x00, 0x00, 0x00,
  ]);
  return dev.sendReport(REPORT_ID, payload);
}

export function decodeKtMicroBandRegisters(gfResp, qResp, compensate2X = false) {
  const typeRevMap = { 0: "PK", 3: "LSQ", 4: "HSQ" };
  const gainRaw = gfResp[6] | (gfResp[7] << 8);
  const gainSigned = gainRaw > 0x7fff ? gainRaw - 0x10000 : gainRaw;
  const gainDb = Math.round((gainSigned / 10.0) * 10) / 10;

  let freqHz = gfResp[8] | (gfResp[9] << 8);
  if (compensate2X) freqHz = freqHz * 2.0;

  const qRaw = qResp[6] | (qResp[7] << 8);
  const qVal = Math.round((qRaw / 1000.0) * 100) / 100;
  const typeVal = qResp[8];
  const ftype = typeRevMap[typeVal] || "PK";

  return {
    type: ftype,
    freq: freqHz,
    gain: gainDb,
    q: qVal,
  };
}

export function readKtMicroRegister(dev, reg, timeoutMs = 500) {
  if (!dev) return Promise.reject(new Error("No device provided."));

  return new Promise((resolve, reject) => {
    let timer = null;

    const onInputReport = (event) => {
      const dv = event.data;
      if (!dv || dv.byteLength < 6) return;
      const respReg = dv.getUint8(0);
      const respCmd = dv.getUint8(4);

      if (respReg === reg && respCmd === 0x52) {
        cleanup();
        const bytes = [];
        for (let i = 0; i < dv.byteLength; i++) {
          bytes.push(dv.getUint8(i));
        }
        resolve(bytes);
      }
    };

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      try {
        dev.removeEventListener("inputreport", onInputReport);
      } catch (_) {}
    };

    timer = setTimeout(() => {
      cleanup();
      reject(new Error(`Timeout reading register 0x${reg.toString(16).toUpperCase().padStart(2, "0")}`));
    }, timeoutMs);

    try {
      dev.addEventListener("inputreport", onInputReport);
      const REPORT_ID = 0x4b;
      const CMD_READ = 0x52;
      const payload = new Uint8Array([
        reg & 0xff, 0x00, 0x00, 0x00,
        CMD_READ, 0x00,
        0x00, 0x00, 0x00, 0x00,
      ]);
      dev.sendReport(REPORT_ID, payload).catch((err) => {
        cleanup();
        reject(err);
      });
    } catch (err) {
      cleanup();
      reject(err);
    }
  });
}

export async function readKtMicroPeq(dev, options = {}) {
  const compensate2X = typeof options === "boolean" ? options : Boolean(options && options.compensate2X);
  const entry = entryFor(dev);
  const isNoPregain = Boolean(options && typeof options === "object" && options.noPregain) ||
    Boolean(entry && (entry.quirks || []).includes("noPregain"));

  // 1. Slot (0x24)
  let slotId = 3;
  try {
    const slotResp = await readKtMicroRegister(dev, 0x24);
    if (slotResp && slotResp.length > 6) slotId = slotResp[6];
  } catch (err) {
    console.warn("Could not read slot ID register 0x24:", err);
  }

  // 2. Preamp (0x66)
  let preampDb = 0.0;
  if (!isNoPregain) {
    try {
      const preampResp = await readKtMicroRegister(dev, 0x66);
      if (preampResp && preampResp.length > 6) {
        const raw = preampResp[6];
        const signed = raw > 127 ? raw - 256 : raw;
        preampDb = Math.round((signed / 2.0) * 10) / 10;
      }
    } catch (err) {
      console.warn("Could not read preamp register 0x66:", err);
    }
  }

  // 3. DAC filter (0x11)
  let dacFilter = null;
  const isFiio = Boolean(entry && (entry.quirks || []).includes("fiio_dac_filter")) && !isNoPregain;
  if (isFiio) {
    try {
      const filtResp = await readKtMicroRegister(dev, 0x11, 200);
      if (filtResp && filtResp.length > 6) dacFilter = filtResp[6];
      else dacFilter = 1;
    } catch (_) {
      dacFilter = 1;
    }
  }

  // 4. Five bands (0x26 - 0x2F)
  const bands = [];
  for (let i = 0; i < 5; i++) {
    const regGf = 0x26 + i * 2;
    const regQ = regGf + 1;
    const gfResp = await readKtMicroRegister(dev, regGf);
    const qResp = await readKtMicroRegister(dev, regQ);
    const bandData = decodeKtMicroBandRegisters(gfResp, qResp, compensate2X);
    bandData.index = i + 1;
    bands.push(bandData);
  }

  return {
    slotId,
    preamp: preampDb,
    dacFilter,
    bands,
  };
}

export function decodeMoondropReport(raw) {
  const typeRevMap = { 0: "PK", 1: "LSQ", 2: "HSQ" };
  const numBands = Math.min(9, Math.max(1, raw[1] || 1));
  let preampRaw = raw[2] | (raw[3] << 8);
  if (preampRaw > 32767) preampRaw -= 65536;
  const preampDb = Math.round((preampRaw / 100.0) * 10) / 10;

  const bands = [];
  let offset = 4;
  for (let i = 0; i < numBands; i++) {
    if (offset + 5 > raw.length) break;
    const typeVal = raw[offset];
    const ftype = typeRevMap[typeVal] || "PK";
    const freqHz = raw[offset + 1] | (raw[offset + 2] << 8);
    let gainRaw = raw[offset + 3];
    if (gainRaw > 127) gainRaw -= 256;
    const gainDb = Math.round((gainRaw / 10.0) * 10) / 10;
    const qRaw = raw[offset + 4];
    const qVal = Math.round((qRaw / 10.0) * 100) / 100;
    bands.push({
      index: i + 1,
      type: ftype,
      freq: freqHz,
      gain: gainDb,
      q: qVal,
    });
    offset += 5;
  }
  while (bands.length < 9) {
    bands.push({
      index: bands.length + 1,
      type: "PK",
      freq: 1000.0,
      gain: 0.0,
      q: 1.0,
    });
  }
  return { preamp: preampDb, bands };
}

export function readMoondropReport(dev, timeoutMs = 500) {
  if (!dev) return Promise.reject(new Error("No device provided."));

  return new Promise((resolve, reject) => {
    let timer = null;

    const onInputReport = (event) => {
      const dv = event.data;
      if (!dv || dv.byteLength < 4) return;
      cleanup();
      const bytes = [];
      for (let i = 0; i < dv.byteLength; i++) {
        bytes.push(dv.getUint8(i));
      }
      resolve(decodeMoondropReport(bytes));
    };

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      try {
        dev.removeEventListener("inputreport", onInputReport);
      } catch (_) {}
    };

    timer = setTimeout(() => {
      cleanup();
      reject(new Error("Timeout reading Moondrop FreeDSP status report."));
    }, timeoutMs);

    try {
      dev.addEventListener("inputreport", onInputReport);
      const req = new Uint8Array(64);
      req[0] = 0x22;
      dev.sendReport(0x00, req).catch((err) => {
        cleanup();
        reject(err);
      });
    } catch (err) {
      cleanup();
      reject(err);
    }
  });
}

// ── WalkPlay Scheme 11 & Scheme 16 Hardware Transport ─────────────────────────
export function computeWalkplayBiquad(freq, gain, q) {
  const bArr = new Uint8Array(20);
  if (Math.abs(gain) < 1e-6) return bArr;

  const A = Math.pow(10, gain / 40);
  const w0 = (freq * 2 * Math.PI) / 96000;
  const sinw0 = Math.sin(w0);
  const cosw0 = Math.cos(w0);
  const alpha = sinw0 / (2 * Math.max(q, 0.01));

  const b0 = 1 + alpha * A;
  const b1 = -2 * cosw0;
  const b2 = 1 - alpha * A;
  const a0 = 1 + alpha / A;
  const a1 = -2 * cosw0;
  const a2 = 1 - alpha / A;

  const scale = 1073741824; // 2^30
  const iArr = [1, a1 / a0, a2 / a0].map((d) => Math.round(d * scale));
  const iArr2 = [b0 / a0, b1 / a0, b2 / a0].map((d) => Math.round(d * scale));

  const quant = [iArr2[0], iArr2[1], iArr2[2], -iArr[1], -iArr[2]];
  const dv = new DataView(bArr.buffer);
  quant.forEach((v, idx) => {
    // No silent wrap: a value that does not fit int32 is refused, not truncated.
    if (v < -2147483648 || v > 2147483647) {
      throw new Error(`SAFETY GUARD: coefficient ${idx} out of int32 range (${v}) for freq ${freq} Hz, gain ${gain} dB, Q ${q}.`);
    }
    dv.setInt32(idx * 4, v, true);
  });
  return bArr;
}

export function encodeWalkplayFilterPacket(filterIdx, freq, gain, q, typeStr = "PK", slot = 101) {
  const typeMap = { LSQ: 1, PK: 2, PEAK: 2, PEAKING: 2, HSQ: 3, LP: 4, HP: 5 };
  const typeId = typeMap[(typeStr || "PK").toUpperCase()] || 2;

  const pkt = new Uint8Array(37);
  pkt[0] = 0x01; // WRITE
  pkt[1] = 0x09; // PEQ_VALUES
  pkt[2] = 0x18; // 24 bytes payload
  pkt[3] = 0x00;
  pkt[4] = filterIdx & 0xff;
  pkt[5] = 0x00;
  pkt[6] = 0x00;

  const biquad = computeWalkplayBiquad(freq, gain, q);
  pkt.set(biquad, 7);

  // Refuse, never clamp: the guard has already checked the accepted ranges, this
  // is the backstop that stops a value that cannot be packed.
  if (!Number.isFinite(freq) || freq <= 0 || freq > 65535) {
    throw new Error(`SAFETY GUARD: write rejected - band ${filterIdx}: freq ${freq} Hz cannot be packed (uint16).`);
  }
  if (!Number.isFinite(q) || q <= 0 || q * 256 > 65535) {
    throw new Error(`SAFETY GUARD: write rejected - band ${filterIdx}: Q ${q} cannot be packed (uint16 x256).`);
  }
  if (!Number.isFinite(gain) || gain * 256 < -32768 || gain * 256 > 32767) {
    throw new Error(`SAFETY GUARD: write rejected - band ${filterIdx}: gain ${gain} dB cannot be packed (int16 x256).`);
  }
  const freqU16 = Math.round(freq);
  const qU16 = Math.round(q * 256);
  const gainI16 = Math.round(gain * 256);

  const dv = new DataView(pkt.buffer);
  dv.setUint16(27, freqU16, true);
  dv.setUint16(29, qU16, true);
  dv.setInt16(31, gainI16, true);

  pkt[33] = typeId;
  pkt[34] = 0x00;
  pkt[35] = slot & 0xff;
  pkt[36] = 0x00; // END

  return pkt;
}

export function decodeWalkplayFilterPacket(bytes) {
  if (!bytes || bytes.length < 34) return null;
  const dv = new DataView(new Uint8Array(bytes).buffer);
  const filterIdx = bytes[4];
  const freqRaw = dv.getUint16(27, true);
  const qRaw = dv.getUint16(29, true);
  const gainRaw = dv.getInt16(31, true);
  const typeId = bytes[33];

  if (freqRaw === 0xffff && qRaw === 0xffff && gainRaw === -1) {
    return {
      index: filterIdx + 1,
      freq: 0,
      gain: 0,
      q: 0,
      type: "PK",
      disabled: true,
    };
  }

  const typeRevMap = { 1: "LSQ", 2: "PK", 3: "HSQ", 4: "LP", 5: "HP" };
  return {
    index: filterIdx + 1,
    freq: freqRaw,
    gain: Math.round((gainRaw / 256) * 100) / 100,
    q: Math.round((qRaw / 256) * 100) / 100,
    type: typeRevMap[typeId] || "PK",
    disabled: freqRaw === 0 || qRaw === 0,
  };
}

export function encodeWalkplayGlobalGain(gainDb) {
  const int8 = Math.round(Math.max(-128, Math.min(127, gainDb)));
  return new Uint8Array([0x01, 0x03, 0x02, 0x00, int8 & 0xff]);
}

export function getWalkplayCommitSequence() {
  return [
    new Uint8Array([0x01, 0x05, 0x00]),
    new Uint8Array([0x01, 0x17, 0x00]),
    new Uint8Array([0x01, 0x0a, 0x04, 0x00, 0x00, 0xff, 0xff, 0x00]),
    new Uint8Array([0x01, 0x01, 0x01, 0x00]),
  ];
}

export async function readWalkplayPeq(dev, maxFilters = 8, timeoutMs = 2000) {
  if (!dev) throw new Error("No device provided.");

  const filters = [];
  const onReport = (event) => {
    const dv = event.data;
    if (!dv || dv.byteLength < 34) return;
    const bytes = new Uint8Array(dv.buffer);
    if (bytes[1] !== 0x09) return; // PEQ_VALUES
    const filter = decodeWalkplayFilterPacket(bytes);
    if (filter) {
      filters[filter.index - 1] = filter;
    }
  };

  dev.addEventListener("inputreport", onReport);
  try {
    for (let i = 0; i < maxFilters; i++) {
      const req = new Uint8Array([0x80, 0x09, 0x00, 0x00, i, 0x00]);
      await dev.sendReport(0x4b, req);
      await new Promise((r) => setTimeout(r, 40));
    }

    // Await responses
    const start = Date.now();
    while (filters.filter(Boolean).length < maxFilters && Date.now() - start < timeoutMs) {
      await new Promise((r) => setTimeout(r, 50));
    }
  } finally {
    try {
      dev.removeEventListener("inputreport", onReport);
    } catch (_) {}
  }

  // Read global gain
  let preamp = 0;
  try {
    preamp = await readWalkplayGlobalGain(dev, 300);
  } catch (_) {}

  return { preamp, bands: filters.filter(Boolean) };
}

export function readWalkplayGlobalGain(dev, timeoutMs = 500) {
  return new Promise((resolve, reject) => {
    let timer = null;
    const onReport = (event) => {
      const dv = event.data;
      if (!dv || dv.byteLength < 5) return;
      const bytes = new Uint8Array(dv.buffer);
      if (bytes[0] === 0x80 && bytes[1] === 0x03) {
        cleanup();
        const int8 = new Int8Array([bytes[4]])[0];
        resolve(int8);
      }
    };

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      try {
        dev.removeEventListener("inputreport", onReport);
      } catch (_) {}
    };

    timer = setTimeout(() => {
      cleanup();
      reject(new Error("Timeout reading WalkPlay global gain."));
    }, timeoutMs);

    try {
      dev.addEventListener("inputreport", onReport);
      dev.sendReport(0x4b, new Uint8Array([0x80, 0x03, 0x00])).catch((err) => {
        cleanup();
        reject(err);
      });
    } catch (err) {
      cleanup();
      reject(err);
    }
  });
}
