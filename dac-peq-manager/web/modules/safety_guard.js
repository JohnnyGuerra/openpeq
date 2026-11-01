/**
 * Browser half of the safety guard. The device table (dacs.json) is the single
 * source of truth for the rule, and the browser reads it like Python and Rust do.
 *
 * The guard refuses a device whose identity it cannot confirm, and refuses a
 * coefficient outside the accepted range, before any packet is built. A rejected
 * write is aborted in full - never half-written. If the table cannot be read the
 * guard fails closed: nothing is written.
 *
 * Mirrors src/dac_peq/safety.py. Ranges are what this tool accepts, not a claim
 * about what the hardware tolerates.
 */

export const BLOCKED_ARCHITECTURES = new Set(["conexant_fixed"]);

export async function loadTable(url = "dacs.json") {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`SAFETY GUARD: cannot read the device table (${url}).`);
  const table = await res.json();
  if (!table || !table.devices || !table.ranges) {
    throw new Error(`SAFETY GUARD: device table ${url} has no 'devices' or 'ranges' section.`);
  }
  return table;
}

export function matchDevice(table, vid, pid, productName = "") {
  if (!table) return null;
  for (const d of table.devices) {
    if (d.vid === vid && d.pid === pid) return d;
  }
  const p = String(productName || "").toLowerCase().trim();
  if (p) {
    for (const d of table.devices) {
      if (d.vid === vid && String(d.name).toLowerCase().includes(p)) return d;
    }
  }
  return null;
}

export function rangesFor(table, architecture) {
  const r = table && table.ranges && table.ranges[architecture];
  if (!r) throw new Error(`SAFETY GUARD: no accepted ranges for architecture '${architecture}'.`);
  return r;
}

export function bandProblems(table, architecture, index, freq, gain, q) {
  const r = rangesFor(table, architecture);
  if (!r) throw new Error(`SAFETY GUARD: no accepted ranges for architecture '${architecture}'.`);
  const problems = [];
  if (!Number.isFinite(freq) || freq <= 0 || freq > r.freq_max_hz) {
    problems.push(`band ${index}: freq ${freq} Hz (accepted 0 to ${r.freq_max_hz} Hz)`);
  }
  if (!Number.isFinite(q) || q < r.q_min || q > r.q_max) {
    problems.push(`band ${index}: Q ${q} (accepted ${r.q_min} to ${r.q_max})`);
  }
  if (!Number.isFinite(gain) || gain < r.gain_min_db || gain > r.gain_max_db) {
    problems.push(`band ${index}: gain ${gain} dB (accepted ${r.gain_min_db} to ${r.gain_max_db} dB)`);
  }
  return problems;
}

/** Refuse before anything is sent. Returns { ok, problems }. */
export function guardWrite(table, device, bands) {
  if (!table) return { ok: false, problems: ["the device table could not be read"] };
  if (!device) return { ok: false, problems: ["device identity could not be confirmed"] };
  if (BLOCKED_ARCHITECTURES.has(device.architecture)) {
    return { ok: false, problems: [`${device.name} (${device.chipset}) has fixed mask ROM, no hardware PEQ`] };
  }
  const problems = [];
  (bands || []).forEach((b, i) => {
    problems.push(...bandProblems(table, device.architecture, i, b.freq, b.gain, b.q));
  });
  return { ok: problems.length === 0, problems };
}

// The table is loaded once by app.js; the transport layer resolves identity through it.
let currentTable = null;

if (typeof process !== "undefined" && process?.versions?.node) {
  try {
    const fs = await import("node:fs");
    const jsonPath = new URL("../dacs.json", import.meta.url);
    currentTable = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  } catch {
    // browser or standalone node without dacs.json
  }
}

export function setTable(table) {
  currentTable = table;
  return table;
}

export function getTable() {
  return currentTable;
}

/** The table entry for a connected device, or null when its identity cannot be confirmed. */
export function entryFor(dev) {
  if (!dev) return null;
  return matchDevice(currentTable, dev.vendorId, dev.productId, dev.productName);
}
