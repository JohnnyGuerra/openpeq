use crate::biquad::calculate_rbj_biquad;
use crate::codec::safety;
use crate::error::{DacError, Result};
use crate::models::{BiquadBand, FilterType};

pub const MOONDROP_VID: u16 = 0x31B2;
pub const MOONDROP_PID: u16 = 0x0112;
pub const MOONDROP_BANDS: usize = 9;
pub const MOONDROP_CMD_APPLY_RAM: u8 = 0x20;
pub const MOONDROP_CMD_FLASH_COMMIT: u8 = 0x21;

/// Encode Moondrop FreeDSP 64-byte Q28 biquad report.
/// Frame format:
///   [0]: 0x20 (Apply RAM) or 0x21 (Flash Commit)
///   [1]: 0x09 (9 bands)
///   [2]: preamp * 2.0 (i8 as u8)
///   [3..57]: 9 bands * 6 bytes:
///     [0..3]: b0 Q28 >> 8 (24-bit signed LE)
///     [3..6]: -a1 Q28 >> 8 (24-bit signed LE)
///   [57..64]: padding 0x00
pub fn encode_moondrop_report(
    bands: &[BiquadBand],
    preamp_db: f64,
    commit_flash: bool,
) -> Result<[u8; 64]> {
    let mut payload = [0u8; 64];
    payload[0] = if commit_flash {
        MOONDROP_CMD_FLASH_COMMIT
    } else {
        MOONDROP_CMD_APPLY_RAM
    };
    payload[1] = MOONDROP_BANDS as u8;

    let preamp_scaled = (preamp_db * 2.0).round().clamp(-128.0, 127.0) as i8;
    payload[2] = preamp_scaled as u8;

    let mut offset = 3;
    let dummy = BiquadBand::new(FilterType::Peaking, 1000.0, 0.0, 1.0);

    for i in 0..MOONDROP_BANDS {
        let band = bands.get(i).unwrap_or(&dummy);
        let eff_gain = if band.enabled { band.gain } else { 0.0 };
        safety::validate_band(safety::table()?, "moondrop_dsp", i, band.freq, eff_gain, band.q)?;

        let c = calculate_rbj_biquad(band.filter_type, band.freq, eff_gain, band.q, 48000.0);

        let scale = (1u64 << 28) as f64;
        let pack_i32 = |v: f64| -> Result<i32> {
            if !v.is_finite() || v < i32::MIN as f64 || v > i32::MAX as f64 {
                return Err(DacError::InvalidFilter(format!(
                    "SAFETY GUARD: write rejected - band {i}: coefficient {v} cannot be packed (int32)."
                )));
            }
            Ok(v.round() as i32)
        };
        let b0 = pack_i32(c.b0 * scale)?;
        let b0_24 = b0 >> 8;
        payload[offset] = (b0_24 & 0xFF) as u8;
        payload[offset + 1] = ((b0_24 >> 8) & 0xFF) as u8;
        payload[offset + 2] = ((b0_24 >> 16) & 0xFF) as u8;

        let a1 = pack_i32(-c.a1 * scale)?;
        let a1_24 = a1 >> 8;
        payload[offset + 3] = (a1_24 & 0xFF) as u8;
        payload[offset + 4] = ((a1_24 >> 8) & 0xFF) as u8;
        payload[offset + 5] = ((a1_24 >> 16) & 0xFF) as u8;

        offset += 6;
    }

    Ok(payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encode_moondrop_report_header_and_length() {
        let bands = vec![
            BiquadBand::new(FilterType::Peaking, 1000.0, 3.0, 1.414),
            BiquadBand::new(FilterType::LowShelf, 105.0, 5.0, 0.71),
        ];

        let rpt_ram = encode_moondrop_report(&bands, -2.5, false).unwrap();
        assert_eq!(rpt_ram[0], 0x20);
        assert_eq!(rpt_ram[1], 0x09);
        assert_eq!(rpt_ram[2] as i8, -5); // -2.5 * 2 = -5

        let rpt_flash = encode_moondrop_report(&bands, -2.5, true).unwrap();
        assert_eq!(rpt_flash[0], 0x21);
    }

    #[test]
    fn test_encode_moondrop_report_disabled_band_zero_gain() {
        let mut b = BiquadBand::new(FilterType::Peaking, 1000.0, 6.0, 1.414);
        b.enabled = false;

        let rpt_disabled = encode_moondrop_report(&[b], 0.0, false).unwrap();

        // When gain is 0 dB, c.b0 = 1.0.
        // b0_q28 = 2^28 = 0x10000000. b0_24 = 0x100000.
        // in 3 bytes LE: [0x00, 0x00, 0x10].
        assert_eq!(&rpt_disabled[3..6], &[0x00, 0x00, 0x10]);
    }
}
