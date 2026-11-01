use dac_peq_core::*;

#[test]
fn test_rbj_biquad_peaking_response() {
    let filt = calculate_rbj_biquad(FilterType::Peaking, 1000.0, 6.0, 1.414, 48000.0);
    // At center frequency (1000 Hz), response should be exactly +6.0 dB
    let resp_center = filt.response_at(1000.0);
    assert!((resp_center - 6.0).abs() < 1e-4);

    // Far from center frequency (e.g. 50 Hz), response should be close to 0 dB
    let resp_low = filt.response_at(50.0);
    assert!(resp_low.abs() < 0.2);
}

#[test]
fn test_rbj_low_shelf_response() {
    let filt = calculate_rbj_biquad(FilterType::LowShelf, 100.0, 4.0, 0.71, 48000.0);
    // At deep sub-bass (20 Hz), low shelf should provide ~+4.0 dB
    let resp_20 = filt.response_at(20.0);
    assert!((resp_20 - 4.0).abs() < 0.2);

    // Above shelf frequency (e.g. 5 kHz), gain should be near 0 dB
    let resp_high = filt.response_at(5000.0);
    assert!(resp_high.abs() < 0.1);
}

#[test]
fn test_preset_deserialization_and_preamp() {
    let json_data = r#"{
        "name": "Test Preset",
        "preamp": -2.5,
        "bands": [
            {"type": "PK", "freq": 1000.0, "gain": 3.0, "q": 1.0},
            {"type": "LSQ", "freq": 100.0, "gain": 2.0, "q": 0.71}
        ]
    }"#;

    let preset: PeqPreset = serde_json::from_str(json_data).expect("Failed to parse preset");
    assert_eq!(preset.name, "Test Preset");
    assert_eq!(preset.preamp, -2.5);
    assert_eq!(preset.bands.len(), 2);
    assert_eq!(preset.bands[0].filter_type, FilterType::Peaking);
    assert_eq!(preset.bands[1].filter_type, FilterType::LowShelf);

    let rec_preamp = calculate_recommended_preamp(&preset.bands, 0.5, 48000.0);
    assert!(rec_preamp <= -3.0);
}

#[test]
fn test_coordinate_descent_decimation() {
    // 10 bands down to 5 bands
    let mut bands = Vec::new();
    for i in 1..=10 {
        bands.push(BiquadBand::new(
            FilterType::Peaking,
            100.0 * i as f64,
            (i as f64 * 0.5) - 2.0,
            1.0,
        ));
    }

    let decimated = decimate_bands(&bands, 5, true, 48000.0);
    assert_eq!(decimated.len(), 5);

    let diff = calculate_curve_difference(&bands, 0.0, &decimated, 0.0, 48000.0, 100);
    assert!(diff.rms_db < 3.0);
}

#[test]
fn test_cx31993_safety_guard_blocks_flashing() {
    let preset = PeqPreset {
        name: "Test".into(),
        description: None,
        preamp: 0.0,
        slot_id: Some(3),
        bands: vec![BiquadBand::new(FilterType::Peaking, 1000.0, 1.0, 1.0)],
        full_bands: None,
    };

    // Attempting to encode KTMicro flash payload for Conexant VID 0x0572 must fail!
    let res = encode_preset_payload(&preset, CONEXANT_VID, CONEXANT_PID, 3, false, true);
    assert!(res.is_err());
    match res {
        Err(DacError::SafetyGuard(msg)) => {
            assert!(msg.contains("Conexant CX31993"));
            assert!(msg.contains("fixed mask ROM"));
        }
        _ => panic!("Expected SafetyGuard error"),
    }
}

#[test]
fn test_allegro_mini_guardrail_omits_preamp_register_0x66() {
    let preset = PeqPreset {
        name: "Allegro Test".into(),
        description: None,
        preamp: -3.0, // Non-zero preamp
        slot_id: Some(3),
        bands: vec![BiquadBand::new(FilterType::Peaking, 1000.0, 1.0, 1.0)],
        full_bands: None,
    };

    // For Kiwi Ears Allegro Mini (0x31B2:0x0111), register 0x66 must NOT be emitted
    let reports = encode_preset_payload(&preset, 0x31B2, 0x0111, 3, true, true)
        .expect("Payload generation failed");

    // Check that no packet targets address 0x66
    for r in &reports {
        let bytes = r.as_bytes();
        assert_ne!(bytes[1], REG_PREAMP, "Register 0x66 write detected on Allegro Mini!");
        assert_ne!(bytes[1], REG_FILTER, "Register 0x11 write detected on Allegro Mini!");
    }

    // Last report must be 0x53 COMMIT
    let last = reports.last().unwrap().as_bytes();
    assert_eq!(last[0], RPT_ID);
    assert_eq!(last[5], CMD_COMMIT);
}

