# `OpenPEQ` (Hardware DSP Flasher & Web Equalizer Suite)

[![CI](https://github.com/JohnnyGuerra/openpeq/actions/workflows/ci.yml/badge.svg)](https://github.com/JohnnyGuerra/openpeq/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/JohnnyGuerra/openpeq?color=10b981&label=Release&style=flat-square)](https://github.com/JohnnyGuerra/openpeq/releases)
[![Stars](https://img.shields.io/github/stars/JohnnyGuerra/openpeq?style=flat-square&color=38bdf8)](https://github.com/JohnnyGuerra/openpeq/stargazers)
[![Growth Dashboard](https://img.shields.io/badge/Analytics-Growth_Dashboard-10b981?style=flat-square&logo=github)](./metrics/GROWTH.md)
[![WebHID Flasher](https://img.shields.io/badge/Web_Flasher-Live_on_Pages-3b82f6?style=flat-square&logo=googlechrome&logoColor=white)](https://johnnyguerra.github.io/openpeq/)
[![Rust WASM](https://img.shields.io/badge/Engine-Rust_WASM-f97316?style=flat-square&logo=rust&logoColor=white)](https://github.com/JohnnyGuerra/openpeq)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Hardware Support Matrix](https://img.shields.io/badge/Hardware%20Matrix-35%20DACs-orange.svg?style=flat-square)](./COMPATIBILITY.md)

<p align="center">
  <a href="https://johnnyguerra.github.io/openpeq/">
    <img src="media/dac-peq-web-flasher-demo.gif" alt="OpenPEQ Web Flasher Demo" width="850">
  </a>
  <br>
  <em>⚡ Live Web Flasher in action: Drag real-time biquad curve handles, audition in volatile RAM, or save to persistent hardware NVRAM in &lt;50ms.</em>
</p>

An open-source hardware DSP flashing suite, WebHID browser flasher, and host equalizer bridge for portable USB-C DAC dongles, DSP upgrade cables, and In-Ear Monitors (IEMs).

Save custom Parametric EQ profiles (including **AutoEq** targets from squig.link) directly into onboard non-volatile hardware memory (NVRAM). Settings persist natively across **iPhones, Android, Macs, Windows, Linux PCs, iPads, and gaming consoles** without running any background apps.

---

## ⚡ Try the Web Flasher (Zero Install)

Run the full hardware flasher directly in your browser via WebHID (Chrome, Brave, Edge):

👉 **[Launch Web Flasher (GitHub Pages)](https://johnnyguerra.github.io/openpeq/)**

* 100% Client-Side & Private (no audio or device data leaves your browser).
* Real-time Interactive SVG Biquad Curve with draggable band handles.
* AutoEq Database Integration (search over 5,000+ headphone & IEM measurements).
* 2-Way Hardware Readback & Live Audition in RAM before saving to persistent NVRAM.
* Built-in Safety Guardrails: NVRAM Flash Wear-Out Tracker & Conexant fixed mask ROM protection.

> [!TIP]
> **Linux Users:** Linux restricts `/dev/hidraw*` devices to `root` by default. See [Linux WebHID & udev Setup](#-linux-webhid--udev-setup) below to enable browser access in 10 seconds.

---

## 📸 Architecture & Feature Slides

<details open>
<summary><b>Click to preview presentation & feature slides (5-Slide Infographic Deck)</b></summary>
<br>

| Slide 1: Overview & Value Proposition | Slide 2: The Status Quo vs Open Source |
| :---: | :---: |
| <a href="media/slides/slide_1.png"><img src="media/slides/slide_1.png" alt="Slide 1: Overview" width="440"></a> | <a href="media/slides/slide_2.png"><img src="media/slides/slide_2.png" alt="Slide 2: Comparison" width="440"></a> |

| Slide 3: Web Flasher UI & Biquad Curve | Slide 4: Multi-Tier Hardware Protections |
| :---: | :---: |
| <a href="media/slides/slide_3.png"><img src="media/slides/slide_3.png" alt="Slide 3: Web Flasher UI" width="440"></a> | <a href="media/slides/slide_4.png"><img src="media/slides/slide_4.png" alt="Slide 4: Hardware Safety" width="440"></a> |

<p align="center">
  <b>Slide 5: Hardware Compatibility & Universal Portability</b><br>
  <a href="media/slides/slide_5.png"><img src="media/slides/slide_5.png" alt="Slide 5: Compatibility" width="680"></a>
</p>
</details>

---

## 📋 Hardware Compatibility Matrix

See **[COMPATIBILITY.md](./COMPATIBILITY.md)** for our full breakdown of all **35+ cataloged DACs** across 4 status tiers:

| Status | Category | Highlighted Devices |
| :---: | :--- | :--- |
| 🟢 | **Hardware Verified & Tested** | **CrinEar Protocol Micro & Max**, **Tanchjim SPACE Pro**, **Kiwi Ears Allegro Mini**, **Moondrop FreeDSP / May Cable**, **TANGZU Wan'er S.G II Cable**, **BASN BmasterX 6 Plug**, **TTGK CX31993**, **Rythflo WD01**, **Bluetrum AB13X** |
| 🟡 | **Protocol Implemented (Awaiting Silicon Tester)** | **TRUTHEAR KEYX**, **Moondrop Chu II DSP**, **Tanchjim ONE DSP**, **FiiO / JadeAudio JA11**, **Fosi Audio DS3**, **FiiO LS-TC2**, **Celest Wyvern Abyss**, **Simgot EW300 DSP** |
| 🔵 | **Protocol In Development (Help Wanted)** | **FiiO KA15**, **FiiO KA17**, **FiiO BTR13**, **ddHiFi Memory DSP** |
| 🔴 | **Fixed Mask ROM (Host DSP & Qudelix Interop)** | **Qudelix-5K Profile Sync**, **Conexant CX31993 (TTGK, JCALLY JM6 Pro)**, **Apple USB-C A2049**, **Moondrop Dawn Pro** |

---

## 🛡️ Silicon Safety & Volume Lockout Prevention

`dac-peq-manager` was built from reverse engineering physical hardware captures to eliminate common firmware bricking and volume lockout bugs:

1. **Hardware Volume Lockout Prevention:**
   * On KTMicro KT02H20 hardware (Kiwi Ears Allegro Mini), writing register `0x11` (DAC reconstruction filter from JA11) or `0x66` (preamp) overwrites internal MCU codec attenuation registers, locking out physical volume buttons on iOS/Android.
   * `dac-peq-manager` strictly restricts writes to the 5 PEQ bands (`0x26`–`0x2F`) and Slot 3 (`0x24`), guaranteeing full native volume slider response on iPhone and YouTube Music.
2. **Official Factory Reset (`0x43 CLEAR`):**
   * If volume controls are locked by other tools, zeroing bands will not restore them. The official vendor `0x43 CLEAR` command completely wipes corrupted NVRAM and soft-reboots the MCU. Available via CLI (`dac-peq-manager reset -y`) and the Web Flasher.
3. **Conexant CX31993 OTP Safety Lock:**
   * Conexant CX31993 devices use fixed mask ROM with One-Time Programmable (OTP) registers. Sending KTMicro HID register writes risks corrupting descriptors. Flashing is automatically blocked for Conexant hardware and safely routed to host-side DSP exporters.
4. **2X Clock Divisor Auto-Detection:**
   * Automatically detects whether firmware has the 2X biquad clock divisor bug (`bcdDevice <= 0x0100`), halving calculation frequencies (`f / 2`) where needed and running native clocks on modern firmwares.
5. **Physical NVRAM Wear-Out Health Tracker:**
   * EEPROMs lack wear leveling (~10k–100k cycles). The built-in counter tracks total flash commits per VID:PID and alerts users if writes exceed safe daily thresholds.

---

## 💻 CLI Quickstart (Python)

### 1. Installation

```bash
git clone https://github.com/JohnnyGuerra/openpeq.git
cd openpeq
pip install -e dac-peq-manager/
```

### 2. Basic Commands

```bash
# Scan and inspect connected USB DACs
openpeq scan

# Audition a preset in live RAM (instant, zero flash wear)
openpeq apply bmasterx6

# Permanently save preset into hardware NVRAM
openpeq flash bmasterx6

# Read active PEQ bands directly from DAC hardware
openpeq read

# Factory reset NVRAM and recover volume control
openpeq reset -y

# Check flash memory write endurance history
openpeq flash-history

# Export 10-band target profile for software equalizers
openpeq export-pipewire bmasterx6 --full-target
openpeq export-apo bmasterx6 --full-target
```

---

## 🌐 OS Compatibility & Browser Requirements

The Web Flasher runs client-side in desktop Chromium browsers (**Google Chrome, Brave, Microsoft Edge, Opera**) using the official W3C WebHID API:

| Operating System | Setup Required | Admin / Driver Needed? | Notes |
| :--- | :---: | :---: | :--- |
| **macOS** (Apple Silicon & Intel) | **Zero (Plug & Play)** | ❌ No | Handled automatically via `IOKit`. Plug in and click *Connect*. |
| **Windows** (10 & 11) | **Zero (Plug & Play)** | ❌ No | Works out of the box. *Note:* Close any OEM companion software (e.g. Tanchjim PC app) if running, as Windows grants background apps exclusive HID locks. |
| **ChromeOS** (Chromebooks) | **Zero (Plug & Play)** | ❌ No | Works natively in the ChromeOS browser. |
| **Linux** (Arch, Ubuntu, Fedora, Debian) | **One-time udev rule** | ❌ No (after rule) | Linux restricts `/dev/hidraw*` to root by default. Run our one-line [udev setup](#-linux-webhid--udev-setup) to grant desktop seat access (`uaccess`). |
| **iOS / iPadOS / Android** | **Save once from PC** | N/A | Apple WebKit does not expose WebHID to mobile browsers. Save your EQ curve once from a PC/Mac/Chromebook, and it remains permanently active in the DAC hardware on your phone. |

---

## 🐧 Linux WebHID & udev Setup

On Linux distributions (Arch, Ubuntu, Debian, Fedora), access to raw USB HID nodes (`/dev/hidraw*`) is restricted to `root` by default. If you encounter a `NotAllowedError: Failed to open the device` in Chrome/Edge, configure non-root user access via our udev rules:

### Quick One-Liner Install
```bash
sudo cp udev/99-dac-peq.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Or write the rule directly:
```bash
sudo tee /etc/udev/rules.d/99-dac-peq.rules << 'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="31b2", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="31b2", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="3302", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3302", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2972", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2972", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="0023", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="0023", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="262a", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="262a", MODE="0666", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

> [!NOTE]
> **Ubuntu / Debian Snap Warning:** If you run Chromium or Chrome installed via **Ubuntu Snap**, Snap's AppArmor sandbox blocks access to `/dev/hidraw*` even with udev rules. Use the official `.deb` package or a Flatpak with device access permissions enabled.

---

## 🤝 Community & Contributing

We need your help testing devices and capturing USB packets!
* Read our **[CONTRIBUTING.md](./CONTRIBUTING.md)** guide to see how to capture WebHID sendReport logs in Chrome DevTools or Wireshark.
* Own a device marked **🟡**? Submit a **[Hardware Verification Report](https://github.com/JohnnyGuerra/openpeq/issues/new?template=dac_hardware_report.yml)**!
* Want support for a new DAC? Open a **[New DAC Support Request](https://github.com/JohnnyGuerra/openpeq/issues/new?template=new_dac_request.yml)**.

---

## 📜 License & Disclaimers

* **License:** [MIT License](./LICENSE)
* **Disclaimer:** `OpenPEQ` is an independent, community-driven open-source project. Not affiliated with KTMicro, Kiwi Ears, FiiO, Moondrop, Tanchjim, or Truthear.

---

## ✒️ Citation & Attribution

If you use `OpenPEQ`, its reverse-engineered KTMicro/WalkPlay USB register maps, or the `dac-peq-core` Rust engine in your own project, fork, or research, please provide attribution:

```text
Guerra, J. (2026). OpenPEQ: Universal hardware DSP flasher & Web equalizer for portable USB-C DACs and IEMs.
GitHub: https://github.com/JohnnyGuerra/openpeq
```

```bibtex
@software{guerra2026openpeq,
  author = {Johnny Guerra},
  title = {OpenPEQ: Universal hardware DSP flasher & Web equalizer for portable USB-C DACs and IEMs},
  url = {https://github.com/JohnnyGuerra/openpeq},
  year = {2026}
}
```
