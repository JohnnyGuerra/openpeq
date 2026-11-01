use dac_peq_core::codec::safety;
use dac_peq_core::codec::walkplay::encode_walkplay_filter_packet;
use dac_peq_core::models::FilterType;

/// The guard must read the shared dacs.json at runtime, not carry its own copy of the
/// device list.
#[test]
fn guard_reads_the_shared_table_at_runtime() {
    let table = safety::table().expect("the shared device table must be readable");
    let jcallly = safety::match_device(table, 0x0572, 0x1B08, None)
        .expect("the JCALLY JM6 Pro must be in the shared table");
    assert_eq!(jcallly.architecture, "conexant_fixed");
    let err = format!(
        "{}",
        safety::assert_safe_for_hardware_flash(0x0572, 0x1B08, None).unwrap_err()
    );
    assert!(err.contains("SAFETY GUARD"), "{err}");
    assert!(err.contains("mask ROM"), "{err}");
}

#[test]
fn guard_refuses_a_device_it_cannot_confirm() {
    let table = safety::table().unwrap();
    assert!(safety::match_device(table, 0x18D1, 0x1908, None).is_none());
    let err = format!(
        "{}",
        safety::assert_safe_for_hardware_flash(0x18D1, 0x1908, None).unwrap_err()
    );
    assert!(err.contains("cannot confirm the identity"), "{err}");
}

/// A product string is enough to resolve identity when the numeric id is not in the table.
#[test]
fn product_string_resolves_identity() {
    let table = safety::table().unwrap();
    let entry = safety::match_device(table, 0x3302, 0x3365, Some("CX31993 DSP"))
        .expect("a Conexant product string must resolve to the blocked architecture");
    assert_eq!(entry.architecture, "conexant_fixed");
}

/// Nothing may be packed from a value the guard has rejected - a partial write is what
/// corrupts the device.
#[test]
fn out_of_range_band_is_refused_before_any_packet_is_built() {
    let err = encode_walkplay_filter_packet(3, 48001.0, 0.0, 4.0, FilterType::Peaking, 101)
        .expect_err("a frequency above the accepted range must be refused");
    let msg = format!("{err}");
    assert!(msg.contains("SAFETY GUARD"), "{msg}");
    assert!(msg.contains("band 3"), "{msg}");
    assert!(msg.contains("20000"), "{msg}");
}

/// The packability backstop is defence in depth: with the table ranges it cannot be
/// reached, so the guard names the band before anything is packed.
#[test]
fn guard_names_the_band_it_rejected() {
    let err = encode_walkplay_filter_packet(2, 0.0, 25.0, 4.0, FilterType::Peaking, 101)
        .expect_err("gain above the accepted range must be refused");
    let msg = format!("{err}");
    assert!(msg.contains("band 2"), "{msg}");
    assert!(msg.contains("20"), "{msg}");
}