#[test]
fn test_ktmicro_zero_db_preamp_writes_register_0x66() {
    let preset = PeqPreset {
        name: "Zero Preamp Test".into(),
        description: None,
        preamp: 0.0,
        slot_id: Some(3),
        bands: vec![BiquadBand::new(FilterType::Peaking, 1000.0, 1.0, 1.0)],
        full_bands: None,
    };

    // For non-Allegro hardware (FiiO JA11 0x2972:0x0102), register 0x66 must be emitted with gain byte 0x00
    let reports = encode_preset_payload(&preset, 0x2972, 0x0102, 3, false, true)
        .expect("Payload generation failed");

    let preamp_rpt = reports
        .iter()
        .find(|r| r.as_bytes()[1] == REG_PREAMP)
        .expect("Register 0x66 was not emitted for FiiO JA11 with 0.0 dB preamp!");

    let bytes = preamp_rpt.as_bytes();
    assert_eq!(bytes[0], RPT_ID);
    assert_eq!(bytes[1], REG_PREAMP);
    assert_eq!(bytes[5], CMD_WRITE);
    assert_eq!(bytes[7], 0x00, "0.0 dB preamp must emit gain byte 0x00");

    // For Allegro Mini (0x31B2:0x0111), register 0x66 must still be omitted
    let allegro_reports = encode_preset_payload(&preset, 0x31B2, 0x0111, 3, true, true)
        .expect("Payload generation failed");
    assert!(
        !allegro_reports.iter().any(|r| r.as_bytes()[1] == REG_PREAMP),
        "Register 0x66 must be omitted on Allegro Mini even with 0.0 dB preamp!"
    );

    // An unlisted PID under VID 0x31B2 is no longer assumed to be KTMicro: the guard
    // refuses it outright, which is what protects the user from writing to a device
    // whose architecture the tool cannot confirm.
    let err = encode_preset_payload(&preset, 0x31B2, 0x9999, 3, true, true)
        .expect_err("Unknown device must be refused");
    assert!(format!("{err}").contains("SAFETY GUARD"), "expected a guard refusal, got: {err}");
}

#[test]
fn test_ktmicro_preamp_safety_clamping_prevents_int8_overflow() {
    let mut preset = PeqPreset {
        name: "Extreme Attenuation Test".into(),
        description: None,
        preamp: -70.0, // Without clamp, (-140) & 0xff = 116 (+58 dB boost acoustic hazard!)
        slot_id: Some(3),
        bands: vec![BiquadBand::new(FilterType::Peaking, 1000.0, 0.0, 1.0)],
        full_bands: None,
    };

    let reports = encode_preset_payload(&preset, 0x2972, 0x0102, 3, false, true)
        .expect("Payload generation failed");
    let preamp_rpt = reports
        .iter()
        .find(|r| r.as_bytes()[1] == REG_PREAMP)
        .expect("Register 0x66 expected");
    let bytes = preamp_rpt.as_bytes();
    // -24.0 dB * 2 = -48 -> as i8 as u8 = 208 (0xD0)
    assert_eq!(bytes[7], (-48i8) as u8, "-70.0 dB must clamp to -24.0 dB (-48 byte)");

    // Test extreme positive boost (+30.0 dB -> clamps to +12.0 dB = +24 byte)
    preset.preamp = 30.0;
    let reports_pos = encode_preset_payload(&preset, 0x2972, 0x0102, 3, false, true)
        .expect("Payload generation failed");
    let preamp_rpt_pos = reports_pos
        .iter()
        .find(|r| r.as_bytes()[1] == REG_PREAMP)
        .expect("Register 0x66 expected");
    assert_eq!(preamp_rpt_pos.as_bytes()[7], 24u8, "+30.0 dB must clamp to +12.0 dB (24 byte)");
}

