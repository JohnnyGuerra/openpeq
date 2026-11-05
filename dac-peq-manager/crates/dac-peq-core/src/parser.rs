use crate::error::{DacError, Result};
use crate::models::{BiquadBand, FilterType, PeqPreset};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PresetFormat {
    EqualizerApo,
    PowerampParametric,
    PowerampGraphic,
    Wavelet,
    AutoEqGraphicEq,
}

impl PresetFormat {
    pub fn as_str(&self) -> &'static str {
        match self {
            PresetFormat::EqualizerApo => "EqualizerAPO",
            PresetFormat::PowerampParametric => "Poweramp Parametric",
            PresetFormat::PowerampGraphic => "Poweramp Graphic",
            PresetFormat::Wavelet => "Wavelet",
            PresetFormat::AutoEqGraphicEq => "AutoEQ GraphicEQ",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ParsedPreset {
    pub name: String,
    pub preamp: f64,
    pub bands: Vec<BiquadBand>,
    pub source_format: PresetFormat,
}

impl ParsedPreset {
    pub fn to_peq_preset(self) -> PeqPreset {
        PeqPreset {
            name: self.name,
            description: Some(format!("Imported from {}", self.source_format.as_str())),
            preamp: self.preamp,
            slot_id: None,
            bands: self.bands,
            full_bands: None,
        }
    }
}

pub fn parse_preset_permissive(text: &str) -> Result<ParsedPreset> {
    let clean = text.trim_start_matches('\u{feff}').trim();
    if clean.is_empty() {
        return Err(DacError::Parse("Preset text is empty".to_string()));
    }

    // 1. AutoEQ GraphicEQ single-line format
    if clean.to_ascii_lowercase().starts_with("graphiceq") {
        return parse_graphiceq(clean);
    }

    // 2. JSON structures (Poweramp Parametric / Graphic or Wavelet)
    if clean.starts_with('{') || clean.starts_with('[') {
        if let Ok(preset) = parse_json_preset(clean) {
            return Ok(preset);
        }
    }

    // 3. Poweramp settings string ("preamp=0.0;55hz=0.5;...")
    if clean.contains('=') && clean.contains(';') && clean.to_ascii_lowercase().contains("hz") {
        if let Ok(preset) = parse_poweramp_string(clean) {
            return Ok(preset);
        }
    }

    // 4. EqualizerAPO format (or Wavelet text export)
    if looks_like_apo(clean) {
        return parse_equalizer_apo(clean);
    }

    Err(DacError::Parse(
        "Unrecognized preset format. Expected EqualizerAPO, Poweramp JSON/settings, Wavelet, or GraphicEQ.".to_string(),
    ))
}

fn looks_like_apo(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    lower.contains("filter") || lower.contains("preamp:")
}

pub fn parse_equalizer_apo(text: &str) -> Result<ParsedPreset> {
    let mut preamp = 0.0;
    let mut bands = Vec::new();
    let mut name = "EqualizerAPO Import".to_string();

    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Check for preset name in comments
        if trimmed.starts_with('#') || trimmed.starts_with(';') {
            let comment = trimmed.trim_start_matches(['#', ';', ' ']);
            if let Some(stripped) = comment.strip_prefix("Preset:") {
                name = stripped.trim().to_string();
            } else if let Some(stripped) = comment.strip_prefix("Name:") {
                name = stripped.trim().to_string();
            }
            continue;
        }

        // Parse Preamp: Preamp: -3.5 dB
        let lower = trimmed.to_ascii_lowercase();
        if lower.starts_with("preamp:") {
            let val_part = trimmed["preamp:".len()..].trim();
            let val_str = val_part
                .split_whitespace()
                .next()
                .unwrap_or("")
                .trim_end_matches("dB")
                .trim_end_matches("db");
            if let Ok(p) = val_str.parse::<f64>() {
                preamp = p;
            }
            continue;
        }

        // Parse Filter line:
        // Filter 1: ON PK Fc 100 Hz Gain 3 dB Q 1.41
        // Filter: ON LSC Fc 80.0 Hz Gain +2.0 dB Q 0.71
        if lower.starts_with("filter") {
            if let Some(band) = parse_apo_filter_line(trimmed) {
                bands.push(band);
            }
        }
    }

    if bands.is_empty() && (preamp - 0.0).abs() < 1e-6 {
        return Err(DacError::Parse(
            "EqualizerAPO text contained no valid filters or preamp".to_string(),
        ));
    }

    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Ok(ParsedPreset {
        name,
        preamp,
        bands,
        source_format: PresetFormat::EqualizerApo,
    })
}

fn parse_apo_filter_line(line: &str) -> Option<BiquadBand> {
    // Split after ':'
    let payload = if let Some(idx) = line.find(':') {
        line[idx + 1..].trim()
    } else {
        line.trim()
    };

    let tokens: Vec<&str> = payload.split_whitespace().collect();
    if tokens.is_empty() {
        return None;
    }

    let mut enabled = true;
    let mut filter_type = FilterType::Peaking;
    let mut freq = 1000.0;
    let mut gain = 0.0;
    let mut q = 1.0;

    let mut i = 0;
    while i < tokens.len() {
        let tok = tokens[i];
        let upper = tok.to_ascii_uppercase();

        if upper == "ON" {
            enabled = true;
            i += 1;
            continue;
        } else if upper == "OFF" {
            enabled = false;
            i += 1;
            continue;
        }

        match upper.as_str() {
            "PK" | "PEAK" | "PEAKING" => {
                filter_type = FilterType::Peaking;
                i += 1;
                continue;
            }
            "LSQ" | "LSC" | "LOW_SHELF" | "LOWSHELF" | "LS" => {
                filter_type = FilterType::LowShelf;
                i += 1;
                continue;
            }
            "HSQ" | "HSC" | "HIGH_SHELF" | "HIGHSHELF" | "HS" => {
                filter_type = FilterType::HighShelf;
                i += 1;
                continue;
            }
            "FC" | "F" => {
                if i + 1 < tokens.len() {
                    let f_str = tokens[i + 1]
                        .trim_end_matches("Hz")
                        .trim_end_matches("hz");
                    if let Ok(parsed_f) = f_str.parse::<f64>() {
                        freq = parsed_f;
                    }
                    i += 2;
                    // skip trailing "Hz" token if present
                    if i < tokens.len() && tokens[i].eq_ignore_ascii_case("hz") {
                        i += 1;
                    }
                    continue;
                }
            }
            "GAIN" | "G" => {
                if i + 1 < tokens.len() {
                    let g_str = tokens[i + 1]
                        .trim_end_matches("dB")
                        .trim_end_matches("db");
                    if let Ok(parsed_g) = g_str.parse::<f64>() {
                        gain = parsed_g;
                    }
                    i += 2;
                    if i < tokens.len() && tokens[i].eq_ignore_ascii_case("db") {
                        i += 1;
                    }
                    continue;
                }
            }
            "Q" | "BW" => {
                if i + 1 < tokens.len() {
                    if let Ok(parsed_q) = tokens[i + 1].parse::<f64>() {
                        q = parsed_q;
                    }
                    i += 2;
                    continue;
                }
            }
            _ => {}
        }
        i += 1;
    }

    Some(BiquadBand {
        index: None,
        enabled,
        filter_type,
        freq,
        gain,
        q,
    })
}

pub fn parse_graphiceq(text: &str) -> Result<ParsedPreset> {
    let payload = if let Some(idx) = text.find(':') {
        text[idx + 1..].trim()
    } else {
        text.trim_start_matches("graphiceq").trim_start_matches("GraphicEQ").trim()
    };

    let mut bands = Vec::new();
    // Chunks are separated by semicolons: "20 -5.5; 25 -5.2; ..."
    for chunk in payload.split(';') {
        let trimmed = chunk.trim();
        if trimmed.is_empty() {
            continue;
        }
        let parts: Vec<&str> = trimmed.split_whitespace().collect();
        if parts.len() >= 2 {
            if let (Ok(f), Ok(g)) = (parts[0].parse::<f64>(), parts[1].parse::<f64>()) {
                if (20.0..=22000.0).contains(&f) {
                    bands.push(BiquadBand::new(FilterType::Peaking, f, g, 1.414));
                }
            }
        }
    }

    if bands.is_empty() {
        return Err(DacError::Parse(
            "AutoEQ GraphicEQ contained no valid frequency/gain pairs".to_string(),
        ));
    }

    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Ok(ParsedPreset {
        name: "AutoEQ GraphicEQ Import".to_string(),
        preamp: 0.0,
        bands,
        source_format: PresetFormat::AutoEqGraphicEq,
    })
}

pub fn parse_poweramp_string(text: &str) -> Result<ParsedPreset> {
    let mut preamp = 0.0;
    let mut bands = Vec::new();

    for chunk in text.split(';') {
        let trimmed = chunk.trim();
        if trimmed.is_empty() || !trimmed.contains('=') {
            continue;
        }
        let parts: Vec<&str> = trimmed.splitn(2, '=').collect();
        if parts.len() != 2 {
            continue;
        }
        let key = parts[0].trim();
        let val_str = parts[1].trim();

        if key.eq_ignore_ascii_case("preamp") {
            if let Ok(p) = val_str.parse::<f64>() {
                preamp = p;
            }
            continue;
        }

        if let (Some(freq), Ok(gain)) = (parse_frequency_key(key), val_str.parse::<f64>()) {
            bands.push(BiquadBand::new(FilterType::Peaking, freq, gain, 1.414));
        }
    }

    if bands.is_empty() {
        return Err(DacError::Parse(
            "Poweramp settings string contained no valid frequency bands".to_string(),
        ));
    }

    bands.sort_by(|a, b| a.freq.partial_cmp(&b.freq).unwrap_or(std::cmp::Ordering::Equal));
    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Ok(ParsedPreset {
        name: "Poweramp Graphic Import".to_string(),
        preamp,
        bands,
        source_format: PresetFormat::PowerampGraphic,
    })
}

fn parse_frequency_key(key: &str) -> Option<f64> {
    let lower = key.to_ascii_lowercase().replace(' ', "");
    let clean = lower.trim_end_matches("hz");
    if let Some(khz_val) = clean.strip_suffix('k') {
        khz_val.parse::<f64>().ok().map(|k| k * 1000.0)
    } else {
        clean.parse::<f64>().ok()
    }
}

pub fn parse_json_preset(text: &str) -> Result<ParsedPreset> {
    let val: Value = serde_json::from_str(text)
        .map_err(|e| DacError::Parse(format!("Invalid JSON syntax: {e}")))?;

    // Try Poweramp Parametric
    if let Some(preset) = try_parse_poweramp_json(&val) {
        return Ok(preset);
    }

    // Try Wavelet JSON
    if let Some(preset) = try_parse_wavelet_json(&val) {
        return Ok(preset);
    }

    // Try Poweramp Graphic JSON (object mapping "55hz": 0.5)
    if let Some(preset) = try_parse_poweramp_graphic_json(&val) {
        return Ok(preset);
    }

    Err(DacError::Parse(
        "JSON does not match known Poweramp or Wavelet schemas".to_string(),
    ))
}

fn try_parse_poweramp_json(val: &Value) -> Option<ParsedPreset> {
    // Array at root or inside ParametricEq.Bands / bands
    let (bands_val, name, preamp) = if let Some(arr) = val.as_array() {
        (arr, "Poweramp Parametric Import".to_string(), 0.0)
    } else if let Some(obj) = val.as_object() {
        let name = obj.get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("Poweramp Parametric Import")
            .to_string();
        let preamp = obj.get("preamp")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);

        let bands_arr = obj.get("PowerampEqualizer.parametric")
            .or_else(|| obj.get("ParametricEq").and_then(|pe| pe.get("Bands").or_else(|| pe.get("bands"))))
            .or_else(|| obj.get("bands"))
            .or_else(|| obj.get("Bands"))
            .and_then(|b| b.as_array())?;

        (bands_arr, name, preamp)
    } else {
        return None;
    };

