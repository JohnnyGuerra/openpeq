use crate::biquad::{
    calculate_rbj_biquad, calculate_recommended_preamp, compute_composite_response,
};
use crate::error::{DacError, Result};
use crate::models::{BiquadBand, FilterType, PeqPreset};

pub const DEFAULT_FS: f64 = 48000.0;
pub const LOW_SHELF_FC_MIN: f64 = 40.0;
pub const LOW_SHELF_FC_MAX: f64 = 180.0;
pub const HIGH_SHELF_FC_MIN: f64 = 6000.0;
pub const HIGH_SHELF_FC_MAX: f64 = 14000.0;

#[derive(Debug, Clone, PartialEq)]
pub struct FreqPoint {
    pub freq: f64,
    pub db: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StandardTarget {
    HarmanInEar2019,
    IefNeutral,
    DiffuseFieldTilted,
}

impl StandardTarget {
    pub fn get_curve(&self) -> Vec<FreqPoint> {
        match self {
            StandardTarget::HarmanInEar2019 => harman_ie_2019_target(),
            StandardTarget::IefNeutral => ief_neutral_target(),
            StandardTarget::DiffuseFieldTilted => diffuse_field_tilted_target(),
        }
    }
}

pub fn parse_fr_text(text: &str) -> Result<Vec<FreqPoint>> {
    let mut points = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with(';') {
            continue;
        }

        // Handle commas or whitespace
        let cleaned = trimmed.replace(',', " ");
        let parts: Vec<&str> = cleaned.split_whitespace().collect();
        if parts.len() < 2 {
            continue;
        }

        // Skip headers like "frequency,spl" or "freq dB"
        if let (Ok(f), Ok(db)) = (parts[0].parse::<f64>(), parts[1].parse::<f64>()) {
            if (10.0..=24000.0).contains(&f) {
                points.push(FreqPoint { freq: f, db });
            }
        }
    }

    if points.is_empty() {
        return Err(DacError::Parse(
            "Frequency response text contained no valid frequency/dB pairs".to_string(),
        ));
    }

    points.sort_by(|a, b| a.freq.partial_cmp(&b.freq).unwrap_or(std::cmp::Ordering::Equal));
    Ok(points)
}

/// Interpolates dB values at target frequencies from measured curve points.
pub fn interpolate_curve(raw: &[FreqPoint], target_freqs: &[f64]) -> Vec<f64> {
    if raw.is_empty() {
        return vec![0.0; target_freqs.len()];
    }
    if raw.len() == 1 {
        return vec![raw[0].db; target_freqs.len()];
    }

    let mut out = Vec::with_capacity(target_freqs.len());
    for &f in target_freqs {
        if f <= raw[0].freq {
            out.push(raw[0].db);
        } else if f >= raw[raw.len() - 1].freq {
            out.push(raw[raw.len() - 1].db);
        } else {
            // Find segment
            let idx = match raw.binary_search_by(|p| p.freq.partial_cmp(&f).unwrap()) {
                Ok(exact) => {
                    out.push(raw[exact].db);
                    continue;
                }
                Err(pos) => pos,
            };
            let p0 = &raw[idx - 1];
            let p1 = &raw[idx];
            let frac = (f.log10() - p0.freq.log10()) / (p1.freq.log10() - p0.freq.log10());
            out.push(p0.db + frac * (p1.db - p0.db));
        }
    }
    out
}

/// Generates standard AutoEq logarithmic frequency grid (20 Hz - 20 kHz, step 1.029, ~241 points).
pub fn generate_autoeq_grid() -> Vec<f64> {
    let step = 1.029f64;
    let mut freqs = Vec::new();
    let mut f = 20.0f64;
    while f <= 20000.0 {
        freqs.push((f * 10.0).round() / 10.0);
        f *= step;
    }
    freqs
}