#[test]
fn test_exporters_pipewire_and_apo() {
    let mut disabled_band = BiquadBand::new(FilterType::HighShelf, 10000.0, 3.0, 0.71);
    disabled_band.enabled = false;

    let preset = PeqPreset {
        name: "BASN Test".into(),
        description: Some("Test bass tune".into()),
        preamp: -2.0,
        slot_id: Some(3),
        bands: vec![
            BiquadBand::new(FilterType::LowShelf, 50.0, 2.5, 0.71),
            BiquadBand::new(FilterType::Peaking, 2200.0, 1.5, 1.3),
            disabled_band,
        ],
        full_bands: None,
    };

    let pw = format_pipewire_filter_chain(&preset, DEFAULT_CX31993_SINK)
        .expect("PipeWire format failed");
    assert!(pw.contains("libpipewire-module-filter-chain"));
    assert!(pw.contains("eq_band1_fl"));
    assert!(pw.contains("bq_lowshelf"));
    assert!(pw.contains("preamp_fl"));
    assert!(pw.contains(r#"node.target      = "alsa_output.usb-Conexant_CX31993*""#));
    assert!(pw.contains(r#""Gain" = 0.00"#));

    let apo = format_equalizer_apo(&preset);
    assert!(apo.contains("Preamp: -2.0 dB"));
    assert!(apo.contains("Filter 1: ON LSQ Fc 50.0 Hz Gain +2.5 dB Q 0.71"));
    assert!(apo.contains("Filter 3: OFF HSQ Fc 10000.0 Hz Gain +3.0 dB Q 0.71"));

    let wav = format_wavelet_graphiceq(&preset);
    assert!(wav.starts_with("GraphicEQ: 20 "));
}

#[test]
fn test_ktmicro_encode_preset_payload_zeroes_disabled_band_gain() {
    let mut b1 = BiquadBand::new(FilterType::Peaking, 1000.0, 6.0, 1.414);
    b1.enabled = false;

    let preset = PeqPreset {
        name: "Muted Band Test".into(),
        description: None,
        preamp: 0.0,
        slot_id: Some(3),
        bands: vec![b1],
        full_bands: None,
    };

    let reports = encode_preset_payload(&preset, 0x31B2, 0x0111, 3, false, false)
        .expect("encode payload");

    // Band 1 Register 0x26 should have 0 gain (bytes 7..9: 0x00, 0x00)
    let rpt_band1 = reports.iter().find(|r| r.as_bytes()[1] == 0x26).expect("band 1 rpt");
    let bytes = rpt_band1.as_bytes();
    assert_eq!(bytes[7], 0x00);
    assert_eq!(bytes[8], 0x00);
}

#[test]
fn test_moondrop_encode_report_9_bands() {
    let mut bands = Vec::new();
    for i in 1..=5 {
        bands.push(BiquadBand::new(FilterType::Peaking, 200.0 * i as f64, 1.5, 1.0));
    }
    let rpt = encode_moondrop_report(&bands, -3.0, true).unwrap();
    assert_eq!(rpt[0], 0x21); // commit flash
    assert_eq!(rpt[1], 0x09); // 9 bands
    assert_eq!(rpt[2] as i8, -6); // -3.0 * 2 = -6
    assert_eq!(rpt.len(), 64);
}

#[test]
fn test_refit_decimated_gains_reduces_mse() {
    let mut orig_bands = Vec::new();
    let freqs = [60.0, 120.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 12000.0];
    let gains = [3.5, 2.0, -1.5, 0.5, -2.0, 3.0, 4.5, -1.0, 2.5, -3.0];
    for (f, g) in freqs.iter().zip(gains.iter()) {
        orig_bands.push(BiquadBand::new(FilterType::Peaking, *f, *g, 1.414));
    }

    // Decimate to 5 bands WITHOUT refit
    let decimated_initial = decimate_bands(&orig_bands, 5, false, 48000.0);
    assert_eq!(decimated_initial.len(), 5);

    let test_points = generate_log_frequencies(20.0, 20000.0, 128);
    let target_curve = compute_composite_response(&orig_bands, 0.0, &test_points, 48000.0);
    let initial_curve = compute_composite_response(&decimated_initial, 0.0, &test_points, 48000.0);
    let initial_mse: f64 = initial_curve
        .iter()
        .zip(target_curve.iter())
        .map(|(c, t)| (c - t).powi(2))
        .sum::<f64>()
        / test_points.len() as f64;

    // Refit gains
    let refitted = refit_decimated_gains(&orig_bands, &decimated_initial, 48000.0);
    assert_eq!(refitted.len(), 5);

    let refitted_curve = compute_composite_response(&refitted, 0.0, &test_points, 48000.0);
    let refitted_mse: f64 = refitted_curve
        .iter()
        .zip(target_curve.iter())
        .map(|(c, t)| (c - t).powi(2))
        .sum::<f64>()
        / test_points.len() as f64;

    // Refit must strictly reduce or maintain MSE
    assert!(
        refitted_mse <= initial_mse + 1e-9,
        "Refitted MSE ({}) should be <= initial MSE ({})",
        refitted_mse,
        initial_mse
    );

    // Verify all gains are within [-18.0, 18.0] and rounded to 0.01 dB
    for b in &refitted {
        assert!(
            (-18.0..=18.0).contains(&b.gain),
            "Gain {} out of [-18, 18] bounds",
            b.gain
        );
        let rounded = (b.gain * 100.0).round() / 100.0;
        assert!(
            (b.gain - rounded).abs() < 1e-6,
            "Gain {} not rounded to 0.01 dB",
            b.gain
        );
    }
}

#[test]
fn test_decimate_bands_5_to_10_expansion() {
    // 5-band input with max frequency >= 6000 Hz and no HighShelf
    let bands = vec![
        BiquadBand::new(FilterType::LowShelf, 100.0, 4.0, 0.71),
        BiquadBand::new(FilterType::Peaking, 500.0, -2.0, 1.4),
        BiquadBand::new(FilterType::Peaking, 1500.0, 3.0, 1.0),
        BiquadBand::new(FilterType::Peaking, 3000.0, -1.5, 2.0),
        BiquadBand::new(FilterType::Peaking, 8000.0, 2.5, 1.414),
    ];

    let target = 10;
    let expanded = decimate_bands(&bands, target, true, 48000.0);
    assert_eq!(expanded.len(), 10);

    // Verify high shelf synthesis at 12500.0 Hz with gain 0.0 and Q 0.71
    let hs_bands: Vec<&BiquadBand> = expanded
        .iter()
        .filter(|b| b.filter_type == FilterType::HighShelf && (b.freq - 12500.0).abs() < 1e-3)
        .collect();
    assert_eq!(hs_bands.len(), 1, "Should synthesize exactly one HighShelf at 12500.0 Hz");
    let hs = hs_bands[0];
    assert_eq!(hs.gain, 0.0, "HighShelf gain must be 0.0");
    assert!((hs.q - 0.71).abs() < 1e-3, "HighShelf Q must be 0.71");

    // Verify padded PK bands have gain 0.0 and Q 1.0
    let padded_pk_bands: Vec<&BiquadBand> = expanded
        .iter()
        .filter(|b| b.gain == 0.0 && b.filter_type == FilterType::Peaking)
        .collect();
    assert_eq!(padded_pk_bands.len(), 4, "Should have 4 padded PK bands with gain 0.0");
    for pb in &padded_pk_bands {
        assert!((pb.q - 1.0).abs() < 1e-3, "Padded PK band Q should be 1.0");
    }

    // Verify zero curve alteration (all added bands have 0.0 dB gain)
    let diff = calculate_curve_difference(&bands, 0.0, &expanded, 0.0, 48000.0, 100);
    assert!(
        diff.rms_db < 1e-6,
        "Expanding bands with 0.0 dB pads should produce 0.0 dB curve alteration, got {}",
        diff.rms_db
    );

    // Verify sorted by frequency
    for i in 0..(expanded.len() - 1) {
        assert!(
            expanded[i].freq <= expanded[i + 1].freq,
            "Bands are not sorted by frequency"
        );
    }

    // Verify 1-based indices
    for (i, b) in expanded.iter().enumerate() {
        assert_eq!(b.index, Some(i + 1));
    }
}

#[test]
fn test_biquad_band_enabled_muting() {
    let mut b1 = BiquadBand::new(FilterType::Peaking, 1000.0, 6.0, 1.414);
    let b2 = BiquadBand::new(FilterType::Peaking, 1000.0, 3.0, 1.414);

    let freqs = [1000.0];
    let resp_active = compute_composite_response(&[b1.clone(), b2.clone()], 0.0, &freqs, 48000.0);
    assert!((resp_active[0] - 9.0).abs() < 1e-3);

    // Mute b1 (enabled: false)
    b1.enabled = false;
    let resp_muted = compute_composite_response(&[b1.clone(), b2.clone()], 0.0, &freqs, 48000.0);
    assert!((resp_muted[0] - 3.0).abs() < 1e-3);

    // calculate_peak_composite_gain should ignore disabled band
    let peak = calculate_peak_composite_gain(&[b1], 48000.0, 50);
    assert_eq!(peak, 0.0);
}

#[test]
fn test_band_deserialization_default_enabled() {
    let json_str = r#"{"type": "PK", "freq": 1000.0, "gain": 2.0, "q": 1.0}"#;
    let band: BiquadBand = serde_json::from_str(json_str).expect("Deserialize band");
    assert!(band.enabled, "Default enabled should be true");

    let json_disabled = r#"{"type": "PK", "freq": 1000.0, "gain": 2.0, "q": 1.0, "enabled": false}"#;
    let disabled_band: BiquadBand = serde_json::from_str(json_disabled).expect("Deserialize disabled band");
    assert!(!disabled_band.enabled);
}

#[test]
fn test_lint_acoustic_bands_ignores_disabled_bands() {
    // 1. 711 coupler artifact band
    let mut b_coupler = BiquadBand::new(FilterType::Peaking, 8000.0, -4.0, 3.0);
    // 2. Extreme boost band
    let mut b_boost = BiquadBand::new(FilterType::Peaking, 1000.0, 8.0, 1.0);
    // 3. Ultra high-Q ringing band
    let mut b_ringing = BiquadBand::new(FilterType::Peaking, 3000.0, 2.0, 6.0);

    // When all are enabled, 3 warnings should be produced
    let warnings_active = lint_acoustic_bands(&[b_coupler.clone(), b_boost.clone(), b_ringing.clone()]);
    assert_eq!(warnings_active.len(), 3);

    // Disable all three
    b_coupler.enabled = false;
    b_boost.enabled = false;
    b_ringing.enabled = false;

    let warnings_disabled = lint_acoustic_bands(&[b_coupler, b_boost, b_ringing]);
    assert!(
        warnings_disabled.is_empty(),
        "Disabled bands must not generate acoustic lint warnings: {:?}",
        warnings_disabled
    );
}

#[test]
fn test_decimate_bands_disabled_bands_do_not_displace_active_bands() {
    // 10 bands: 5 active landmark bands and 5 disabled bands with huge gains
    let mut bands = vec![
        BiquadBand::new(FilterType::LowShelf, 100.0, 5.0, 0.71),   // Active 1
        BiquadBand::new(FilterType::Peaking, 250.0, 15.0, 1.0),    // Disabled
        BiquadBand::new(FilterType::Peaking, 500.0, -3.0, 1.414),  // Active 2
        BiquadBand::new(FilterType::Peaking, 1200.0, 15.0, 1.0),   // Disabled
        BiquadBand::new(FilterType::Peaking, 2500.0, 4.0, 2.0),    // Active 3
        BiquadBand::new(FilterType::Peaking, 3500.0, 15.0, 1.0),   // Disabled
        BiquadBand::new(FilterType::Peaking, 4500.0, -2.0, 1.5),   // Active 4
        BiquadBand::new(FilterType::Peaking, 6500.0, 15.0, 1.0),   // Disabled
        BiquadBand::new(FilterType::HighShelf, 9000.0, 3.0, 0.71), // Active 5
        BiquadBand::new(FilterType::Peaking, 14000.0, 15.0, 1.0),  // Disabled
    ];

    bands[1].enabled = false;
    bands[3].enabled = false;
    bands[5].enabled = false;
    bands[7].enabled = false;
    bands[9].enabled = false;

    // Decimate from 10 bands down to 5 bands
    let decimated = decimate_bands(&bands, 5, false, 48000.0);
    assert_eq!(decimated.len(), 5);

    // All 5 decimated bands should preserve the 5 active frequencies
    let expected_freqs = [100.0, 500.0, 2500.0, 4500.0, 9000.0];
    for (i, b) in decimated.iter().enumerate() {
        assert!(
            (b.freq - expected_freqs[i]).abs() < 1e-3,
            "Expected freq {} at index {}, got {}",
            expected_freqs[i],
            i,
            b.freq
        );
        assert!(
            b.enabled,
            "Decimated active bands should be enabled"
        );
    }

    // Also test fallback when all bands are disabled: should not panic
    let all_disabled: Vec<BiquadBand> = bands.into_iter().map(|mut b| { b.enabled = false; b }).collect();
    let decimated_fallback = decimate_bands(&all_disabled, 5, false, 48000.0);
    assert_eq!(decimated_fallback.len(), 5);
}
