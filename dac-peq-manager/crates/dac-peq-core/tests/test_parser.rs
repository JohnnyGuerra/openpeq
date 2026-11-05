use dac_peq_core::models::FilterType;
use dac_peq_core::parser::{parse_preset_permissive, PresetFormat};

#[test]
fn test_parse_equalizer_apo() {
    let apo = r#"
# EqualizerAPO config
# Preset: Harman Target 2019
Preamp: -3.5 dB
Filter 1: ON PK Fc 105.0 Hz Gain +4.2 dB Q 0.71
Filter 2: ON LSQ Fc 80.0 Hz Gain +2.5 dB Q 0.71
Filter 3: OFF HSQ Fc 12000.0 Hz Gain -1.8 dB Q 0.71
"#;
    let res = parse_preset_permissive(apo).expect("Should parse APO format");
    assert_eq!(res.source_format, PresetFormat::EqualizerApo);
    assert_eq!(res.name, "Harman Target 2019");
    assert_eq!(res.preamp, -3.5);
    assert_eq!(res.bands.len(), 3);
    assert_eq!(res.bands[0].filter_type, FilterType::Peaking);
    assert_eq!(res.bands[0].freq, 105.0);
    assert_eq!(res.bands[0].gain, 4.2);
    assert!(res.bands[0].enabled);

    assert_eq!(res.bands[1].filter_type, FilterType::LowShelf);
    assert!(!res.bands[2].enabled);
    assert_eq!(res.bands[2].filter_type, FilterType::HighShelf);
}

#[test]
fn test_parse_poweramp_parametric_json() {
    let json_text = r#"{
        "name": "Kato Neutral",
        "preamp": -2.0,
        "PowerampEqualizer.parametric": [
            {"type": "lowshelf", "freq": 105.0, "gain": 3.5, "q": 0.71, "enabled": true},
            {"type": "peaking", "freq": 2500.0, "gain": -1.2, "q": 1.4, "enabled": true},
            {"type": "highshelf", "freq": 10000.0, "gain": 1.0, "q": 0.71, "enabled": true}
        ]
    }"#;
    let res = parse_preset_permissive(json_text).expect("Should parse Poweramp Parametric JSON");
    assert_eq!(res.source_format, PresetFormat::PowerampParametric);
    assert_eq!(res.name, "Kato Neutral");
    assert_eq!(res.preamp, -2.0);
    assert_eq!(res.bands.len(), 3);
    assert_eq!(res.bands[0].filter_type, FilterType::LowShelf);
    assert_eq!(res.bands[1].filter_type, FilterType::Peaking);
    assert_eq!(res.bands[2].filter_type, FilterType::HighShelf);
}

#[test]
fn test_parse_poweramp_graphic_string() {
    let str_text = "preamp=-1.500;31hz=1.000;62hz=2.000;125hz=0.500;1khz=-0.500;8khz=1.500;";
    let res = parse_preset_permissive(str_text).expect("Should parse Poweramp Graphic settings string");
    assert_eq!(res.source_format, PresetFormat::PowerampGraphic);
    assert_eq!(res.preamp, -1.5);
    assert_eq!(res.bands.len(), 5);
    assert_eq!(res.bands[0].freq, 31.0);
    assert_eq!(res.bands[3].freq, 1000.0);
    assert_eq!(res.bands[3].gain, -0.5);
}

#[test]
fn test_parse_autoeq_graphiceq_string() {
    let graphic_eq = "GraphicEQ: 20 0.0; 25 0.5; 32 1.2; 63 2.5; 1000 -1.0; 8000 2.0; 16000 -3.0";
    let res = parse_preset_permissive(graphic_eq).expect("Should parse GraphicEQ");
    assert_eq!(res.source_format, PresetFormat::AutoEqGraphicEq);
    assert_eq!(res.bands.len(), 7);
    assert_eq!(res.bands[0].freq, 20.0);
    assert_eq!(res.bands[0].gain, 0.0);
    assert_eq!(res.bands[3].freq, 63.0);
    assert_eq!(res.bands[3].gain, 2.5);
}

#[test]
fn test_parse_wavelet_json() {
    let wavelet_json = r#"{
        "name": "IEM Bass Boost",
        "preamp": -4.0,
        "filters": [
            {"type": "lowshelf", "frequency": 80.0, "gain": 4.0, "q": 0.707},
            {"type": "peaking", "frequency": 3000.0, "gain": 2.5, "q": 2.0}
        ]
    }"#;
    let res = parse_preset_permissive(wavelet_json).expect("Should parse Wavelet JSON");
    assert_eq!(res.source_format, PresetFormat::Wavelet);
    assert_eq!(res.name, "IEM Bass Boost");
    assert_eq!(res.preamp, -4.0);
    assert_eq!(res.bands.len(), 2);
    assert_eq!(res.bands[0].filter_type, FilterType::LowShelf);
    assert_eq!(res.bands[1].filter_type, FilterType::Peaking);
}