/// Fits a parametric EQ preset to match a measured frequency response to a target curve.
pub fn fit_measurement_to_target(
    measurement_text: &str,
    target: StandardTarget,
    target_bands: usize,
    anchor_shelves: bool,
    fs: f64,
) -> Result<PeqPreset> {
    let meas_raw = parse_fr_text(measurement_text)?;
    let target_raw = target.get_curve();

    let grid = generate_autoeq_grid();
    let mut meas_grid = interpolate_curve(&meas_raw, &grid);
    let target_grid = interpolate_curve(&target_raw, &grid);

    // Normalize at 1kHz region (800 Hz - 1200 Hz)
    let mut norm_sum = 0.0;
    let mut norm_count = 0;
    for (i, &f) in grid.iter().enumerate() {
        if (800.0..=1200.0).contains(&f) {
            norm_sum += target_grid[i] - meas_grid[i];
            norm_count += 1;
        }
    }
    let offset = if norm_count > 0 { norm_sum / norm_count as f64 } else { 0.0 };
    for v in &mut meas_grid {
        *v += offset;
    }

    let bands = run_greedy_filter_fitting(&grid, &meas_grid, &target_grid, target_bands, anchor_shelves, fs);
    let preamp = calculate_recommended_preamp(&bands, 0.5, fs);

    Ok(PeqPreset {
        name: "AutoEq Fitted Profile".to_string(),
        description: Some(format!("Client-side fitted {target_bands}-band profile")),
        preamp,
        slot_id: None,
        bands,
        full_bands: None,
    })
}

fn run_greedy_filter_fitting(
    freqs: &[f64],
    meas: &[f64],
    target: &[f64],
    max_filters: usize,
    anchor_shelves: bool,
    fs: f64,
) -> Vec<BiquadBand> {
    let target_count = max_filters.clamp(1, 15);
    let mut filters: Vec<BiquadBand> = Vec::new();

    let num_shelves = if anchor_shelves && target_count >= 3 { 2 } else { 0 };
    let peaking_slots = target_count.saturating_sub(num_shelves);

    let mut current_meas = meas.to_vec();

    // 1. Greedy peaking filter allocation by largest deviation (width * height)
    for _ in 0..peaking_slots {
        let error: Vec<f64> = target.iter().zip(current_meas.iter()).map(|(t, m)| t - m).collect();
        let peak = match find_largest_peak(&error, freqs) {
            Some(p) if p.height >= 0.5 => p,
            _ => break,
        };

        let fc = freqs[peak.index];
        let gain = (if peak.is_positive { peak.height } else { -peak.height }).clamp(-12.0, 12.0);
        let bw = peak.width_octaves.max(0.15);
        let q = (2.0f64.powf(bw).sqrt() / (2.0f64.powf(bw) - 1.0)).clamp(0.5, 10.0);

        let band = BiquadBand::new(FilterType::Peaking, (fc * 10.0).round() / 10.0, (gain * 10.0).round() / 10.0, (q * 10.0).round() / 10.0);
        current_meas = apply_bands_to_curve(meas, &[band.clone()], freqs, fs);
        filters.push(band);
    }

    // 2. Anchor shelves if requested
    if anchor_shelves && target_count >= 3 {
        let error: Vec<f64> = target.iter().zip(current_meas.iter()).map(|(t, m)| t - m).collect();
        let low_shelf = init_shelf(&error, freqs, FilterType::LowShelf, LOW_SHELF_FC_MIN, LOW_SHELF_FC_MAX, fs);
        if low_shelf.gain.abs() > 0.3 {
            filters.push(low_shelf);
        }

        let cur_resp = compute_composite_response(&filters, 0.0, freqs, fs);
        let err2: Vec<f64> = target.iter().zip(meas.iter()).zip(cur_resp.iter()).map(|((t, m), c)| t - (m + c)).collect();
        let high_shelf = init_shelf(&err2, freqs, FilterType::HighShelf, HIGH_SHELF_FC_MIN, HIGH_SHELF_FC_MAX, fs);
        if high_shelf.gain.abs() > 0.3 {
            filters.push(high_shelf);
        }
    }

    // 3. Grid search optimization (2 passes)
    for _pass in 0..2 {
        for i in 0..filters.len() {
            let mut others = filters.clone();
            others.remove(i);
            filters[i] = optimize_single_band(freqs, meas, target, &filters[i], &others, fs);
        }
    }

    // 4. Pad with zero-gain peaking bands if under target_count
    let pad_freqs: [f64; 7] = [105.0, 350.0, 1000.0, 2500.0, 4000.0, 8000.0, 12500.0];
    while filters.len() < target_count {
        let mut chosen = 1000.0;
        for &pf in &pad_freqs {
            if !filters.iter().any(|b| (b.freq.log10() - pf.log10()).abs() < 0.1) {
                chosen = pf;
                break;
            }
        }
        filters.push(BiquadBand::new(FilterType::Peaking, chosen, 0.0, 1.414));
    }

    filters.sort_by(|a, b| a.freq.partial_cmp(&b.freq).unwrap_or(std::cmp::Ordering::Equal));
    for (i, b) in filters.iter_mut().enumerate() {
        b.index = Some(i + 1);
    }

    filters
}

