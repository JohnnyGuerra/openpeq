# Hardware Chipset Datasheets & Architectural Specifications

This document catalogs technical specifications, architecture details, register/DSP capabilities, and hardware guardrails for all audio chipsets across the portable USB-C DAC, DSP cable, and IEM ecosystems supported by **OpenPEQ**.

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

---

## Overview of Silicon Categories

USB-C audio dongles and DSP cables generally divide into three functional topologies:
1. **Single-Chip DSP SoCs:** Combines USB transceiver, MCU, RAM/EEPROM, parametric hardware filter engine, stereo DAC, and headphone driver onto a single silicon die (e.g. KTMicro KT02H20, WalkPlay CB1300D). These chips allow **permanent hardware PEQ flashing**.
2. **Fixed-Function Codecs:** Fixed-mask ROM silicon with One-Time Programmable (OTP) calibration memory. While they possess superior standalone DAC/ADC specs, registers cannot store custom biquads; register writes risk permanently corrupting the factory descriptor (e.g. Conexant CX31993). Supported via **host DSP pipelines** (PipeWire, Equalizer APO, Wavelet).
3. **Multi-Stage Audiophile Dongles:** Pairs a USB bridge or DSP processor (XMOS XU316, Qualcomm QCC, or WalkPlay MCU) with dedicated flagship DAC ICs (Cirrus CS43131, ESS ES9069Q) and high-current analog buffer op-amps (SGM8262, MAX97220).

---

## Category 1: Integrated USB Audio SoCs with Hardware DSP (Flashable)

### KTMicro KT02H20 / CB1200AU
* **Manufacturer:** Beijing Kunteng Microelectronics (昆腾微电子)
* **Silicon Architecture:** Single-chip USB 2.0 High-Speed/Full-Speed Audio Codec with 32-bit DSP engine and integrated Class-G headphone amplifier.
* **Package:** 36-pin QFN (4 mm × 4 mm)
* **USB Interface:** UAC 1.0 / UAC 2.0, USB HID 1.11 Vendor-defined control endpoint (`Report ID 0x01` / `0x02`).
* **DAC Specs:**
  * Resolution & Rate: Up to 32-bit / 384 kHz PCM, native DSD64 / DSD128.
  * Dynamic Range / SNR: 115 dB (A-weighted).
  * THD+N: -85 dB (0.005%).
  * Power Output: ~30 mW @ 32 Ω (single-ended 3.5mm) / ~60 mW @ 32 Ω (balanced 4.4mm with differential bridge).
* **ADC Specs:** 32-bit / 384 kHz mono capture, 98 dB DNR, integrated low-noise microphone bias and preamplifier with CTIA/OMTP auto-detection.
* **DSP Capabilities:**
  * Hardware Biquads: 5 cascaded Direct Form I/II second-order IIR biquad filters per stereo channel.
  * Filter Registers: Registers `0x26` through `0x2F` (16-bit coefficient word pairs).
  * Clock Base: Fixed internal 48 kHz / 96 kHz filter calculation base.
* **Known Firmware Quirks & Guardrails:**
  * **2X Frequency Divisor Bug:** Early revisions (`bcdDevice <= 0x0100`, Kiwi Ears Allegro Mini FW v1.0.1) calculate biquad center frequencies at half-rate at 48 kHz. Center frequency must be multiplied or halved accordingly unless firmware is v1.8+ (e.g. FiiO JA11 `0x0180` fixes this natively).
  * **Register 0x11 Volume Lockout:** Register `0x11` configures DAC reconstruction filter response on FiiO JA11. On Kiwi Ears Allegro Mini, writing to `0x11` directly overwrites the MCU internal volume attenuation register, permanently muting or locking physical phone volume keys.
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
  * Protocol Framing: Standard KTMicro 8-byte framed packets (`CMD_WRITE 0x4B`, `CMD_COMMIT 0x53`).

---

### WalkPlay CB1300D / Scheme 11, 15, 16
* **Manufacturer:** WalkPlay Semiconductor / TTGK OEM (深圳沃普微电子)
* **Found In:** CrinEar Protocol Micro (Scheme 11), CrinEar Protocol Max (Scheme 16), Tanchjim STARGATE II & SPACE Pro (Scheme 15), TRUTHEAR KEYX.
* **Silicon Architecture:** Custom 32-bit DSP audio microcontroller paired with high-resolution Sigma-Delta DAC core or external Cirrus CS43131 converters.
* **USB Interface:** UAC 2.0 High-Speed, Custom Vendor HID (`Report ID 0x01` / `0x02`, 64-byte payload frames).
* **DSP Capabilities & Schemes:**
  * **Scheme 11 (CrinEar Protocol Micro):** 8-band hardware PEQ running in Q2.30 fixed-point arithmetic at 96 kHz base rate. Writes payload frame via memory Slot `101`.
  * **Scheme 15 (Tanchjim SPACE Pro / STARGATE II):** 8 to 10-band hardware PEQ with dual Cirrus Logic CS43131 DACs. Supports independent L/R channel calibration and digital volume ramps.
  * **Scheme 16 (CrinEar Protocol Max):** 10-band hardware PEQ with 3.5mm SE + 4.4mm balanced dual architecture.
* **Biquad Coefficient Format:** 5 coefficients ($b_0, b_1, b_2, a_1, a_2$) formatted as 32-bit two's complement integers ($Q2.30$ where $1.0 = 0x40000000$).

---

### Moondrop Custom 9-Band DSP
* **Manufacturer:** Moondrop / Custom Assembled MCU
* **Found In:** Moondrop FreeDSP Cable, Moondrop May 2-pin DSP Cable, Moondrop Chu II DSP, Moondrop Click.
* **Silicon Architecture:** 32-bit RISC core with 9-band hardware biquad filter chain and on-chip flash memory.
* **USB Interface:** VID `0x31B2` / PID `0x0112`.
* **DSP Capabilities:**
  * 9 Parametric EQ bands with dedicated readback verification.
  * Preamp gain offset support (`-12.0 dB` to `+12.0 dB`).
  * Filter types: Low Shelf, Peaking, High Shelf.

---

## Category 2: Fixed-Mask ROM & OTP Audio Codecs (Host DSP Only)

> [!WARNING]
> Chips in this category use **fixed mask ROM** with One-Time Programmable (OTP) calibration registers. Attempting to write KTMicro or WalkPlay HID register commands will permanently corrupt OTP descriptors or brick USB enumeration. OpenPEQ automatically shields these devices from register writes.

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
* **Software DSP Integration:** Routed via host PipeWire filter-chain, Equalizer APO, or Wavelet 10-band graphic curves.

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
    * **A2155 (European Union):** 0.5 Vrms (8 mW @ 32 Ω, hard-limited by EU directive).
  * THD+N: -99 dB (0.0011%).
  * Dynamic Range: 113 dBA.

---

## Category 3: Premium Dedicated DAC Converters

### Cirrus Logic CS43131 (MasterHIFI)
* **Manufacturer:** Cirrus Logic
* **Architecture:** Flagship ultra-low-power 32-bit stereo audio DAC with integrated high-impedance Class-H headphone amplifier.
* **Found In:** Tanchjim SPACE, Tanchjim SPACE Pro (Dual), Moondrop Dawn Pro (Dual), FiiO KA11, FiiO BTR13 (Dual).
* **Package:** 42-ball WLCSP
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
