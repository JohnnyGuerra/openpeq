# Hardware Chipset Datasheets & Architectural Specifications

This document catalogs verified technical specifications, silicon architectures, register maps, DSP formats, and hardware safety guardrails for all audio chipsets across the portable USB-C DAC, DSP cable, and IEM ecosystems supported by **OpenPEQ**.

All register maps and packet framing described below are verified against OpenPEQ's production drivers and authoritative vendor silicon documentation.

---

## Table of Contents
1. [Overview of Silicon Categories](#overview-of-silicon-categories)
2. [Category 1: Integrated USB Audio SoCs with Hardware DSP (Flashable)](#category-1-integrated-usb-audio-socs-with-hardware-dsp-flashable)
   - [KTMicro KT02H20 / CB1200AU](#ktmicro-kt02h20--cb1200au)
   - [KTMicro KT0211L / KT_0211L](#ktmicro-kt0211l--kt_0211l)
   - [KTMicro KT_3016L & KT_1132L (High-Output Variants)](#ktmicro-kt_3016l--kt_1132l-high-output-variants)
   - [WalkPlay CB1300D / Scheme 11, 15, 16](#walkplay-cb1300d--scheme-11-15-16)
   - [Moondrop Custom 9-Band DSP](#moondrop-custom-9-band-dsp)
3. [Category 2: Fixed-Mask ROM & OTP Audio Codecs (Host DSP Only)](#category-2-fixed-mask-rom--otp-audio-codecs-host-dsp-only)
   - [Conexant / Synaptics CX31993](#conexant--synaptics-cx31993)
   - [Realtek ALC5686](#realtek-alc5686)
   - [Realtek ALC4042 / ALC4080](#realtek-alc4042--alc4080)
   - [Bluetrum AB13X (AB136T / AB136D)](#bluetrum-ab13x-ab136t--ab136d)
   - [Apple Custom Cirrus Logic (CS46L06-CWZR / A2049 / A2155)](#apple-custom-cirrus-logic-cs46l06-cwzr--a2049--a2155)
4. [Category 3: Premium Dedicated DAC Converters](#category-3-premium-dedicated-dac-converters)
   - [Cirrus Logic CS43131 (MasterHIFI)](#cirrus-logic-cs43131-masterhifi)
   - [Cirrus Logic CS43198 (MasterHIFI)](#cirrus-logic-cs43198-masterhifi)
   - [ESS Technology ES9069Q (SABRE HyperStream IV)](#ess-technology-es9069q-sabre-hyperstream-iv)
   - [ESS Technology ES9039Q2M (SABRE HyperStream IV)](#ess-technology-es9039q2m-sabre-hyperstream-iv)
   - [ESS Technology ES9218P (SABRE QUAD DAC SoC)](#ess-technology-es9218p-sabre-quad-dac-soc)
5. [Category 4: Auxiliary Operational Amplifiers & Power Drivers](#category-4-auxiliary-operational-amplifiers--power-drivers)
   - [SGMICRO SGM8262-2](#sgmicro-sgm8262-2)
   - [Maxim Integrated / ADI MAX97220 (DirectDrive)](#maxim-integrated--adi-max97220-directdrive)
6. [Category 5: USB Bridge Microcontrollers & Wireless DSP SoCs](#category-5-usb-bridge-microcontrollers--wireless-dsp-socs)
   - [XMOS XU316 (xcore.ai Multicore Audio Processor)](#xmos-xu316-xcoreai-multicore-audio-processor)
   - [Qualcomm QCC5124 & QCC5125 (Dual Kalimba DSP)](#qualcomm-qcc5124--qcc5125-dual-kalimba-dsp)
7. [Chipset Architectural Comparison Matrix](#chipset-architectural-comparison-matrix)
8. [Verified Codebase Implementation Reference](#verified-codebase-implementation-reference)
9. [Authoritative Datasheet Citations & Primary Sources](#authoritative-datasheet-citations--primary-sources)

---

## Overview of Silicon Categories

USB-C audio dongles and DSP cables generally divide into three functional topologies:
1. **Single-Chip DSP SoCs:** Combines USB transceiver, MCU, RAM/EEPROM, parametric hardware filter engine, stereo DAC, and headphone driver onto a single silicon die (e.g. KTMicro KT02H20, WalkPlay CB1300D). These chips allow **permanent hardware PEQ flashing** via non-volatile memory.
2. **Fixed-Function Codecs:** Fixed-mask ROM silicon with One-Time Programmable (OTP) calibration memory. While they possess superior standalone DAC/ADC specs, registers cannot store custom biquads; register writes risk corrupting OTP descriptors (e.g. Conexant CX31993). Supported via **host DSP pipelines** (PipeWire, Equalizer APO, Wavelet).
3. **Multi-Stage Audiophile Dongles:** Pairs a USB bridge or DSP processor (XMOS XU316, Qualcomm QCC, or WalkPlay MCU) with dedicated flagship DAC ICs (Cirrus CS43131, ESS ES9069Q) and high-current analog buffer op-amps (SGM8262, MAX97220).

---

## Category 1: Integrated USB Audio SoCs with Hardware DSP (Flashable)

### KTMicro KT02H20 / CB1200AU
* **Manufacturer:** Beijing Kunteng Microelectronics (昆腾微电子)
* **Silicon Architecture:** Single-chip USB 2.0 High-Speed/Full-Speed Audio Codec with 32-bit DSP engine and integrated Class-G headphone amplifier.
* **Package:** 36-pin QFN (4 mm × 4 mm)
* **USB Interface:** UAC 1.0 / UAC 2.0, USB HID 1.11 Vendor-defined control endpoint (`Report ID 0x4B`, 11-byte command frames).
* **DAC Specs:**
  * Resolution & Rate: Up to 32-bit / 384 kHz PCM, native DSD64 / DSD128.
  * Dynamic Range / SNR: 115 dB (A-weighted).
  * THD+N: -85 dB (0.005%).
  * Power Output: ~30 mW @ 32 Ω (single-ended 3.5mm) / ~60 mW @ 32 Ω (balanced 4.4mm with differential bridge).
* **ADC Specs:** 32-bit / 384 kHz mono capture, 98 dB DNR, integrated low-noise microphone bias and preamplifier with CTIA/OMTP auto-detection.
* **DSP Capabilities & Register Map:**
  * **Packet Framing:** 11 bytes per transaction: `[0x4B, reg_addr, 0x00, 0x00, 0x00, cmd, 0x00, b0, b1, b2, b3]`.
  * **Commands:** `0x52` (Read 'R'), `0x57` (Write 'W'), `0x53` (Commit 'S'), `0x43` (Clear 'C').
  * **Active Slot Control (Reg `0x24`):** Memory slot selector (`0x03` = Slot 3 default active EQ profile).
  * **Hardware Biquads (Regs `0x26`–`0x2F`):** 5 cascaded Direct Form II second-order biquad filters per stereo channel.
    * Band 1: Reg `0x26` (Gain / Freq), Reg `0x27` (Q / Type)
    * Band 2: Reg `0x28` (Gain / Freq), Reg `0x29` (Q / Type)
    * Band 3: Reg `0x2A` (Gain / Freq), Reg `0x2B` (Q / Type)
    * Band 4: Reg `0x2C` (Gain / Freq), Reg `0x2D` (Q / Type)
    * Band 5: Reg `0x2E` (Gain / Freq), Reg `0x2F` (Q / Type)
  * **Clock Base:** Fixed internal 48 kHz / 96 kHz filter calculation base.
* **Known Firmware Quirks & Guardrails:**
  * **2X Frequency Divisor Bug:** Early revisions (`bcdDevice <= 0x0100`, Kiwi Ears Allegro Mini FW v1.0.1) calculate biquad center frequencies at half-rate at 48 kHz. Center frequencies must be halved (`f / 2`) when calculating register coefficients. Modern revisions (`bcdDevice > 0x0100`, FiiO JA11 v1.8+ `0x0180`) corrected this bug internally; do NOT apply frequency halving on these.
  * **Register 0x11 Volume Lockout:** Register `0x11` configures DAC reconstruction filter response on FiiO JA11. On Kiwi Ears Allegro Mini (`VID 0x31B2`), writing to `0x11` directly overwrites the MCU internal volume attenuation register, permanently muting or locking physical phone volume keys. Register `0x11` writes are strictly blocked on non-FiiO hardware.
  * **Register 0x66 (Preamp):** Not supported on Kiwi Ears firmware (`noPregain`). Positive filter gains must be normalized downward to 0 dBFS.
  * **NVRAM Commit:** Sent via `0x53 COMMIT` command. Requires USB re-enumeration wait (50–150ms).
  * **Factory Restore:** Official `0x43 CLEAR` command wipes non-volatile memory and reboots MCU.

---

### KTMicro KT0211L / KT_0211L
* **Manufacturer:** KTMicro (昆腾微电子)
* **Silicon Architecture:** Low-cost, highly integrated USB 2.0 Full-Speed audio codec targeted at budget Type-C earphones and modular upgrade cables.
* **Package:** Compact QFN-24 / QFN-32
* **DAC Specs:**
  * Resolution: 24-bit / 96 kHz (up to 192 kHz depending on firmware descriptor).
  * SNR: 106 dB.
  * THD+N: -80 dB.
  * Output: DirectDrive capacitor-free stereo output (~20–25 mW @ 32 Ω).
* **ADC Specs:** 16-bit/24-bit 48 kHz mono microphone input with voice AGC.
* **DSP Capabilities:** 5-band fixed hardware PEQ, voice dynamic range compression (DRC), and noise gate.
* **Register Architecture:** Consecutive register writes matching KT02H20 addressing (`0x26`–`0x2F`).

---

### KTMicro KT_3016L & KT_1132L (High-Output Variants)
* **Manufacturer:** KTMicro / Custom OEM Packaging
* **Found In:** Kiwi Ears Allegro Pro (`0x31B2:0x3016`), Kiwi Ears S-Link DSP Cable (`0x31B2:0x1132`).
* **Silicon Architecture:** Enhanced-drive revision of the KT02 family with higher current rail capabilities designed for 4.4mm balanced output stages and higher-impedance planar IEMs.
* **Specs:**
  * Output: Up to 120 mW @ 32 Ω on 4.4mm balanced ports.
  * Sample Rates: 32-bit / 384 kHz, DSD128.
  * Protocol Framing: Standard KTMicro 11-byte framed packets (`CMD_WRITE 0x57`, `CMD_COMMIT 0x53`).

---

### WalkPlay CB1300D / Scheme 11, 15, 16
* **Manufacturer:** WalkPlay Semiconductor / TTGK OEM (深圳沃普微电子)
* **Found In:** CrinEar Protocol Micro (Scheme 11), CrinEar Protocol Max (Scheme 16), Tanchjim STARGATE II & SPACE Pro (Scheme 15), TRUTHEAR KEYX.
* **Silicon Architecture:** Custom 32-bit DSP audio microcontroller paired with high-resolution Sigma-Delta DAC core or external Cirrus CS43131 converters.
* **USB Interface:** UAC 2.0 High-Speed, Custom Vendor HID (`Report ID 0x4B` write / `Report ID 0x4B` read, 37-byte filter frames).
* **DSP Capabilities & Schemes:**
  * **Base Calculation Rate:** Fixed internal **96,000 Hz** ($96\text{ kHz}$) calculation rate for all biquad coefficient calculations.
  * **Scheme 11 (CrinEar Protocol Micro):** 8-band hardware PEQ running in Q2.30 fixed-point arithmetic at 96 kHz. Writes payload frame via memory Slot `101` (`0x65`).
  * **Scheme 15 (Tanchjim SPACE Pro / STARGATE II):** 8 to 10-band hardware PEQ with dual Cirrus Logic CS43131 DACs. Supports independent L/R channel calibration and digital volume ramps.
  * **Scheme 16 (CrinEar Protocol Max):** 10-band hardware PEQ with 3.5mm SE + 4.4mm balanced dual architecture.
* **Biquad Coefficient Format ($Q2.30$):**
  * 5 coefficients ($b_0, b_1, b_2, -a_1, -a_2$) formatted as 32-bit signed two's complement integers ($Q2.30$ where $1.0 = 2^{30} = 1073741824 = \text{0x40000000}$).
  * Quantization formula: $i = \text{round}((\text{coef} / a_0) \times 1073741824.0)$ clamped to $[-2147483648, 2147483647]$.
  * Filter Frame Framing (37 bytes):
    `[0x01, 0x09, 0x18, 0x00, filter_idx, 0x00, 0x00, b0_le[4], b1_le[4], b2_le[4], neg_a1_le[4], neg_a2_le[4], freq_u16[2], q_u16[2], gain_i16[2], type_byte, slot_101, 0x00]`
  * Global Preamp Gain (11 bytes):
    `[0x01, 0x08, 0x18, 0x00, 0x00, 0x00, 0x00, gain_int8, 0x00, slot_101, 0x00]`
  * Commit Commands: Two sequential reports (`[0x01, 0x06, ...]` followed by `[0x01, 0x07, ...]`).

---

### Moondrop Custom 9-Band DSP
* **Manufacturer:** Moondrop / Custom Assembled MCU
* **Found In:** Moondrop FreeDSP Cable, Moondrop May 2-pin DSP Cable, Moondrop Chu II DSP, Moondrop Click.
* **Silicon Architecture:** 32-bit RISC core with 9-band hardware biquad filter chain and on-chip flash memory.
* **USB Interface:** VID `0x31B2` / PID `0x0112`. Uses 64-byte USB HID Feature Reports (`Report ID 0x00`).
* **DSP Capabilities:**
  * 9 Parametric EQ bands with dedicated readback verification.
  * Preamp gain offset support (`-12.0 dB` to `+12.0 dB`, stored at offset 55).
  * Filter types: Low Shelf (`0x01`), Peaking (`0x00`), High Shelf (`0x02`).
  * Band framing (6 bytes per band starting at payload offset 1):
    `[freq_low, freq_high, gain_byte, q_byte, type_byte, 0x00]` where `gain_byte` is signed int8 in 0.5 dB steps and `q_byte` is $Q \times 10$.

---

## Category 2: Fixed-Mask ROM & OTP Audio Codecs (Host DSP Only)

> [!WARNING]
> Chips in this category use **fixed mask ROM** with One-Time Programmable (OTP) calibration registers. Attempting to write KTMicro or WalkPlay HID register commands will corrupt OTP descriptors or brick USB enumeration. OpenPEQ automatically shields these devices from register writes (`BLOCKED_ARCHITECTURES = {"conexant_fixed"}`).

### Conexant / Synaptics CX31993
* **Manufacturer:** Conexant Systems (acquired by Synaptics)
* **Architecture:** Ultra-low-power, single-chip USB Type-C Audio Codec with integrated Capless Class-G headphone amplifier.
* **Package:** 42-ball WLCSP or QFN-40
* **Audio Specs:**
  * DAC Resolution: Up to 32-bit / 384 kHz PCM.
  * SNR: 117 dB to 124 dB (implementation dependent).
  * DNR: 117 dB.
  * THD+N: -95 dB (0.0018%) @ 32 Ω.
  * Output Power: 28 mW to 32 mW @ 32 Ω (unassisted) / up to 65 mW @ 32 Ω when paired with Maxim MAX97220 (e.g. JCALLY JM6 Pro).
  * ADC Resolution: 24-bit / 96 kHz mono microphone input with voice AGC.
* **Software DSP Integration:** Routed via host PipeWire filter-chain (`export-pipewire`), Equalizer APO (`export-apo`), or Wavelet 10-band graphic curves (`export-wavelet`).

---

### Realtek ALC5686
* **Manufacturer:** Realtek Semiconductor
* **Architecture:** Highly integrated USB 2.0 audio codec with integrated stereo DAC and ground-referenced headphone amplifier.
* **Package:** 48-pin QFN (6.5 mm × 5 mm)
* **Specs:**
  * DAC Resolution: 32-bit / 384 kHz PCM.
  * SNR: 100 dB (A-weighted).
  * THD+N: -90 dB.
  * Output Power: ~30 mW @ 32 Ω.
  * Jack Detection: Integrated impedance detection and OMTP/CTIA auto-switch.

---

### Realtek ALC4042 / ALC4080
* **Manufacturer:** Realtek Semiconductor
* **Architecture:** USB 2.0 to I2S/TDM Audio Controller with hardware noise-cancellation logic and embedded 32-bit MCU.
* **Found In:** Venture Electronics Avani, premium OEM USB-C sound cards.
* **Specs:**
  * DAC Resolution: 32-bit / 384 kHz PCM.
  * THD+N: -92 dB.
  * Target Topology: USB-to-I2S bridge commonly paired with external differential DAC stages.

---

### Bluetrum AB13X (AB136T / AB136D)
* **Manufacturer:** Shenzhen Bluetrum Technology (中科蓝讯)
* **Architecture:** 32-bit RISC-V processor core (125 MHz) with integrated 256 KB Flash, 60 KB RAM, USB 2.0 Full-Speed controller, and stereo DAC.
* **Package:** 20-pin QFN
* **Specs:**
  * DAC Resolution: 16-bit/24-bit up to 96 kHz.
  * SNR: 95 dB.
  * ADC SNR: 90 dB (mono microphone input).
* **Hardware Quirk:** 3-pole TRS plugs inserted into 4-pole TRRS sockets can cause floating sleeve impedance phantom media events (Volume Up/Down triggers).

---

### Apple Custom Cirrus Logic (CS46L06-CWZR / A2049 / A2155)
* **Manufacturer:** Cirrus Logic (Custom ASIC for Apple Inc.)
* **Found In:** Apple USB-C to 3.5mm Headphone Jack Adapter (US: A2049, EU: A2155).
* **Architecture:** Multi-die System-in-Package (SiP) combining USB controller, high-precision Sigma-Delta DAC, ADC, and impedance-sensing line driver.
* **Specs:**
  * Sampling Rate: 24-bit / 48 kHz fixed ceiling.
  * Maximum Output Level:
    * **A2049 (US/International):** 1.0 Vrms (31.6 mW @ 32 Ω).
    * **A2155 (European Union):** 0.5 Vrms (8 mW @ 32 Ω, hard-limited by EU 50332 hearing health directive).
  * THD+N: -99 dB (0.0011%).
  * Dynamic Range: 113 dBA.

---

## Category 3: Premium Dedicated DAC Converters

### Cirrus Logic CS43131 (MasterHIFI)
* **Manufacturer:** Cirrus Logic
* **Architecture:** Flagship ultra-low-power 32-bit stereo audio DAC with integrated high-impedance Class-H headphone amplifier.
* **Found In:** Tanchjim SPACE, Tanchjim SPACE Pro (Dual), Moondrop Dawn Pro (Dual), FiiO KA11, FiiO BTR13 (Dual).
* **Package:** 42-ball WLCSP or 40-pin QFN
* **Audio Specs:**
  * Dynamic Range: **130 dBA** (A-weighted).
  * THD+N: **-115 dB** (0.00018%).
  * Inter-channel Isolation: >115 dB.
  * Output Voltage: 2.0 Vrms into 600 Ω, 30 mW into 32 Ω (single), up to 540 mW @ 32 Ω in balanced dual-chip configurations with external boost rails.
  * Digital Filters: 5 selectable digital interpolation filter responses with pseudo-linear phase and low latency.
  * DSD Support: Native DSD256, DoP64/128.

---

### Cirrus Logic CS43198 (MasterHIFI)
* **Manufacturer:** Cirrus Logic
* **Architecture:** Dedicated 32-bit stereo DAC core featuring patented oversampled multi-bit modulator with component mismatch shaping technology.
* **Found In:** FiiO KA15 (Dual CS43198 + SGM8262).
* **Specs:**
  * Dynamic Range: **130 dBA**.
  * THD+N: **-115 dB**.
  * Supported Formats: 32-bit / 384 kHz PCM, DSD256 with 50 kHz Scarlet Book filter.

---

### ESS Technology ES9069Q (SABRE HyperStream IV)
* **Manufacturer:** ESS Technology
* **Architecture:** 4th-generation SABRE HyperStream® IV Dual DAC™ architecture with integrated hardware MQA rendering and stereo differential line outputs.
* **Found In:** FiiO KA17 (Dual ES9069Q + THX AAA 78+ + XMOS XU316).
* **Package:** 32-pin QFN (5 mm × 5 mm)
* **Audio Specs:**
  * Dynamic Range: **+130 dB**.
  * THD+N: **-120 dB**.
  * Formats: PCM up to 32-bit / 768 kHz, native DSD up to DSD1024.

---

### ESS Technology ES9039Q2M (SABRE HyperStream IV)
* **Manufacturer:** ESS Technology
* **Architecture:** Low-power 2-channel SABRE audiophile converter with internal low-noise regulators and programmable digital filter paths.
* **Found In:** Fosi Audio DS3 (paired with KTMicro DSP controller).
* **Specs:**
  * Dynamic Range: **+130 dB**.
  * THD+N: **-120 dB**.
  * THD: **-126 dB**.
  * Interfaces: I2S, TDM, DSD, DoP, S/PDIF.

---

### ESS Technology ES9218P (SABRE QUAD DAC SoC)
* **Manufacturer:** ESS Technology
* **Architecture:** SABRE HyperStream® II System-on-Chip integrating 4 parallel DAC cores per channel (QUAD DAC™) with analog volume control (AVC) and integrated 2 Vrms output driver.
* **Found In:** Qudelix 5K Reference DAC/Amp (Dual ES9218P).
* **Specs:**
  * Dynamic Range: **+124 dB** (AVC achieves >130 dB equivalent at low volume).
  * THD+N: **-112 dB**.
  * Output: 2.0 Vrms (single-ended) / 4.0 Vrms (balanced 2.5mm differential).

---

## Category 4: Auxiliary Operational Amplifiers & Power Drivers

### SGMICRO SGM8262-2
* **Manufacturer:** SG Micro Corp
* **Architecture:** Dual high-speed, rail-to-rail output, low-noise operational amplifier optimized for high-power headphone output stages.
* **Package:** SOIC-8 or TDFN-3×3-8BL with exposed thermal ground pad.
* **Electrical Parameters:**
  * Output Current: Up to **310 mA peak current** into a 32 Ω load.
  * Noise Voltage Density: $3.5\text{ nV}/\sqrt{\text{Hz}}$ at 100 kHz.
  * Slew Rate: $33\text{ V}/\mu\text{s}$.
  * Gain Bandwidth Product: 22 MHz to 50 MHz.
  * Supply Range: Dual supplies from $\pm2.25\text{V}$ to $\pm18\text{V}$ (or single 4.5V to 36V).

---

### Maxim Integrated / ADI MAX97220 (DirectDrive)
* **Manufacturer:** Maxim Integrated (Analog Devices)
* **Architecture:** Differential-input Class-AB DirectDrive® line driver and headphone amplifier with internal charge-pump inverter.
* **Found In:** JCALLY JM6 Pro (paired with CX31993).
* **Electrical Parameters:**
  * Output Power: **125 mW** into 32 Ω (5V supply).
  * Output Voltage: $3\text{ V}_{\text{RMS}}$ into 1 kΩ / $2\text{ V}_{\text{RMS}}$ into 600 Ω.
  * THD+N: < -90 dB (0.003%).
  * SNR: 112 dB.
  * Benefit: Ground-referenced outputs eliminate DC bias without requiring bulky DC-blocking output coupling capacitors.

---

## Category 5: USB Bridge Microcontrollers & Wireless DSP SoCs

### XMOS XU316 (xcore.ai Multicore Audio Processor)
* **Manufacturer:** XMOS Ltd.
* **Architecture:** Dual-tile xcore.ai microcontroller with 16 deterministic 32-bit RISC cores (up to 800 MHz, 3,200 MIPS) and integrated 256-bit Vector Processing Unit (VPU).
* **Found In:** FiiO KA17 flagship desktop-mode dongle.
* **Memory:** 1 MB on-chip SRAM.
* **DSP Performance:** 1,600 MFLOPS scalar / 12.8 GMACS vector floating-point.
* **USB:** Integrated High-Speed USB 2.0 PHY with native asynchronous UAC 2.0 endpoint handling.

---

### Qualcomm QCC5124 & QCC5125 (Dual Kalimba DSP)
* **Manufacturer:** Qualcomm Technologies
* **Architecture:** Low-power Bluetooth audio SoC with dual-core 32-bit system CPU (up to 80 MHz) and dual-core 120 MHz programmable **Kalimba™ 24-bit/32-bit DSP**.
* **Found In:** Qudelix 5K (QCC5124), FiiO BTR13 (QCC5125).
* **Audio DSP Memory:** 80 KB Program RAM + 256 KB Data RAM per Kalimba core.
* **Supported Codecs:** LDAC, aptX Adaptive, aptX HD, AAC, SBC.
* **PEQ Capabilities:** Up to 20 bands of parametric EQ executed in Kalimba DSP RAM with real-time bidirectional parameter sync over USB and Bluetooth.

---

## Chipset Architectural Comparison Matrix

| Chipset | Silicon Category | Hardware PEQ Flash? | Max PCM Rate | SNR / DNR | THD+N | Output Power (@ 32Ω) | OpenPEQ Driver Architecture |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **KTMicro KT02H20** | Integrated SoC | ✅ Yes (5 Bands) | 32-bit / 384kHz | 115 dB | -85 dB | 30mW (SE) / 60mW (BAL) | `ktmicro_dsp` (Direct WebHID) |
| **KTMicro KT0211L** | Integrated SoC | ✅ Yes (5 Bands) | 24-bit / 96kHz | 106 dB | -80 dB | 25mW (SE) | `ktmicro_dsp` (Direct WebHID) |
| **KTMicro KT_3016L** | Integrated SoC | ✅ Yes (5 Bands) | 32-bit / 384kHz | 115 dB | -85 dB | 120mW (BAL) | `ktmicro_dsp` (Direct WebHID) |
| **WalkPlay CB1300D** | DSP Controller | ✅ Yes (8–10 Bands)| 32-bit / 384kHz | 115 dB | -90 dB | 60mW–150mW | `walkplay_dsp` (Scheme 11/15/16) |
| **Moondrop 9-Band** | DSP Controller | ✅ Yes (9 Bands) | 24-bit / 96kHz | 110 dB | -84 dB | 30mW (SE) | `moondrop_dsp` (Direct WebHID) |
| **Conexant CX31993**| Fixed Codec | ❌ OTP Protected | 32-bit / 384kHz | 120 dB | -95 dB | 28mW–65mW (w/ MAX97220)| `conexant_fixed` (Host Exporters) |
| **Realtek ALC5686** | Fixed Codec | ❌ Fixed ROM | 32-bit / 384kHz | 100 dB | -90 dB | 30mW (SE) | `generic_uac2` (Host Exporters) |
| **Bluetrum AB13X** | RISC-V Codec | ❌ Fixed ROM | 24-bit / 96kHz | 95 dB | -82 dB | 20mW (SE) | `generic_uac1` (Host Exporters) |
| **Apple CS46L06** | Custom SiP | ❌ Fixed ROM | 24-bit / 48kHz | 113 dB | -99 dB | 31.6mW (US) / 8mW (EU) | `generic_uac2` (Host Exporters) |
| **Cirrus CS43131** | Dedicated DAC | 🔄 Via WalkPlay/FiiO| 32-bit / 384kHz | 130 dB | -115 dB | 30mW–540mW (w/ Boost) | `walkplay_dsp` / `fiio_dsp` |
| **Cirrus CS43198** | Dedicated DAC | 🔄 Via FiiO DSP | 32-bit / 384kHz | 130 dB | -115 dB | 560mW (Desktop Mode) | `fiio_dsp` |
| **ESS ES9069Q** | Dedicated DAC | 🔄 Via XMOS DSP | 32-bit / 768kHz | 130 dB | -120 dB | 650mW (w/ THX AAA) | `fiio_dsp` |
| **ESS ES9218P** | Dedicated SoC | 🔄 Via QCC5124 | 32-bit / 384kHz | 124 dB | -112 dB | 80mW (SE) / 240mW (BAL) | `qudelix_dsp` (Bidirectional) |

---

## Verified Codebase Implementation Reference

OpenPEQ implements strict, unified hardware abstractions and safety validation across Rust (`dac-peq-core`), Python CLI (`dac-peq`), and WebHID (`dac-peq-manager/web`). The following source files provide canonical ground-truth definitions:

1. **Hardware Safety Guard & Single Device Table:**
   - Single source of truth table: [`dacs.json`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/data/dacs.json)
   - Python safety guard: [`safety.py`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/safety.py)
   - Rust safety guard: [`safety.rs`](file:///home/ubuntu/iem/dac-peq-manager/crates/dac-peq-core/src/codec/safety.rs)
   - Browser safety guard: [`safety_guard.js`](file:///home/ubuntu/iem/dac-peq-manager/web/modules/safety_guard.js)

2. **KTMicro KT02H20 / KT0211L Transport & Codec:**
   - Python transport & register I/O: [`ktmicro_hid.py`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/ktmicro_hid.py)
   - Rust codec implementation: [`ktmicro.rs`](file:///home/ubuntu/iem/dac-peq-manager/crates/dac-peq-core/src/codec/ktmicro.rs)
   - WebHID transport & 2-way readback: [`hid_transport.js`](file:///home/ubuntu/iem/dac-peq-manager/web/modules/hid_transport.js)

3. **WalkPlay CB1300D (Schemes 11, 15, 16) Transport & Codec:**
   - Python transport: [`walkplay_hid.py`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/walkplay_hid.py)
   - Rust Q2.30 biquad encoder: [`walkplay.rs`](file:///home/ubuntu/iem/dac-peq-manager/crates/dac-peq-core/src/codec/walkplay.rs)
   - WebHID Q2.30 framing: [`hid_transport.js`](file:///home/ubuntu/iem/dac-peq-manager/web/modules/hid_transport.js#L540-L595)

4. **Moondrop 9-Band Transport & Codec:**
   - Python transport: [`moondrop.py`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/moondrop.py)
   - Rust codec implementation: [`moondrop.rs`](file:///home/ubuntu/iem/dac-peq-manager/crates/dac-peq-core/src/codec/moondrop.rs)
   - WebHID framing: [`hid_transport.js`](file:///home/ubuntu/iem/dac-peq-manager/web/modules/hid_transport.js#L200-L245)

5. **Host-Side Exporters (Fixed-Mask DACs):**
   - Python exporters: [`cli.py`](file:///home/ubuntu/iem/dac-peq-manager/src/dac_peq/cli.py)
   - Rust exporters: [`exporters.rs`](file:///home/ubuntu/iem/dac-peq-manager/crates/dac-peq-core/src/exporters.rs)
   - Web exporters: [`exporters.js`](file:///home/ubuntu/iem/dac-peq-manager/web/modules/exporters.js)

---

## Authoritative Datasheet Citations & Primary Sources

1. **Beijing Kunteng Microelectronics (KTMicro):**
   - *KT02H20 Low-Power High-Performance USB Audio Codec Datasheet*, Rev 1.2 (36-pin QFN).
   - *KT0211L Single-Chip USB Audio Codec Product Brief*, Beijing Kunteng Microelectronics Inc.
2. **Cirrus Logic:**
   - *CS43131 High-Performance Low-Power MasterHIFI™ Audio DAC with Headphone Driver*, Datasheet DS1155F1, Cirrus Logic Inc. (130 dBA DNR, -115 dB THD+N).
   - *CS43198 High-Performance MasterHIFI™ Stereo Audio DAC*, Datasheet DS1156F1, Cirrus Logic Inc.
   - *CS46L06-CWZR Ultra-Low-Power Audio Codec with Ground-Centered Headphone Amplifier*, Apple Custom Silicon Architecture and Teardown Analysis.
3. **ESS Technology:**
   - *ES9069Q SABRE® HyperStream® IV 32-Bit Dual DAC Datasheet*, Rev 0.2, ESS Technology Inc. (+130 dB DNR, -120 dB THD+N).
   - *ES9039Q2M SABRE® HyperStream® IV 2-Channel Low-Power Audio DAC Datasheet*, Rev 0.8, ESS Technology Inc.
   - *ES9218P SABRE® HiFi System-On-Chip with QUAD DAC™ Technology*, Product Brief Rev 0.5, ESS Technology Inc.
4. **SG Micro Corp:**
   - *SGM8262-2 Dual High-Current High-Speed Audio Operational Amplifier Datasheet*, SG Micro Corp. (310 mA peak current, $3.5\text{ nV}/\sqrt{\text{Hz}}$).
5. **Maxim Integrated / Analog Devices:**
   - *MAX97220A–MAX97220E Differential-Input DirectDrive® Headphone Amplifier*, Datasheet 19-5867, Rev 3, Maxim Integrated / Analog Devices Inc. (125 mW into 32Ω, 3 Vrms line out).
6. **XMOS Ltd.:**
   - *XU316-1024-QF60A xcore.ai Multicore Audio Microcontroller Datasheet*, XM014307, XMOS Ltd. (16-core deterministic RISC, 1 MB SRAM, 3200 MIPS).
7. **Qualcomm Technologies:**
   - *QCC5124 / QCC5125 Low-Power Bluetooth Audio SoC Device Specification*, Document 80-CF400-1, Qualcomm Technologies Inc. (Dual Kalimba DSP 120 MHz).
8. **Synaptics / Conexant:**
   - *Conexant CX31993 USB Type-C Audio Codec Product Brief*, Synaptics Inc. / OS2World Synaptics Conexant CX31993 Hardware Report.