#[derive(Debug)]
struct PeakInfo {
    index: usize,
    width_octaves: f64,
    height: f64,
    is_positive: bool,
}

fn find_largest_peak(error: &[f64], freqs: &[f64]) -> Option<PeakInfo> {
    let mut best: Option<PeakInfo> = None;
    let mut max_metric = 0.0;

    for i in 1..error.len().saturating_sub(1) {
        let is_max = error[i] > error[i - 1] && error[i] > error[i + 1] && error[i] > 0.5;
        let is_min = error[i] < error[i - 1] && error[i] < error[i + 1] && error[i] < -0.5;
        if !is_max && !is_min {
            continue;
        }

        let half_h = error[i].abs() / 2.0;
        let mut left = i;
        let mut right = i;
        while left > 0 && error[left].abs() > half_h {
            left -= 1;
        }
        while right < error.len() - 1 && error[right].abs() > half_h {
            right += 1;
        }

        let width = if right > left {
            (freqs[right] / freqs[left]).ln() / 2.0f64.ln()
        } else {
            0.15
        };

        let metric = width * error[i].abs();
        if metric > max_metric {
            max_metric = metric;
            best = Some(PeakInfo {
                index: i,
                width_octaves: width,
                height: error[i].abs(),
                is_positive: is_max,
            });
        }
    }

    best
}

fn init_shelf(
    error: &[f64],
    freqs: &[f64],
    shelf_type: FilterType,
    f_min: f64,
    f_max: f64,
    fs: f64,
) -> BiquadBand {
    let min_idx = freqs.iter().position(|&f| f >= f_min).unwrap_or(0);
    let max_idx = freqs.iter().rposition(|&f| f <= f_max).unwrap_or(freqs.len() - 1);

    let mut best_idx = min_idx;
    let mut best_avg = 0.0f64;

    for i in min_idx..=max_idx {
        let avg: f64 = if shelf_type == FilterType::LowShelf {
            error[0..=i].iter().sum::<f64>() / (i + 1) as f64
        } else {
            error[i..error.len()].iter().sum::<f64>() / (error.len() - i) as f64
        };
        if avg.abs() > best_avg.abs() {
            best_avg = avg;
            best_idx = i;
        }
    }

    let fc = freqs[best_idx];
    let unit_filter = BiquadBand::new(shelf_type, fc, 1.0, 0.71);
    let unit_resp = compute_composite_response(&[unit_filter], 0.0, freqs, fs);

    let dot: f64 = error.iter().zip(unit_resp.iter()).map(|(e, r)| e * r).sum();
    let norm: f64 = unit_resp.iter().map(|r| r * r).sum();

    let gain = if norm > 0.001 {
        (dot / norm).clamp(-12.0, 12.0)
    } else {
        0.0
    };

    BiquadBand::new(shelf_type, (fc * 10.0).round() / 10.0, (gain * 10.0).round() / 10.0, 0.71)
}

fn optimize_single_band(
    freqs: &[f64],
    meas: &[f64],
    target: &[f64],
    band: &BiquadBand,
    others: &[BiquadBand],
    fs: f64,
) -> BiquadBand {
    let base_resp = compute_composite_response(others, 0.0, freqs, fs);
    let ix10k = freqs.iter().position(|&f| f >= 10000.0).unwrap_or(freqs.len());

    let mut best = band.clone();
    let mut best_err = calc_error(freqs, meas, target, &base_resp, &best, ix10k, fs);

    let fc_candidates: Vec<f64> = match band.filter_type {
        FilterType::LowShelf => vec![60.0, 80.0, 105.0, 140.0, 180.0],
        FilterType::HighShelf => vec![7000.0, 8500.0, 10000.0, 12000.0],
        FilterType::Peaking => {
            let mut f_list = Vec::new();
            let mut f = (band.freq * 0.75).max(20.0);
            let f_end = (band.freq * 1.35).min(18000.0);
            while f <= f_end {
                f_list.push(f);
                f *= 1.10;
            }
            f_list
        }
        FilterType::Bypass => vec![band.freq],
    };

    let q_candidates: &[f64] = match band.filter_type {
        FilterType::LowShelf | FilterType::HighShelf => &[0.5, 0.71, 1.0],
        _ => &[0.71, 1.41, 2.5, 4.0],
    };

    let mut g_candidates: Vec<f64> = Vec::new();
    let g_center = band.gain;
    for &delta in &[-3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0] {
        let cand_g = (g_center + delta).clamp(-12.0, 12.0);
        g_candidates.push((cand_g * 10.0).round() / 10.0);
    }

    for &fc in &fc_candidates {
        for &q in q_candidates {
            for &g in &g_candidates {
                let candidate = BiquadBand::new(band.filter_type, fc, g, q);
                let err = calc_error(freqs, meas, target, &base_resp, &candidate, ix10k, fs);
                if err < best_err {
                    best_err = err;
                    best = candidate;
                }
            }
        }
    }

    best
}

