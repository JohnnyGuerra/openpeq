# My IEM & DAC Collection

A curated inventory of In-Ear Monitors (IEMs), DAC dongles, cable configurations, and their corresponding hardware PEQ profiles in [OpenPEQ](file:///home/ubuntu/iem/README.md).

---

## 🎧 In-Ear Monitors (IEMs)

| IEM | Driver Configuration | Connection Type | Acoustic Signature & Tuning | OpenPEQ Preset |
| :--- | :--- | :---: | :--- | :--- |
| **TANGZU Wan'er S.G II** | 10mm PET Dual-Cavity Dynamic Driver (1DD) | **0.78mm 2-Pin** | **Vocal-Forward & Transparent**: Refined acoustic dampening, intimate midrange, clean pinna gain, airy highs. Ideal for acoustic, jazz, live recordings, and vocal tracks. | [`tangzu-waner.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/tangzu-waner.json) (`waner`) |
| **Linsoul 7Hz x Crinacle Zero:2** | 10mm PU + Metal Composite Diaphragm (1DD) | **0.78mm 2-Pin** | **Warm & Punchy**: Generous sub-bass shelf (+3 dB boost over original Zero), relaxed treble, fatigue-free pinna gain. Built for EDM, hip-hop, gaming, and long listening sessions. | [`7hz-zero2.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/7hz-zero2.json) (`zero2`) |
| **7Hz Salnotes Zero (Mecha Edition)** | 10mm Metal Composite Diaphragm (1DD) | **0.78mm 2-Pin** | **IEF Neutral & Analytical**: Mecha-styled angular shells with lean, controlled sub-bass, transparent mids, and sparkling treble. Highly revealing with pinpoint imaging for competitive gaming and vocal accuracy. | [`targets/ief_neutral.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/targets/ief_neutral.json) (`ief_neutral`) |
| **Kiwi Ears Cadenza** | 10mm Beryllium-Coated Diaphragm (1DD) | **0.78mm 2-Pin** | **Warm Harman & Lush**: Smooth beryllium transients, punchy mid-bass warmth, natural vocal timbre, and non-fatiguing treble roll-off. An everyday musical all-rounder. | [`kiwi-ears-cadenza.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/kiwi-ears-cadenza.json) (`cadenza`) |
| **Simgot EW300** | Tribrid: 1DD (Ceramic-PZT) + 1 Planar + 1 PZT | **0.78mm 2-Pin** | **Technical & Dynamic**: Rapid planar speed with dynamic slam. Swappable tuning nozzles: Silver (Harman target clarity) vs Gold (balanced warm-neutral). | [`ew300_silver.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/ew300_silver.json) & [`ew300_gold.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/ew300_gold.json) |
| **BASN BmasterX 6** | 6-Driver Tribrid: 1DD + 3BA + 2PZT | **MMCX** | **High-Energy Basshead & Stage Monitor**: Monstrous sub-bass impact from dedicated DD, combined with micro-detail from triple balanced armatures and dual piezoelectric super-tweeters. | [`bmasterx6.json`](file:///home/ubuntu/iem/dac-peq-manager/presets/bmasterx6.json) (`bmasterx6`) |

---

## ⚡ Portable DAC / Amp

### **Kiwi Ears Allegro Mini**
- **Chipset**: KTMicro KT02H20 / CB1200AU
- **DSP Architecture**: Hardware 5-Band Biquad PEQ (Slot 3 NVRAM)
- **Resolution**: Up to 32-bit / 384 kHz PCM, DSD128
- **Outputs**:
  - **3.5mm Single-Ended (SE)**: 30mW @ 32Ω
  - **4.4mm Balanced (BAL)**: 60mW @ 32Ω
- **Hardware Flashing**: Fully verified with OpenPEQ CLI (`dac-peq`) and Web Flasher.
- **Guardrails**: No register `0x11` filter overwrites (preserves physical volume attenuation) and strict preamp clamping.

---

## 🔌 Allegro Mini Output Pairing

Since cables are interchangeable, you can run any of your 0.78mm 2-Pin IEMs on either port by swapping cables:

| Allegro Mini Port | Output Specs | Ideal Usage |
| :--- | :--- | :--- |
| **4.4mm Balanced** | 60mW @ 32Ω | **High Dynamic Swing & Headroom**: Uses a 4.4mm Pentaconn cable. Delivers double the output power, +6 dB voltage headroom, and zero common-ground crosstalk. Excellent for driving multi-driver or planar hybrids (EW300) or elevating vocal intimacy (Wan'er S.G II). |
| **3.5mm Single-Ended** | 30mW @ 32Ω | **Universal Standard**: Uses any standard 3.5mm TRS cable. Plenty of power for high-sensitivity single dynamic drivers (Zero:2, Cadenza) with an ultra-quiet noise floor. |

---

## 🎛️ OpenPEQ Quick Commands

Flash acoustic profiles directly into the Allegro Mini's hardware NVRAM or export them for host-side DSP:

```bash
# 1. 7Hz x Crinacle Zero:2
dac-peq flash zero2

# 2. 7Hz Salnotes Zero (Mecha Edition - IEF Neutral)
dac-peq flash ief_neutral

# 3. Tangzu Wan'er S.G II
dac-peq flash tangzu-waner

# 3. Kiwi Ears Cadenza
dac-peq flash cadenza

# 4. Simgot EW300 (Silver Nozzle)
dac-peq flash ew300_silver

# 5. Simgot EW300 (Gold Nozzle)
dac-peq flash ew300_gold

# 6. BASN BmasterX 6
dac-peq flash bmasterx6

# Export any profile for PipeWire / Wavelet / EqualizerAPO
dac-peq export-pipewire zero2 -o zero2_sink.conf
dac-peq export-wavelet ew300_silver -o ew300_wavelet.txt
```
