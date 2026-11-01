# openpeq Domain Glossary

This document records the canonical domain terms, acronyms, and hardware abstractions used across `openpeq` (Web Flasher, Rust Core, Python CLI).

## Hardware & Audio Concepts

- **PEQ (Parametric Equalizer)**: Audio equalizer that processes signal through parametric biquad filter stages with configurable center frequency ($f_0$), gain ($\text{dB}$), and quality factor ($Q$).
- **Biquad Filter**: Second-order IIR (Infinite Impulse Response) recursive digital filter stage characterized by coefficients $[b_0, b_1, b_2, a_1, a_2]$.
- **NVRAM Flash Commit**: Writing active filter parameters to non-volatile on-chip EEPROM or NOR Flash so the equalization curve persists across device reboots and unpowered states without host software running.
- **Audition Mode (RAM Write)**: Writing filter parameters directly to MCU runtime SRAM for instant acoustic listening without consuming physical flash burn endurance cycles.
- **Stock Backup**: An automated snapshot taken prior to the very first flash burn to guarantee 1-click restore to manufacturer-default settings.

## Silicon DSP Architectures

- **KTMicro KT02H20**: 5-band hardware PEQ DSP microcontroller (`0x31B2`, `0x2972`). Communicates over WebHID / HID Report ID `0x4B` with 11-byte command framing (`0x57` Write, `0x52` Read, `0x53` Commit, `0x43` Reset).
- **WalkPlay CB1300D**: Multi-band hardware PEQ DSP architecture (`0x3302`) supporting Scheme 11 (8-band, e.g. CrinEar Protocol Micro) and Scheme 16 (10-band, e.g. CrinEar Protocol Max, Tanchjim SPACE Pro). Employs 96 kHz Q2.30 biquad integers and Report ID `0x4B` (37-byte write frames).
- **Moondrop DSP**: 9-band hardware PEQ architecture (`0x31B2:0x0112`, e.g. FreeDSP, May Cable, Chu II DSP) communicating via 64-byte HID report frames.
- **Fixed Mask ROM (Non-Writable)**: Fixed-function UAC2 audio chips (e.g. Conexant CX31993, Apple A2049) with One-Time Programmable (OTP) registers. Hardware writes are strictly safety-locked to prevent bricking, routing profiles to host-side DSP engines instead.

## Host DSP Ecosystem

- **PipeWire**: Modern Linux audio server supporting low-latency biquad filter-chain configuration files (`pipewire.conf`).
- **EqualizerAPO**: Parametric EQ processing engine for Windows audio endpoints.
- **Wavelet / GraphicEQ**: System-wide graphic equalizer application for Android utilizing 127-point interpolated splines.
