use crate::models::{BiquadBand, FilterType};

pub const WALKPLAY_RPT_ID: u8 = 0x4B;
pub const WALKPLAY_RPT_WRITE_LEN: usize = 37;
pub const WALKPLAY_RPT_READ_REQ_LEN: usize = 6;

pub const WALKPLAY_CMD_FLASH_EQ: u8 = 0x01;
pub const WALKPLAY_CMD_MIC_GAIN: u8 = 0x02;
pub const WALKPLAY_CMD_GLOBAL_GAIN: u8 = 0x03;
pub const WALKPLAY_CMD_PEQ_VALUES: u8 = 0x09;
pub const WALKPLAY_CMD_TEMP_WRITE: u8 = 0x0A;
pub const WALKPLAY_CMD_VERSION: u8 = 0x0C;
pub const WALKPLAY_CMD_GET_SLOT: u8 = 0x0F;
pub const WALKPLAY_CMD_DAC_FILTER: u8 = 0x11;
pub const WALKPLAY_CMD_DAC_BALANCE: u8 = 0x16;

pub const OP_WRITE: u8 = 0x01;
pub const OP_READ: u8 = 0x80;
pub const END_BYTE: u8 = 0x00;

/// Compute 20-byte Q2.30 biquad coefficient array for WalkPlay DSP at 96 kHz.
/// Matches official WalkPlay hardware DSP encoder.
pub fn compute_walkplay_biquad(freq: f64, gain: f64, q: f64) -> [u8; 20] {
    if gain.abs() < 1e-6 {
        return [0u8; 20];
    }

    let a = 10f64.powf(gain / 40.0);
    let w0 = (freq * 2.0 * std::f64::consts::PI) / 96000.0;
    let sinw0 = w0.sin();
    let cosw0 = w0.cos();
    let alpha = sinw0 / (2.0 * q.max(0.01));

    let b0 = 1.0 + alpha * a;
    let b1 = -2.0 * cosw0;
    let b2 = 1.0 - alpha * a;
    let a0 = 1.0 + alpha / a;
    let a1 = -2.0 * cosw0;
    let a2 = 1.0 - alpha / a;

    let scale = 1073741824.0; // 2^30
    let i_b0 = (b0 / a0 * scale).round() as i32;
    let i_b1 = (b1 / a0 * scale).round() as i32;
    let i_b2 = (b2 / a0 * scale).round() as i32;
    let i_neg_a1 = (-(a1 / a0) * scale).round() as i32;
    let i_neg_a2 = (-(a2 / a0) * scale).round() as i32;

    let mut out = [0u8; 20];
    out[0..4].copy_from_slice(&i_b0.to_le_bytes());
    out[4..8].copy_from_slice(&i_b1.to_le_bytes());
    out[8..12].copy_from_slice(&i_b2.to_le_bytes());
    out[12..16].copy_from_slice(&i_neg_a1.to_le_bytes());
    out[16..20].copy_from_slice(&i_neg_a2.to_le_bytes());
    out
}

/// Encode a single filter packet (37 bytes) for WalkPlay Scheme 11 / Scheme 16 devices.
/// [0x01, 0x09, 0x18, 0x00, filter_idx, 0x00, 0x00, ...bArr(20), freq(2), q(2), gain(2), type(1), 0x00, slot(1), 0x00]
pub fn encode_walkplay_filter_packet(
    filter_idx: u8,
    freq: f64,
    gain: f64,
    q: f64,
    filter_type: FilterType,
    slot: u8,
) -> [u8; WALKPLAY_RPT_WRITE_LEN] {
    let mut pkt = [0u8; WALKPLAY_RPT_WRITE_LEN];
    pkt[0] = OP_WRITE;
    pkt[1] = WALKPLAY_CMD_PEQ_VALUES;
    pkt[2] = 0x18; // 24 bytes payload
    pkt[3] = 0x00;
    pkt[4] = filter_idx;
    pkt[5] = 0x00;
    pkt[6] = 0x00;

    let biquad_bytes = compute_walkplay_biquad(freq, gain, q);
    pkt[7..27].copy_from_slice(&biquad_bytes);

    let freq_u16 = freq.round().clamp(10.0, 48000.0) as u16;
    let q_u16 = (q * 256.0).round().clamp(1.0, 65535.0) as u16;
    let gain_i16 = (gain * 256.0).round().clamp(-32768.0, 32767.0) as i16;

    pkt[27..29].copy_from_slice(&freq_u16.to_le_bytes());
    pkt[29..31].copy_from_slice(&q_u16.to_le_bytes());
    pkt[31..33].copy_from_slice(&gain_i16.to_le_bytes());
    pkt[33] = filter_type.to_walkplay_id();
    pkt[34] = 0x00;
    pkt[35] = slot;
    pkt[36] = END_BYTE;

    pkt
}

