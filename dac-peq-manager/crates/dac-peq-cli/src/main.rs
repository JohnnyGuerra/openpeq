use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use colored::*;
use std::ffi::CString;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::Duration;

use dac_peq_core::models::PeqPreset;
use dac_peq_core::*;

const KNOWN_HARDWARE: &[(u16, u16, &str)] = &[
    (0x31B2, 0x0111, "Kiwi Ears Allegro Mini / KT02H20"),
    (0x2972, 0x0102, "FiiO JA11"),
    (0x2972, 0x0034, "FiiO KA11 (Legacy)"),
    (0x1908, 0x2070, "JCALLY JM20 / JM6 Pro"),
    (0x3302, 0x022A, "Moondrop Click"),
    (0x3302, 0x43CC, "CrinEar Protocol Max (WalkPlay)"),
    (0x3302, 0x4307, "Tanchjim SPACE Pro (WalkPlay)"),
    (0x3302, 0x431D, "Tanchjim SPACE Pro Rev B (WalkPlay)"),
    (0x31B2, 0x0112, "Moondrop FreeDSP / Mays"),
];

#[derive(Parser)]
#[command(name = "dac-peq")]
#[command(about = "Unified Parametric Equalizer Manager & Hardware NVRAM Flasher for USB DACs", long_about = None)]
#[command(version)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan and display connected USB DACs
    #[command(alias = "status")]
    Scan,

    /// Render terminal ASCII frequency response curve
    Plot {
        /// Preset name, JSON file path, or target curve
        preset: String,
    },

    /// Apply PEQ preset to live DSP RAM (instant listening, volatile)
    Apply {
        /// Preset name or path to JSON file
        preset: String,

        /// Hardware slot ID (1-4, default 3)
        #[arg(short, long, default_value_t = 3)]
        slot: u8,

        /// Target USB Vendor ID in hex (e.g. 0x31B2)
        #[arg(long)]
        vid: Option<String>,

        /// Target USB Product ID in hex (e.g. 0x0111)
        #[arg(long)]
        pid: Option<String>,

        /// Simulate writes in dry-run mode without accessing hardware
        #[arg(long, alias = "mock")]
        dry_run: bool,
    },

    /// Burn PEQ preset to hardware NVRAM flash (persists across unplugs)
    Flash {
        /// Preset name or path to JSON file
        preset: String,

        /// Hardware slot ID (1-4, default 3)
        #[arg(short, long, default_value_t = 3)]
        slot: u8,

        /// Skip interactive confirmation
        #[arg(short, long)]
        yes: bool,

        /// Target USB Vendor ID in hex (e.g. 0x31B2)
        #[arg(long)]
        vid: Option<String>,

        /// Target USB Product ID in hex (e.g. 0x0111)
        #[arg(long)]
        pid: Option<String>,

        /// Simulate flash in dry-run mode without accessing hardware
        #[arg(long, alias = "mock")]
        dry_run: bool,
    },

    /// Factory reset DAC registers to stock defaults (0x43 CLEAR)
    Reset {
        /// Skip interactive confirmation
        #[arg(short, long)]
        yes: bool,

        /// Target USB Vendor ID in hex (e.g. 0x31B2)
        #[arg(long)]
        vid: Option<String>,

        /// Target USB Product ID in hex (e.g. 0x0111)
        #[arg(long)]
        pid: Option<String>,

        /// Simulate reset in dry-run mode without accessing hardware
        #[arg(long, alias = "mock")]
        dry_run: bool,
    },

    /// Export preset to PipeWire filter-chain configuration
    ExportPipewire {
        /// Preset name or path to JSON file
        preset: String,

        /// Output file path (default: stdout or ~/.config/pipewire/pipewire.conf.d/)
        #[arg(short, long)]
        output: Option<PathBuf>,
    },

    /// Export preset to EqualizerAPO and Wavelet formats
    ExportApo {
        /// Preset name or path to JSON file
        preset: String,

        /// Output directory path
        #[arg(short, long)]
        output_dir: Option<PathBuf>,
    },

    /// Print recommended Linux udev rules for driverless access
    Udev,
}

