use dac_peq_core::fitter::{
    fit_measurement_to_target, parse_fr_text, StandardTarget,
};
use dac_peq_core::models::FilterType;

#[test]
fn test_parse_fr_text() {
    let raw = r#"
# Measured with IEC 60318-4 coupler
20.0, 75.0
50.0, 76.5
100.0, 77.0
1000.0, 80.0
3000.0, 88.0
10000.0, 78.0
20000.0, 70.0
"#;
    let points = parse_fr_text(raw).expect("Should parse FR text");
    assert_eq!(points.len(), 7);
    assert_eq!(points[0].freq, 20.0);
    assert_eq!(points[0].db, 75.0);
    assert_eq!(points[3].freq, 1000.0);
}

#[test]
fn test_fit_measurement_5_bands_allegro_mini() {
    // Simulated measurement of a bass-light, treble-peaky IEM
    let raw = r#"
20.0, 68.0
50.0, 70.0
100.0, 72.0
200.0, 75.0
500.0, 78.0
1000.0, 80.0
2000.0, 83.0
3000.0, 86.0
4000.0, 82.0
6000.0, 80.0
8000.0, 92.0
10000.0, 85.0
15000.0, 75.0
20000.0, 65.0
"#;
    let preset = fit_measurement_to_target(
        raw,
        StandardTarget::HarmanInEar2019,
        5,
        true, // anchor shelves
        48000.0,
    )
    .expect("Fitting should succeed");

    assert_eq!(preset.bands.len(), 5);
    // Band 1 should be LowShelf boosting the weak bass
    assert_eq!(preset.bands[0].filter_type, FilterType::LowShelf);
    assert!(preset.bands[0].gain > 0.0);

    // Band 5 should be HighShelf
    assert_eq!(preset.bands[4].filter_type, FilterType::HighShelf);

    // Preamp should be non-positive to prevent clipping
    assert!(preset.preamp <= 0.0);
}

#[test]
fn test_fit_measurement_10_bands() {
    let raw = r#"
20.0, 72.0
100.0, 74.0
500.0, 78.0
1000.0, 80.0
3000.0, 85.0
8000.0, 88.0
16000.0, 70.0
"#;
    let preset = fit_measurement_to_target(
        raw,
        StandardTarget::IefNeutral,
        10,
        true,
        48000.0,
    )
    .expect("Fitting should succeed");

    assert_eq!(preset.bands.len(), 10);
    for (i, b) in preset.bands.iter().enumerate() {
        assert_eq!(b.index, Some(i + 1));
        assert!(b.freq >= 20.0 && b.freq <= 20000.0);
    }
}
