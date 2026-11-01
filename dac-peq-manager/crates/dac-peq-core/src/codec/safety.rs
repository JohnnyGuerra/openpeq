use std::collections::BTreeMap;
use std::sync::OnceLock;

use serde::Deserialize;

use crate::error::{DacError, Result};

pub const CONEXANT_VID: u16 = 0x0572;
pub const CONEXANT_PID: u16 = 0x1B08;

/// Architectures that must never be written to. `conexant_fixed` is a mask ROM with
/// OTP registers: a HID register write is irreversible.
pub const BLOCKED_ARCHITECTURES: &[&str] = &["conexant_fixed"];

/// shortcut: default path assumes the CLI runs from the repo root, upgrade to a
/// packaged data dir when the crate is installed standalone.
pub const TABLE_PATH: &str = "src/dac_peq/data/dacs.json";

#[derive(Debug, Clone, Deserialize)]
pub struct DeviceEntry {
    pub vid: u16,
    pub pid: u16,
    pub name: String,
    pub chipset: String,
    pub architecture: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Ranges {
    pub freq_max_hz: f64,
    pub q_min: f64,
    pub q_max: f64,
    pub gain_min_db: f64,
    pub gain_max_db: f64,
}

/// The device table is the single source of truth for identity and ranges, shared by
/// Python, Rust and the browser. Ranges are what the tool accepts, not a hardware claim.
#[derive(Debug, Clone, Deserialize)]
pub struct DeviceTable {
    pub devices: Vec<DeviceEntry>,
    pub ranges: BTreeMap<String, Ranges>,
}

pub fn load_table(json: &str) -> Result<DeviceTable> {
    serde_json::from_str(json).map_err(|e| DacError::Serialization(format!("Could not read the device table: {e}")))
}

/// The table is read once, at runtime, from the same file Python and the browser use.
/// If it cannot be read the guard fails closed.
static TABLE: OnceLock<DeviceTable> = OnceLock::new();

pub fn table() -> Result<&'static DeviceTable> {
    if let Some(t) = TABLE.get() {
        return Ok(t);
    }
    let path = table_path();
    let json = std::fs::read_to_string(&path)
        .map_err(|e| DacError::SafetyGuard(format!("SAFETY GUARD: could not read the device table at {path} ({e}), so writes are refused.")))?;
    let t = load_table(&json)?;
    let _ = TABLE.set(t);
    Ok(TABLE.get().unwrap())
}

/// Used by the browser: the table is already loaded there, so JS hands it to Rust
/// instead of Rust reading a file it cannot reach.
pub fn set_device_table(json: &str) -> Result<&'static DeviceTable> {
    if let Some(t) = TABLE.get() {
        return Ok(t);
    }
    let _ = TABLE.set(load_table(json)?);
    Ok(TABLE.get().unwrap())
}

pub fn table_path() -> String {
    if let Ok(p) = std::env::var("DAC_PEQ_TABLE") {
        return p;
    }
    if std::path::Path::new(TABLE_PATH).exists() {
        return TABLE_PATH.to_string();
    }
    // cargo runs from the crate directory, so the repo layout is one level up.
    format!("{}/../../src/dac_peq/data/dacs.json", env!("CARGO_MANIFEST_DIR"))
}

pub fn match_device<'a>(table: &'a DeviceTable, vid: u16, pid: u16, product_name: Option<&str>) -> Option<&'a DeviceEntry> {
    let entry = table.devices.iter().find(|d| d.vid == vid && d.pid == pid);
    if entry.is_some() {
        return entry;
    }
    // Same vendor, unknown product id: resolve by name before anything else.
    if let Some(name) = product_name {
        let lower = name.to_lowercase();
        return table.devices.iter().find(|d| {
            d.vid == vid && (lower.contains(&d.name.to_lowercase()) || d.name.to_lowercase().contains(&lower))
        });
    }
    None
}

pub fn ranges_for<'a>(table: &'a DeviceTable, architecture: &str) -> Option<&'a Ranges> {
    table.ranges.get(architecture)
}

pub fn validate_band(table: &DeviceTable, architecture: &str, index: usize, freq: f64, gain: f64, q: f64) -> Result<()> {
    let r = match ranges_for(table, architecture) {
        Some(r) => r,
        None => return Ok(()),
    };
    let mut problems: Vec<String> = Vec::new();
    if !freq.is_finite() || freq <= 0.0 || freq > r.freq_max_hz {
        problems.push(format!("freq {freq} Hz (max {} Hz)", r.freq_max_hz));
    }
    if !q.is_finite() || q < r.q_min || q > r.q_max {
        problems.push(format!("Q {q} (range {}-{})", r.q_min, r.q_max));
    }
    if !gain.is_finite() || gain < r.gain_min_db || gain > r.gain_max_db {
        problems.push(format!("gain {gain} dB (range {} to {} dB)", r.gain_min_db, r.gain_max_db));
    }
    if problems.is_empty() {
        return Ok(());
    }
    Err(DacError::InvalidFilter(format!(
        "SAFETY GUARD: write rejected - band {}: {}",
        index,
        problems.join(", ")
    )))
}

/// Returns true if the device is a Conexant CX31993 fixed mask ROM DAC.
pub fn is_conexant_cx31993(vid: u16, pid: u16, product_name: Option<&str>) -> bool {
    let t = match table() {
        Ok(t) => t,
        Err(_) => return vid == CONEXANT_VID,
    };
    match match_device(t, vid, pid, product_name) {
        Some(e) => BLOCKED_ARCHITECTURES.contains(&e.architecture.as_str()),
        // An id that is not in the table is refused anyway, so a name match here is
        // only a legacy convenience for callers that already know the vendor.
        None => vid == CONEXANT_VID,
    }
}

/// Safety guard: identity must be confirmed from the table before anything is written.
pub fn assert_safe_for_hardware_flash(vid: u16, pid: u16, product_name: Option<&str>) -> Result<()> {
    let t = table()?;
    let entry = match match_device(t, vid, pid, product_name) {
        Some(e) => e,
        None => return Err(DacError::SafetyGuard(format!(
            "SAFETY GUARD: cannot confirm the identity of 0x{vid:04X}:{pid:04X} - it is not in the device table, \
             so writes are refused. Use host-side DSP exporters (export-pipewire, export-apo)."
        ))),
    };
    if BLOCKED_ARCHITECTURES.contains(&entry.architecture.as_str()) {
        return Err(DacError::SafetyGuard(format!(
            "SAFETY GUARD: {} (0x{vid:04X}:{pid:04X}) is a {} with fixed mask ROM. \
             Attempting HID register writes will corrupt OTP descriptors. \
             Hardware flashing is strictly blocked. Use host-side DSP (PipeWire/Wavelet).",
            entry.name, entry.chipset
        )));
    }
    Ok(())
}