fn resolve_preset(preset_str: &str) -> Result<PeqPreset> {
    let p = Path::new(preset_str);
    if p.is_file() {
        let content = fs::read_to_string(p)
            .with_context(|| format!("Failed to read preset file at {}", p.display()))?;
        let preset: PeqPreset = serde_json::from_str(&content)
            .with_context(|| format!("Invalid JSON preset at {}", p.display()))?;
        return Ok(preset);
    }

    // Check presets directory relative to executable or current dir
    for base in &[
        PathBuf::from("presets"),
        PathBuf::from("dac-peq-manager/presets"),
        PathBuf::from("../presets"),
    ] {
        let candidate = base.join(format!("{preset_str}.json"));
        if candidate.is_file() {
            let content = fs::read_to_string(&candidate)?;
            let preset: PeqPreset = serde_json::from_str(&content)?;
            return Ok(preset);
        }
        let target_candidate = base.join("targets").join(format!("{preset_str}.json"));
        if target_candidate.is_file() {
            let content = fs::read_to_string(&target_candidate)?;
            let preset: PeqPreset = serde_json::from_str(&content)?;
            return Ok(preset);
        }
    }

    anyhow::bail!("Preset '{}' not found as a file or in bundled presets directory.", preset_str);
}

fn parse_hex_u16(s: &str) -> Result<u16> {
    let clean = s.trim_start_matches("0x").trim_start_matches("0X");
    u16::from_str_radix(clean, 16).with_context(|| format!("Invalid hex ID: {s}"))
}

fn write_hid_report(dev: &hidapi::HidDevice, rpt_bytes: &[u8]) -> Result<()> {
    let mut buf = [0u8; 65];
    buf[0] = 0x00;
    let copy_len = rpt_bytes.len().min(64);
    buf[1..1 + copy_len].copy_from_slice(&rpt_bytes[..copy_len]);
    dev.write(&buf)
        .with_context(|| "Failed to write 65-byte HID report to USB DAC")?;
    thread::sleep(Duration::from_millis(35));
    Ok(())
}

fn find_ktmicro_device(
    api: &hidapi::HidApi,
    vid_filter: Option<u16>,
    pid_filter: Option<u16>,
) -> Result<Option<(CString, u16, u16, String, bool)>> {
    for dev in api.device_list() {
        let vid = dev.vendor_id();
        let pid = dev.product_id();
        let prod = dev.product_string().unwrap_or("Unknown Audio Device").to_string();

        if let Some(target_v) = vid_filter {
            if vid != target_v {
                continue;
            }
        }
        if let Some(target_p) = pid_filter {
            if pid != target_p {
                continue;
            }
        }

        // Safety check: Conexant CX31993 must never be targeted for hardware flashing
        if is_conexant_cx31993(vid, pid, Some(&prod)) || vid == 0x0572 || (vid == 0x3302 && pid == 0x3365) {
            if vid_filter.is_some() || pid_filter.is_some() {
                anyhow::bail!(
                    "Target device [{:04X}:{:04X}] {} is Conexant CX31993 (Fixed Mask ROM). Hardware flashing is permanently blocked to prevent bricking!",
                    vid, pid, prod
                );
            }
            continue;
        }

        let is_ktmicro = vid == 0x31B2
            || (vid == 0x2972 && (pid == 0x0102 || pid == 0x0034))
            || (vid == 0x1908 && pid == 0x2070)
            || (vid == 0x3302 && pid == 0x022A)
            || vid_filter.is_some();

        if is_ktmicro {
            let rel = dev.release_number();
            let is_ja11 = vid == 0x2972 && pid == 0x0102;
            let clock_divisor_2x = if is_ja11 && rel >= 0x0180 {
                false
            } else {
                rel <= 0x0100
            };
            return Ok(Some((dev.path().to_owned(), vid, pid, prod, clock_divisor_2x)));
        }
    }

    Ok(None)
}