/// Decode a filter packet returned by WalkPlay DSP into a BiquadBand.
pub fn decode_walkplay_filter_packet(packet: &[u8]) -> Option<BiquadBand> {
    if packet.len() < 34 {
        return None;
    }

    let filter_idx = packet[4] as usize;
    let freq_raw = u16::from_le_bytes([packet[27], packet[28]]);
    let q_raw = u16::from_le_bytes([packet[29], packet[30]]);
    let gain_raw = i16::from_le_bytes([packet[31], packet[32]]);
    let type_raw = packet[33];

    // Check for unset / uninitialized memory marker (0xFFFF)
    if freq_raw == 0xFFFF && q_raw == 0xFFFF && gain_raw == -1 {
        return Some(BiquadBand {
            index: Some(filter_idx),
            enabled: true,
            filter_type: FilterType::Peaking,
            freq: 0.0,
            gain: 0.0,
            q: 0.0,
        });
    }

    let freq = freq_raw as f64;
    let q = (q_raw as f64) / 256.0;
    let gain = (gain_raw as f64) / 256.0;
    let filter_type = FilterType::from_walkplay_id(type_raw);

    Some(BiquadBand {
        index: Some(filter_idx),
        enabled: true,
        filter_type,
        freq,
        gain,
        q,
    })
}

/// Encode global preamp / gain command: [0x01, 0x03, 0x02, 0x00, gain_db]
pub fn encode_walkplay_global_gain(gain_db: f64) -> [u8; 5] {
    let int8 = gain_db.round().clamp(-128.0, 127.0) as i8;
    [OP_WRITE, WALKPLAY_CMD_GLOBAL_GAIN, 0x02, 0x00, int8 as u8]
}

/// Flash save and commit sequence for WalkPlay Scheme 11 / Scheme 16 devices.
/// Sequence matches official CrinEar / WalkPlay tool:
/// 1. [0x01, 0x05, 0x00]
/// 2. [0x01, 0x17, 0x00]
/// 3. [0x01, 0x0A, 0x04, 0x00, 0x00, 0xFF, 0xFF, 0x00]
/// 4. [0x01, 0x01, 0x01, 0x00]
pub fn get_walkplay_commit_sequence() -> Vec<Vec<u8>> {
    vec![
        vec![OP_WRITE, 0x05, END_BYTE],
        vec![OP_WRITE, 0x17, END_BYTE],
        vec![OP_WRITE, WALKPLAY_CMD_TEMP_WRITE, 0x04, 0x00, 0x00, 0xFF, 0xFF, END_BYTE],
        vec![OP_WRITE, WALKPLAY_CMD_FLASH_EQ, 0x01, END_BYTE],
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_walkplay_filter_packet_exact_match() {
        // Filter 2 from captured Protocol Micro log:
        // freq: 500, q: 1.50, gain: 8.0 dB, type: PK, slot: 101
        let pkt = encode_walkplay_filter_packet(2, 500.0, 8.0, 1.5, FilterType::Peaking, 101);
        let expected_prefix = [0x01, 0x09, 0x18, 0x00, 0x02, 0x00, 0x00];
        assert_eq!(&pkt[0..7], &expected_prefix);

        // Biquad coeffs check:
        let expected_biquad = [
            0x2C, 0x4B, 0xA9, 0x40, 0xEC, 0x5F, 0xF1, 0x80, 0x94, 0xC1, 0x76, 0x3E, 0x14, 0xA0,
            0x0E, 0x7F, 0x41, 0xF3, 0xDF, 0xC0,
        ];
        assert_eq!(&pkt[7..27], &expected_biquad);

        // Metadata check:
        // freq 500 = 0x01F4 -> [0xF4, 0x01]
        assert_eq!(&pkt[27..29], &[0xF4, 0x01]);
        // q 1.5 * 256 = 384 = 0x0180 -> [0x80, 0x01]
        assert_eq!(&pkt[29..31], &[0x80, 0x01]);
        // gain 8.0 * 256 = 2048 = 0x0800 -> [0x00, 0x08]
        assert_eq!(&pkt[31..33], &[0x00, 0x08]);
        // type PK = 2
        assert_eq!(pkt[33], 2);
        // slot = 101
        assert_eq!(pkt[35], 101);
    }

    #[test]
    fn test_walkplay_decode_filter_packet() {
        let pkt = encode_walkplay_filter_packet(1, 200.0, 4.0, 0.20, FilterType::Peaking, 101);
        let decoded = decode_walkplay_filter_packet(&pkt).expect("Should decode");
        assert_eq!(decoded.index, Some(1));
        assert_eq!(decoded.freq, 200.0);
        assert!((decoded.gain - 4.0).abs() < 0.01);
        assert!((decoded.q - 0.20).abs() < 0.01);
        assert_eq!(decoded.filter_type, FilterType::Peaking);
    }
}