fn calc_error(
    freqs: &[f64],
    meas: &[f64],
    target: &[f64],
    base_resp: &[f64],
    band: &BiquadBand,
    ix10k: usize,
    fs: f64,
) -> f64 {
    let coeffs = calculate_rbj_biquad(band.filter_type, band.freq, band.gain, band.q, fs);
    let mut sse = 0.0;

    // Per-point SSE below 10 kHz
    for i in 0..ix10k {
        let band_val = coeffs.response_at(freqs[i]);
        let simulated = meas[i] + base_resp[i] + band_val;
        let diff = target[i] - simulated;
        sse += diff * diff;
    }

    // Mean energy collapse above 10 kHz (prevent overfitting 711 resonance spike)
    if ix10k < freqs.len() {
        let count = freqs.len() - ix10k;
        let mut target_sum = 0.0;
        let mut sim_sum = 0.0;
        for i in ix10k..freqs.len() {
            let band_val = coeffs.response_at(freqs[i]);
            target_sum += target[i];
            sim_sum += meas[i] + base_resp[i] + band_val;
        }
        let diff = (target_sum - sim_sum) / count as f64;
        sse += diff * diff * count as f64;
    }

    sse / freqs.len() as f64
}

fn apply_bands_to_curve(meas: &[f64], bands: &[BiquadBand], freqs: &[f64], fs: f64) -> Vec<f64> {
    let resp = compute_composite_response(bands, 0.0, freqs, fs);
    meas.iter().zip(resp.iter()).map(|(m, r)| m + r).collect()
}

// Built-in standard targets
fn harman_ie_2019_target() -> Vec<FreqPoint> {
    vec![
        FreqPoint { freq: 20.0, db: 8.8 },
        FreqPoint { freq: 30.0, db: 8.5 },
        FreqPoint { freq: 50.0, db: 7.7 },
        FreqPoint { freq: 100.0, db: 5.5 },
        FreqPoint { freq: 200.0, db: 2.2 },
        FreqPoint { freq: 500.0, db: 0.0 },
        FreqPoint { freq: 1000.0, db: 0.0 },
        FreqPoint { freq: 2000.0, db: 5.0 },
        FreqPoint { freq: 3000.0, db: 9.5 },
        FreqPoint { freq: 4000.0, db: 7.5 },
        FreqPoint { freq: 6000.0, db: 3.0 },
        FreqPoint { freq: 8000.0, db: 4.5 },
        FreqPoint { freq: 10000.0, db: 0.0 },
        FreqPoint { freq: 15000.0, db: -3.0 },
        FreqPoint { freq: 20000.0, db: -6.0 },
    ]
}

fn ief_neutral_target() -> Vec<FreqPoint> {
    vec![
        FreqPoint { freq: 20.0, db: 0.0 },
        FreqPoint { freq: 50.0, db: 0.0 },
        FreqPoint { freq: 100.0, db: 0.0 },
        FreqPoint { freq: 200.0, db: 0.0 },
        FreqPoint { freq: 1000.0, db: 0.0 },
        FreqPoint { freq: 2000.0, db: 4.5 },
        FreqPoint { freq: 3000.0, db: 8.0 },
        FreqPoint { freq: 4000.0, db: 6.0 },
        FreqPoint { freq: 6000.0, db: 2.0 },
        FreqPoint { freq: 8000.0, db: 2.5 },
        FreqPoint { freq: 10000.0, db: 0.0 },
        FreqPoint { freq: 20000.0, db: -5.0 },
    ]
}

fn diffuse_field_tilted_target() -> Vec<FreqPoint> {
    vec![
        FreqPoint { freq: 20.0, db: 4.0 },
        FreqPoint { freq: 100.0, db: 2.5 },
        FreqPoint { freq: 500.0, db: 0.5 },
        FreqPoint { freq: 1000.0, db: 0.0 },
        FreqPoint { freq: 3000.0, db: 7.0 },
        FreqPoint { freq: 6000.0, db: 1.0 },
        FreqPoint { freq: 10000.0, db: -1.0 },
        FreqPoint { freq: 20000.0, db: -7.0 },
    ]
}