fn render_ascii_plot(p: &PeqPreset) {
    println!("{}\n", format!("Preset: {}", p.name).bold().cyan());
    if let Some(desc) = &p.description {
        println!("  Description: {}\n", desc.dimmed());
    }

    let points = 60;
    let freqs = generate_log_frequencies(20.0, 20000.0, points);
    let curve = compute_composite_response(&p.bands, p.preamp, &freqs, 48000.0);

    let max_gain = curve.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let min_gain = curve.iter().copied().fold(f64::INFINITY, f64::min);

    let rows = 15;
    let cols = 60;

    let mut top_db = (max_gain.max(3.0) / 3.0).ceil() * 3.0;
    let mut bot_db = (min_gain.min(-3.0) / 3.0).floor() * 3.0;
    if top_db - bot_db < 6.0 {
        top_db = 6.0;
        bot_db = -6.0;
    }
    let span = top_db - bot_db;

    let mut grid = vec![vec![' '; cols]; rows];

    // Reference 0.0 dB line '-'
    let zero_row = ((top_db - 0.0) / span * (rows - 1) as f64).round() as i32;
    if zero_row >= 0 && zero_row < rows as i32 {
        for c in 0..cols {
            grid[zero_row as usize][c] = '-';
        }
    }

    // Plot response curve '*'
    for c in 0..cols {
        let val = curve[c];
        let r = ((top_db - val) / span * (rows - 1) as f64).round() as i32;
        if r >= 0 && r < rows as i32 {
            grid[r as usize][c] = '*';
        }
    }

    // Render ASCII graph
    for r in 0..rows {
        let row_db = top_db - (r as f64 * span / (rows - 1) as f64);
        let row_str: String = grid[r].iter().collect();
        println!("{:>+5.1} dB |{}", row_db, row_str);
    }

    println!("       +{:-<60}+", "");
    println!("        20Hz        100Hz        1kHz         10kHz    20kHz\n");

    let rec_preamp = calculate_recommended_preamp(&p.bands, 0.5, 48000.0);
    println!(
        "  Peak Gain: {:+.2} dB | Min Gain: {:+.2} dB | Preamp: {:+.2} dB | Auto-Preamp Rec: {:+.2} dB",
        max_gain, min_gain, p.preamp, rec_preamp
    );

    println!("\n  Bands ({}):", p.bands.len());
    for (i, b) in p.bands.iter().enumerate() {
        println!(
            "    [{}] {:<9} {:>7.1} Hz  {:>+6.2} dB  Q={:<5.2}",
            i + 1,
            b.filter_type.as_str(),
            b.freq,
            b.gain,
            b.q
        );
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Scan => {
            println!("{}", "Scanning USB devices for supported Audio DACs...".bold().cyan());
            let api = match hidapi::HidApi::new() {
                Ok(api) => api,
                Err(e) => {
                    eprintln!("{}: {}", "[ERROR]".bold().red(), e);
                    std::process::exit(1);
                }
            };

            let mut found = 0;
            for dev in api.device_list() {
                let vid = dev.vendor_id();
                let pid = dev.product_id();
                let prod = dev.product_string().unwrap_or("Unknown Audio Device");
                let is_cx = is_conexant_cx31993(vid, pid, Some(prod))
                    || vid == 0x0572
                    || (vid == 0x3302 && pid == 0x3365);

                let is_known = KNOWN_HARDWARE.iter().any(|(k_vid, k_pid, _)| *k_vid == vid && *k_pid == pid);
                let is_ktmicro = vid == 0x31B2
                    || (vid == 0x2972 && (pid == 0x0102 || pid == 0x0034))
                    || (vid == 0x1908 && pid == 0x2070)
                    || (vid == 0x3302 && pid == 0x022A);
                let is_walkplay = (vid == 0x3302 && pid != 0x022A && pid != 0x3365)
                    || (vid == 0x0BDA && pid == 0x0023);

                if is_cx || is_known || is_ktmicro || is_walkplay {
                    found += 1;
                    let known_name = KNOWN_HARDWARE
                        .iter()
                        .find(|(k_vid, k_pid, _)| *k_vid == vid && *k_pid == pid)
                        .map(|(_, _, name)| *name)
                        .unwrap_or(prod);

                    let badge = if is_cx {
                        "[HOST-DSP ONLY - Fixed Mask ROM]".bold().yellow()
                    } else if is_ktmicro {
                        "[HARDWARE FLASHABLE (KTMicro KT02H20)]".bold().green()
                    } else if is_walkplay {
                        "[HARDWARE FLASHABLE (WalkPlay DSP)]".bold().green()
                    } else {
                        "[SUPPORTED AUDIO DEVICE]".bold().green()
                    };

                    println!(
                        "  • [{:04X}:{:04X}] {} (rev: 0x{:04X}) — {}",
                        vid, pid, known_name.bold(), dev.release_number(), badge
                    );
                }
            }

            if found == 0 {
                println!("{}", "  No supported USB DACs currently detected. Connect device and retry.".dimmed());
            } else {
                println!("\n{} {} supported DAC(s) found.", "[OK]".bold().green(), found);
            }
        }

        Commands::Plot { preset } => {
            let p = resolve_preset(&preset)?;
            render_ascii_plot(&p);
        }

        Commands::Apply { preset, slot, vid, pid, dry_run } => {
            let target_vid = vid.as_deref().map(parse_hex_u16).transpose()?;
            let target_pid = pid.as_deref().map(parse_hex_u16).transpose()?;

            let mut p = resolve_preset(&preset)?;
            if p.bands.len() > 5 {
                println!(
                    "{} Preset has {} bands; decimating to 5 hardware bands...",
                    "[INFO]".bold().blue(),
                    p.bands.len()
                );
                p.bands = decimate_bands(&p.bands, 5, true, 48000.0);
            }

            println!("{}", format!("[APPLY] Loading preset '{}' into live DSP RAM (Slot {})...", p.name, slot).bold().cyan());

            if dry_run {
                let v = target_vid.unwrap_or(0x31B2);
                let p_id = target_pid.unwrap_or(0x0111);
                assert_safe_for_hardware_flash(v, p_id, None)?;
                let reports = encode_ram_preset_payload(&p, v, p_id, slot, true)?;
                println!("  Generated {} low-level RAM reports.", reports.len());
                for (i, r) in reports.iter().enumerate() {
                    let b = r.as_bytes();
                    println!("    Report #{}: {:02X?}", i + 1, b);
                }
                println!("{} Simulated live DSP write (Dry-run mode active).", "[DRY-RUN OK]".bold().green());
                return Ok(());
            }

            let api = hidapi::HidApi::new().context("Failed to initialize HIDAPI")?;
            let matched = find_ktmicro_device(&api, target_vid, target_pid)?;
            let (dev_path, dev_vid, dev_pid, dev_prod, clock_divisor_2x) = match matched {
                Some(info) => info,
                None => {
                    anyhow::bail!("No compatible KTMicro USB DAC found. Connect a device or use --dry-run.");
                }
            };

            assert_safe_for_hardware_flash(dev_vid, dev_pid, Some(&dev_prod))?;
            println!(
                "  Connecting to [{:04X}:{:04X}] {} (2X clock compensation: {})...",
                dev_vid, dev_pid, dev_prod.bold(), clock_divisor_2x
            );

            let device = api.open_path(&dev_path).with_context(|| {
                format!("Failed to open USB device [{:04X}:{:04X}]. Ensure udev rules are installed.", dev_vid, dev_pid)
            })?;

            let reports = encode_ram_preset_payload(&p, dev_vid, dev_pid, slot, clock_divisor_2x)?;
            for r in &reports {
                write_hid_report(&device, r.as_bytes())?;
            }

            println!("{} PEQ active in live DSP RAM.", "[OK]".bold().green());
        }

        Commands::Flash { preset, slot, yes, vid, pid, dry_run } => {
            let target_vid = vid.as_deref().map(parse_hex_u16).transpose()?;
            let target_pid = pid.as_deref().map(parse_hex_u16).transpose()?;

            let mut p = resolve_preset(&preset)?;
            if p.bands.len() > 5 {
                println!(
                    "{} Preset has {} bands; decimating to 5 hardware bands...",
                    "[INFO]".bold().blue(),
                    p.bands.len()
                );
                p.bands = decimate_bands(&p.bands, 5, true, 48000.0);
            }

            if dry_run {
                let v = target_vid.unwrap_or(0x31B2);
                let p_id = target_pid.unwrap_or(0x0111);
                assert_safe_for_hardware_flash(v, p_id, None)?;
                println!("{}", format!("[FLASH] Burning preset '{}' to NVRAM flash (Slot {})...", p.name, slot).bold().cyan());
                let reports = encode_preset_payload(&p, v, p_id, slot, true, true)?;
                println!("  Generated {} low-level HID reports (including 0x53 COMMIT).", reports.len());
                for (i, r) in reports.iter().enumerate() {
                    let b = r.as_bytes();
                    println!("    Report #{}: {:02X?}", i + 1, b);
                }
                println!("{} Verified safety guard & simulated hardware commit (Dry-run mode active).", "[DRY-RUN OK]".bold().green());
                return Ok(());
            }

            let api = hidapi::HidApi::new().context("Failed to initialize HIDAPI")?;
            let matched = find_ktmicro_device(&api, target_vid, target_pid)?;
            let (dev_path, dev_vid, dev_pid, dev_prod, clock_divisor_2x) = match matched {
                Some(info) => info,
                None => {
                    anyhow::bail!("No compatible KTMicro USB DAC found. Connect a device or use --dry-run.");
                }
            };

            assert_safe_for_hardware_flash(dev_vid, dev_pid, Some(&dev_prod))?;

            if !yes {
                eprintln!("{}", "⚠️  NVRAM Flash commits permanently to hardware flash memory (~10k-100k cycles).".yellow());
                eprint!("Commit preset '{}' to hardware flash on [{:04X}:{:04X}] {}? [y/N]: ", p.name, dev_vid, dev_pid, dev_prod);
                std::io::stderr().flush()?;
                let mut input = String::new();
                std::io::stdin().read_line(&mut input)?;
                if !input.trim().eq_ignore_ascii_case("y") {
                    println!("Aborted.");
                    return Ok(());
                }
            }

            println!("{}", format!("[FLASH] Burning preset '{}' to NVRAM flash (Slot {})...", p.name, slot).bold().cyan());
            println!(
                "  Connecting to [{:04X}:{:04X}] {} (2X clock compensation: {})...",
                dev_vid, dev_pid, dev_prod.bold(), clock_divisor_2x
            );

            let device = api.open_path(&dev_path).with_context(|| {
                format!("Failed to open USB device [{:04X}:{:04X}]. Ensure udev rules are installed.", dev_vid, dev_pid)
            })?;

            let reports = encode_preset_payload(&p, dev_vid, dev_pid, slot, clock_divisor_2x, true)?;
            for r in &reports {
                write_hid_report(&device, r.as_bytes())?;
            }

            // Consume commit response if returned by MCU before soft reboot
            let mut ack = [0u8; 64];
            let _ = device.read_timeout(&mut ack, 300);

            println!("{} PEQ curve successfully burned to hardware NVRAM flash! MCU soft-rebooting...", "[OK]".bold().green());
        }

        Commands::Reset { yes, vid, pid, dry_run } => {
            let target_vid = vid.as_deref().map(parse_hex_u16).transpose()?;
            let target_pid = pid.as_deref().map(parse_hex_u16).transpose()?;

            if dry_run {
                let rpt = encode_factory_reset();
                println!("{}", "[RESET] Generating factory reset command (0x43 CLEAR)...".bold().cyan());
                println!("  Report: {:02X?}", rpt.as_bytes());
                println!("{} Factory reset simulated successfully (0x43 CLEAR executed in dry-run).", "[DRY-RUN OK]".bold().green());
                return Ok(());
            }

            let api = hidapi::HidApi::new().context("Failed to initialize HIDAPI")?;
            let matched = find_ktmicro_device(&api, target_vid, target_pid)?;
            let (dev_path, dev_vid, dev_pid, dev_prod, _) = match matched {
                Some(info) => info,
                None => {
                    anyhow::bail!("No compatible KTMicro USB DAC found. Connect a device or use --dry-run.");
                }
            };

            assert_safe_for_hardware_flash(dev_vid, dev_pid, Some(&dev_prod))?;

            if !yes {
                eprint!("Send 0x43 CLEAR to restore stock factory defaults on [{:04X}:{:04X}] {}? [y/N]: ", dev_vid, dev_pid, dev_prod);
                std::io::stderr().flush()?;
                let mut input = String::new();
                std::io::stdin().read_line(&mut input)?;
                if !input.trim().eq_ignore_ascii_case("y") {
                    println!("Aborted.");
                    return Ok(());
                }
            }

            println!(
                "  Connecting to [{:04X}:{:04X}] {}...",
                dev_vid, dev_pid, dev_prod.bold()
            );

            let device = api.open_path(&dev_path).with_context(|| {
                format!("Failed to open USB device [{:04X}:{:04X}]. Ensure udev rules are installed.", dev_vid, dev_pid)
            })?;

            let rpt = encode_factory_reset();
            write_hid_report(&device, rpt.as_bytes())?;

            let mut ack = [0u8; 64];
            let _ = device.read_timeout(&mut ack, 300);

            println!("{} Factory reset command sent (0x43 CLEAR). Rebooting MCU...", "[OK]".bold().green());
        }

        Commands::ExportPipewire { preset, output } => {
            let p = resolve_preset(&preset)?;
            let conf = format_pipewire_filter_chain(&p, DEFAULT_CX31993_SINK)?;
            if let Some(out_p) = output {
                if let Some(parent) = out_p.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::write(&out_p, conf)?;
                println!("{} PipeWire filter-chain saved to {}", "[OK]".bold().green(), out_p.display());
            } else {
                println!("{conf}");
            }
        }

        Commands::ExportApo { preset, output_dir } => {
            let p = resolve_preset(&preset)?;
            let apo = format_equalizer_apo(&p);
            let wav = format_wavelet_graphiceq(&p);

            let dir = output_dir.unwrap_or_else(|| PathBuf::from("exports"));
            fs::create_dir_all(&dir)?;

            let slug = p.name.replace([' ', '-'], "_").to_lowercase();
            let apo_file = dir.join(format!("{slug}_apo.txt"));
            let wav_file = dir.join(format!("{slug}_wavelet.txt"));

            fs::write(&apo_file, apo)?;
            fs::write(&wav_file, wav)?;

            println!("{} Saved EqualizerAPO config to {}", "[OK]".bold().green(), apo_file.display());
            println!("{} Saved Wavelet GraphicEQ config to {}", "[OK]".bold().green(), wav_file.display());
        }

        Commands::Udev => {
            println!(r#"# /etc/udev/rules.d/99-dac-peq.rules
# udev rules for dac-peq-manager
# Grants unprivileged user access to supported USB-C DAC dongles and DSP cables for WebHID and CLI.
#
# Installation:
#   sudo cp udev/99-dac-peq.rules /etc/udev/rules.d/
#   sudo udevadm control --reload-rules && sudo udevadm trigger

# KTMicro / Kiwi Ears (Allegro Mini, Allegro Pro, S-Link) / Moondrop (FreeDSP, May) / BASN BmasterX
SUBSYSTEM=="usb", ATTRS{{idVendor}}=="31b2", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="31b2", MODE="0666", TAG+="uaccess"

# WalkPlay / CrinEar (Protocol Micro, Protocol Max) / Tanchjim (SPACE Pro 0x4307, STARGATE II) / TTGK
SUBSYSTEM=="usb", ATTRS{{idVendor}}=="3302", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="3302", MODE="0666", TAG+="uaccess"

# FiiO / JadeAudio (JA11, LS-TC2, KA15)
SUBSYSTEM=="usb", ATTRS{{idVendor}}=="2972", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="2972", MODE="0666", TAG+="uaccess"

# WalkPlay Realtek OEM
SUBSYSTEM=="usb", ATTRS{{idVendor}}=="0bda", ATTRS{{idProduct}}=="0023", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="0bda", ATTRS{{idProduct}}=="0023", MODE="0666", TAG+="uaccess"

# Celest / Kinera (Wyvern Abyss DSP)
SUBSYSTEM=="usb", ATTRS{{idVendor}}=="262a", TAG+="uaccess"
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="262a", MODE="0666", TAG+="uaccess"
"#);
        }
    }

    Ok(())
}