    let mut bands = Vec::new();
    for item in bands_val {
        let obj = item.as_object()?;
        let freq = obj.get("freq")
            .or_else(|| obj.get("frequency"))
            .or_else(|| obj.get("f"))
            .or_else(|| obj.get("hz"))
            .and_then(|v| v.as_f64())?;

        let gain = obj.get("gain")
            .or_else(|| obj.get("g"))
            .or_else(|| obj.get("db"))
            .and_then(|v| v.as_f64())?;

        let q = obj.get("q")
            .or_else(|| obj.get("Q"))
            .or_else(|| obj.get("bandwidth"))
            .and_then(|v| v.as_f64())
            .unwrap_or(1.414);

        let enabled = obj.get("enabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);

        let filter_type = if let Some(t_str) = obj.get("type").or_else(|| obj.get("Type")).and_then(|v| v.as_str()) {
            map_poweramp_type_str(t_str)
        } else if let Some(t_num) = obj.get("type").and_then(|v| v.as_i64()) {
            match t_num {
                1 => FilterType::LowShelf,
                2 => FilterType::HighShelf,
                _ => FilterType::Peaking,
            }
        } else {
            FilterType::Peaking
        };

        bands.push(BiquadBand {
            index: None,
            enabled,
            filter_type,
            freq,
            gain,
            q,
        });
    }

    if bands.is_empty() {
        return None;
    }

    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Some(ParsedPreset {
        name,
        preamp,
        bands,
        source_format: PresetFormat::PowerampParametric,
    })
}

fn try_parse_wavelet_json(val: &Value) -> Option<ParsedPreset> {
    let obj = val.as_object()?;
    let filters_arr = obj.get("filters")
        .or_else(|| obj.get("Filters"))
        .and_then(|f| f.as_array())?;

    let name = obj.get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("Wavelet Import")
        .to_string();

    let preamp = obj.get("preamp")
        .or_else(|| obj.get("Preamp"))
        .or_else(|| obj.get("preampDb"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);

    let mut bands = Vec::new();
    for item in filters_arr {
        let f_obj = item.as_object()?;
        let freq = f_obj.get("frequency")
            .or_else(|| f_obj.get("freq"))
            .or_else(|| f_obj.get("f"))
            .or_else(|| f_obj.get("hz"))
            .and_then(|v| v.as_f64())?;

        let gain = f_obj.get("gain")
            .or_else(|| f_obj.get("g"))
            .or_else(|| f_obj.get("db"))
            .and_then(|v| v.as_f64())?;

        let q = f_obj.get("q")
            .or_else(|| f_obj.get("Q"))
            .and_then(|v| v.as_f64())
            .unwrap_or(1.0);

        let type_str = f_obj.get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("peaking");

        bands.push(BiquadBand::new(map_poweramp_type_str(type_str), freq, gain, q));
    }

    if bands.is_empty() {
        return None;
    }

    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Some(ParsedPreset {
        name,
        preamp,
        bands,
        source_format: PresetFormat::Wavelet,
    })
}

fn try_parse_poweramp_graphic_json(val: &Value) -> Option<ParsedPreset> {
    let obj = val.as_object()?;
    let settings_obj = obj.get("EqualizerSettings")
        .or_else(|| obj.get("Equalizer"))
        .and_then(|v| v.as_object())
        .unwrap_or(obj);

    let mut preamp = 0.0;
    let mut bands = Vec::new();

    for (k, v) in settings_obj {
        if k.eq_ignore_ascii_case("preamp") {
            if let Some(p) = v.as_f64() {
                preamp = p;
            }
            continue;
        }

        if let (Some(freq), Some(gain)) = (parse_frequency_key(k), v.as_f64()) {
            bands.push(BiquadBand::new(FilterType::Peaking, freq, gain, 1.414));
        }
    }

    if bands.is_empty() {
        return None;
    }

    bands.sort_by(|a, b| a.freq.partial_cmp(&b.freq).unwrap_or(std::cmp::Ordering::Equal));
    for (i, b) in bands.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    Some(ParsedPreset {
        name: "Poweramp Graphic Import".to_string(),
        preamp,
        bands,
        source_format: PresetFormat::PowerampGraphic,
    })
}

fn map_poweramp_type_str(raw: &str) -> FilterType {
    match raw.to_ascii_lowercase().trim() {
        "peaking" | "peak" | "pk" | "bell" => FilterType::Peaking,
        "lowshelf" | "low_shelf" | "low-shelf" | "ls" | "lsc" | "lsq" => FilterType::LowShelf,
        "highshelf" | "high_shelf" | "high-shelf" | "hs" | "hsc" | "hsq" => FilterType::HighShelf,
        _ => FilterType::Peaking,
    }
}
