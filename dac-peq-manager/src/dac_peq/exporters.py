"""Host-side DSP configuration generators for JCALLY JM6 Pro (Conexant CX31993)
and universal software parametric equalizers.

Supports:
  1. PipeWire filter-chain configuration bound to Conexant CX31993 ALSA sink.
  2. EqualizerAPO .txt configuration.
  3. Wavelet GraphicEQ .txt and 9-band interpolated Wavelet JSON profiles for Android.

--------------------------------------------------------------------------------
ACKNOWLEDGMENTS & ATTRIBUTION:
  - PipeWire filter-chain graph specification and builtin DSP filter definitions:
    PipeWire project (Wim Taymans et al., https://pipewire.org)
  - EqualizerAPO text configuration format:
    EqualizerAPO project (Peter Verheet, https://sourceforge.net/projects/equalizerapo/)
  - Wavelet GraphicEQ 127-frequency format & AutoEq normalization conventions:
    AutoEq project (Jaakko Pasanen, https://github.com/jaakkopasanen/AutoEq)
    Wavelet app by Pitched Apps (https://wavelet.app/)
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from dac_peq.biquad import (
    calculate_recommended_preamp,
    compute_composite_response,
    generate_log_frequencies,
)


DEFAULT_CX31993_SINK = "alsa_output.usb-Conexant_CX31993*"


def format_pipewire_filter_chain(
    preset: Dict[str, Any],
    sink_target: str = DEFAULT_CX31993_SINK,
    auto_preamp: bool = False,
) -> str:
    """Generate PipeWire filter-chain configuration content."""
    preset_name = preset.get("name", "custom")
    preset_slug = preset_name.replace(" ", "_").replace("-", "_").lower()
    description = preset.get("description", f"JM6 Pro EQ Preset {preset_name}")
    bands = preset.get("bands", [])
    if len(bands) < 1:
        raise ValueError("Preset must contain at least 1 band.")
    num_bands = len(bands)

    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))
    linear_gain = round(10.0 ** (preamp_db / 20.0), 4)

    # Map filter types to PipeWire builtin labels
    type_map = {
        "PK": "bq_peaking",
        "PEAK": "bq_peaking",
        "PEAKING": "bq_peaking",
        "LSQ": "bq_lowshelf",
        "LOW_SHELF": "bq_lowshelf",
        "LOWSHELF": "bq_lowshelf",
        "HSQ": "bq_highshelf",
        "HIGH_SHELF": "bq_highshelf",
        "HIGHSHELF": "bq_highshelf",
    }

    # Generate node definitions for FL and FR channels
    nodes = []

    # 1. Preamp linear nodes
    nodes.append(f"""                    # Preamp Gain Stage ({preamp_db:+.1f} dB = linear {linear_gain})
                    {{
                        type   = builtin
                        name   = "preamp_fl"
                        label  = linear
                        control = {{
                            "Gain" = {linear_gain}
                        }}
                    }}
                    {{
                        type   = builtin
                        name   = "preamp_fr"
                        label  = linear
                        control = {{
                            "Gain" = {linear_gain}
                        }}
                    }}""")

    # 2. Biquad nodes for each band (FL and FR)
    for i in range(num_bands):
        b = bands[i]
        b_idx = i + 1
        ftype = type_map.get(str(b.get("type", "PK")).upper(), "bq_peaking")
        freq = float(b.get("freq", 1000.0))
        gain = float(b.get("gain", 0.0))
        q = float(b.get("q", 1.0))
        comment = b.get("comment", f"Band {b_idx}")

        nodes.append(f"""                    # Band {b_idx}: {b.get('type', 'PK')} {freq:.1f} Hz, {gain:+.1f} dB, Q={q:.2f} ({comment})
                    {{
                        type   = builtin
                        name   = "eq_band{b_idx}_fl"
                        label  = {ftype}
                        control = {{
                            "Freq" = {freq:.1f}
                            "Gain" = {gain:.2f}
                            "Q"    = {q:.2f}
                        }}
                    }}
                    {{
                        type   = builtin
                        name   = "eq_band{b_idx}_fr"
                        label  = {ftype}
                        control = {{
                            "Freq" = {freq:.1f}
                            "Gain" = {gain:.2f}
                            "Q"    = {q:.2f}
                        }}
                    }}""")

    # 3. Chained links
    links = [
        """                    # Route Preamp -> Band 1
                    { output = "preamp_fl:Out", input = "eq_band1_fl:In" }
                    { output = "preamp_fr:Out", input = "eq_band1_fr:In" }"""
    ]
    for i in range(1, num_bands):
        prev = i
        curr = i + 1
        links.append(f"""                    # Route Band {prev} -> Band {curr}
                    {{ output = "eq_band{prev}_fl:Out", input = "eq_band{curr}_fl:In" }}
                    {{ output = "eq_band{prev}_fr:Out", input = "eq_band{curr}_fr:In" }}""")

    nodes_block = "\n".join(nodes)
    links_block = "\n".join(links)

    conf = f"""# PipeWire filter-chain configuration for JCALLY JM6 Pro (Conexant CX31993)
# Preset: {preset_name}
# Description: {description}
# Generated by dac-peq-manager

context.modules = [
    {{
        name = libpipewire-module-filter-chain
        args = {{
            node.description = "JCALLY JM6 Pro DSP [{preset_name}]"
            media.name       = "JCALLY JM6 Pro DSP [{preset_name}]"
            filter.graph = {{
                nodes = [
{nodes_block}
                ]
                links = [
{links_block}
                ]
                inputs  = [ "preamp_fl:In", "preamp_fr:In" ]
                outputs = [ "eq_band{num_bands}_fl:Out", "eq_band{num_bands}_fr:Out" ]
            }}
            capture.props = {{
                node.name        = "effect_input.jm6pro_{preset_slug}"
                media.class      = "Audio/Sink"
                audio.position   = [ "FL", "FR" ]
                node.description = "JM6 Pro [{preset_name}] Virtual Sink"
            }}
            playback.props = {{
                node.name        = "effect_output.jm6pro_{preset_slug}"
                node.target      = "{sink_target}"
                audio.position   = [ "FL", "FR" ]
                node.passive     = true
            }}
        }}
    }}
]
"""
    return conf


def export_pipewire_conf(
    preset: Dict[str, Any],
    output_path: Optional[str | Path] = None,
    sink_target: str = DEFAULT_CX31993_SINK,
    auto_preamp: bool = False,
) -> Path:
    """Write PipeWire filter-chain configuration file."""
    preset_name = preset.get("name", "custom")
    preset_slug = preset_name.replace(" ", "_").replace("-", "_").lower()

    if output_path is None:
        pw_dir = Path.home() / ".config" / "pipewire" / "pipewire.conf.d"
        pw_dir.mkdir(parents=True, exist_ok=True)
        target = pw_dir / f"99-jm6pro-{preset_slug}.conf"
    else:
        target = Path(output_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)

    content = format_pipewire_filter_chain(preset, sink_target=sink_target, auto_preamp=auto_preamp)
    target.write_text(content, encoding="utf-8")
    return target


def format_equalizer_apo(preset: Dict[str, Any], auto_preamp: bool = False) -> str:
    """Generate standard EqualizerAPO .txt configuration."""
    preset_name = preset.get("name", "custom")
    description = preset.get("description", "")
    bands = preset.get("bands", [])

    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))

    lines = [
        "# EqualizerAPO Configuration",
        f"# Preset: {preset_name}",
        f"# Description: {description}",
        "# Generated by dac-peq-manager for JCALLY JM6 Pro & Universal Host DSP",
        "",
        f"Preamp: {preamp_db:+.1f} dB",
    ]

    type_map = {
        "PK": "PK",
        "PEAK": "PK",
        "PEAKING": "PK",
        "LSQ": "LSQ",
        "LOW_SHELF": "LSQ",
        "LOWSHELF": "LSQ",
        "HSQ": "HSQ",
        "HIGH_SHELF": "HSQ",
        "HIGHSHELF": "HSQ",
    }

    for i, b in enumerate(bands):
        idx = i + 1
        ftype = type_map.get(str(b.get("type", "PK")).upper(), "PK")
        freq = float(b.get("freq", 1000.0))
        gain = float(b.get("gain", 0.0))
        q = float(b.get("q", 1.0))
        lines.append(f"Filter {idx}: ON {ftype} Fc {freq:.1f} Hz Gain {gain:+.1f} dB Q {q:.2f}")

    return "\n".join(lines) + "\n"


def format_wavelet_graphiceq(
    preset: Dict[str, Any],
    points: int = 127,
    auto_preamp: bool = False,
) -> str:
    """Generate AutoEq-compatible GraphicEQ string for Wavelet import."""
    bands = preset.get("bands", [])
    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))

    frequencies = generate_log_frequencies(20.0, 20000.0, points)
    curve = compute_composite_response(bands, preamp_db, frequencies)

    # Format as: GraphicEQ: 20 -0.5; 21 -0.5; ...
    pairs = [f"{round(f)} {val:.1f}" for f, val in zip(frequencies, curve)]
    return "GraphicEQ: " + "; ".join(pairs) + "\n"


def format_wavelet_json(preset: Dict[str, Any], auto_preamp: bool = False) -> Dict[str, Any]:
    """Generate Wavelet JSON profile with 9-band interpolated gains and GraphicEQ string."""
    preset_name = preset.get("name", "custom")
    description = preset.get("description", "")
    bands = preset.get("bands", [])
    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))

    # Standard Wavelet 9-band center frequencies (Hz)
    wavelet_9_bands = [53.8, 107.7, 215.3, 430.7, 861.3, 1722.7, 3445.3, 6890.6, 13781.3]
    gains_9 = compute_composite_response(bands, preamp_db, wavelet_9_bands)

    nine_band_dict = {}
    for f, g in zip(wavelet_9_bands, gains_9):
        nine_band_dict[f"{f:.1f}Hz"] = round(g, 1)

    graphiceq_str = format_wavelet_graphiceq(preset, auto_preamp=auto_preamp).strip()

    return {
        "name": preset_name,
        "description": description,
        "target": "JCALLY JM6 Pro (Conexant CX31993) / Android Wavelet",
        "preamp": preamp_db,
        "nine_band_gains": nine_band_dict,
        "graphiceq": graphiceq_str,
        "bands": [
            {
                "index": i + 1,
                "type": b.get("type", "PK"),
                "freq": b.get("freq", 1000.0),
                "gain": b.get("gain", 0.0),
                "q": b.get("q", 1.0),
            }
            for i, b in enumerate(bands)
        ],
    }


def export_apo_suite(
    preset: Dict[str, Any],
    output_dir: str | Path = "./exports",
    auto_preamp: bool = False,
) -> Dict[str, Path]:
    """Export EqualizerAPO .txt, Wavelet GraphicEQ .txt, and Wavelet JSON files."""
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    preset_name = preset.get("name", "custom")
    preset_slug = preset_name.replace(" ", "_").replace("-", "_").lower()

    apo_file = out_dir / f"{preset_slug}_equalizer_apo.txt"
    wavelet_txt = out_dir / f"{preset_slug}_wavelet_graphiceq.txt"
    wavelet_json = out_dir / f"{preset_slug}_wavelet.json"

    apo_file.write_text(format_equalizer_apo(preset, auto_preamp=auto_preamp), encoding="utf-8")
    wavelet_txt.write_text(format_wavelet_graphiceq(preset, auto_preamp=auto_preamp), encoding="utf-8")
    wavelet_json.write_text(json.dumps(format_wavelet_json(preset, auto_preamp=auto_preamp), indent=2), encoding="utf-8")

    return {
        "equalizer_apo": apo_file,
        "wavelet_txt": wavelet_txt,
        "wavelet_json": wavelet_json,
    }


def format_qudelix_text(
    preset: Dict[str, Any],
    auto_preamp: bool = False,
    pad_to_10: bool = True,
) -> str:
    """Generate Qudelix-5K standard 10-band text configuration.

    Compatible with Qudelix-5K Chrome Extension and mobile app import.
    Uses standard AutoEq filter line syntax with 10 bands.
    """
    preset_name = preset.get("name", "custom")
    description = preset.get("description", "")
    bands = preset.get("bands", [])

    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))

    lines = [
        f"# Qudelix-5K PEQ Profile: {preset_name}",
        f"# Description: {description}",
        "# Compatible with Qudelix-5K Chrome App & Mobile App import",
        f"Preamp: {preamp_db:+.1f} dB",
    ]

    type_map = {
        "PK": "PK",
        "PEAK": "PK",
        "PEAKING": "PK",
        "LSQ": "LSQ",
        "LOW_SHELF": "LSQ",
        "LOWSHELF": "LSQ",
        "HSQ": "HSQ",
        "HIGH_SHELF": "HSQ",
        "HIGHSHELF": "HSQ",
    }

    total_slots = 10 if pad_to_10 else len(bands)
    for i in range(total_slots):
        idx = i + 1
        if i < len(bands):
            b = bands[i]
            ftype = type_map.get(str(b.get("type", "PK")).upper(), "PK")
            freq = float(b.get("freq", 1000.0))
            gain = float(b.get("gain", 0.0))
            q = float(b.get("q", 1.0))
            enabled_str = "ON" if b.get("enabled", True) else "OFF"
            lines.append(f"Filter {idx}: {enabled_str} {ftype} Fc {freq:.1f} Hz Gain {gain:+.1f} dB Q {q:.2f}")
        else:
            lines.append(f"Filter {idx}: OFF PK Fc 1000.0 Hz Gain +0.0 dB Q 1.00")

    return "\n".join(lines) + "\n"


def format_qudelix_json(
    preset: Dict[str, Any],
    auto_preamp: bool = False,
    pad_to_10: bool = True,
) -> Dict[str, Any]:
    """Generate Qudelix-5K Chrome App JSON preset profile.

    Supports direct import into the Qudelix-5K web/desktop extension.
    """
    preset_name = preset.get("name", "custom")
    description = preset.get("description", "")
    bands = preset.get("bands", [])

    if auto_preamp:
        rec = calculate_recommended_preamp(bands)
        preamp_db = min(float(preset.get("preamp", 0.0)), rec)
    else:
        preamp_db = float(preset.get("preamp", 0.0))

    type_to_q5k = {
        "PK": "PEAK",
        "PEAK": "PEAK",
        "PEAKING": "PEAK",
        "LSQ": "LOW_SHELF",
        "LOW_SHELF": "LOW_SHELF",
        "LOWSHELF": "LOW_SHELF",
        "HSQ": "HIGH_SHELF",
        "HIGH_SHELF": "HIGH_SHELF",
        "HIGHSHELF": "HIGH_SHELF",
    }

    q5k_bands = []
    total_slots = 10 if pad_to_10 else max(len(bands), 10)
    for i in range(total_slots):
        if i < len(bands):
            b = bands[i]
            ftype = type_to_q5k.get(str(b.get("type", "PK")).upper(), "PEAK")
            q5k_bands.append({
                "band": i,
                "enable": 1 if b.get("enabled", True) else 0,
                "type": ftype,
                "freq": round(float(b.get("freq", 1000.0)), 1),
                "gain": round(float(b.get("gain", 0.0)), 1),
                "q": round(float(b.get("q", 1.0)), 2),
            })
        else:
            q5k_bands.append({
                "band": i,
                "enable": 0,
                "type": "PEAK",
                "freq": 1000.0,
                "gain": 0.0,
                "q": 1.0,
            })

    return {
        "profile_name": preset_name,
        "name": preset_name,
        "description": description,
        "target": "Qudelix-5K Bluetooth & USB DAC/Amp",
        "preamp_db": round(preamp_db, 1),
        "preamp": round(preamp_db, 1),
        "eq_mode": "USER",
        "eq_list": q5k_bands,
        "bands": q5k_bands,
    }


def export_qudelix(
    preset: Dict[str, Any],
    output_path: Optional[str | Path] = None,
    as_json: bool = True,
    auto_preamp: bool = False,
) -> Path:
    """Export preset to Qudelix-5K format (JSON or text)."""
    preset_name = preset.get("name", "custom")
    preset_slug = preset_name.replace(" ", "_").replace("-", "_").lower()

    if output_path is None:
        ext = ".json" if as_json else ".txt"
        target = Path(f"{preset_slug}_qudelix{ext}")
    else:
        target = Path(output_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)

    if as_json:
        data = format_qudelix_json(preset, auto_preamp=auto_preamp)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        content = format_qudelix_text(preset, auto_preamp=auto_preamp)
        target.write_text(content, encoding="utf-8")

    return target


def parse_parametric_eq(raw_text: str, default_name: str = "imported_peq") -> Dict[str, Any]:
    """Parse GraphWorks EQ, Equalizer APO, Peace, Squig.link, or CSV parametric EQ configs.

    Extracts preamp and individual biquad filter bands (PK, LSQ, HSQ).
    Raises ValueError if no valid filters or supported structure is found.
    """
    text = raw_text.strip()
    if not text:
        raise ValueError("Cannot parse empty configuration.")

    # Check if it's JSON (e.g. Qudelix JSON or Wavelet JSON)
    if text.startswith("{") and text.endswith("}"):
        return parse_qudelix_profile(text)

    type_map = {
        "PK": "PK",
        "PEAK": "PK",
        "PEAKING": "PK",
        "LS": "LSQ",
        "LSQ": "LSQ",
        "LOW_SHELF": "LSQ",
        "LOWSHELF": "LSQ",
        "HS": "HSQ",
        "HSQ": "HSQ",
        "HIGH_SHELF": "HSQ",
        "HIGHSHELF": "HSQ",
    }

    lines = text.splitlines()
    name = default_name
    description = "Imported parametric EQ configuration"
    preamp = 0.0
    bands = []

    for line in lines:
        raw_line = line.strip()
        if not raw_line:
            continue

        # Comments and metadata
        if raw_line.startswith(("#", "//", ";")):
            comment_body = raw_line.lstrip("#/; ").strip()
            if comment_body.lower().startswith(("preset:", "name:", "profile:")):
                name = comment_body.split(":", 1)[1].strip()
            elif comment_body.lower().startswith("description:"):
                description = comment_body.split(":", 1)[1].strip()
            continue

        # Preamp statements: "Preamp: -3.5 dB" or "Pre-amp: -3.5 dB"
        lower_line = raw_line.lower()
        if lower_line.startswith(("preamp:", "pre-amp:", "preamp ", "pre-amp ")):
            parts = raw_line.split(":", 1)[-1] if ":" in raw_line else raw_line.split(None, 1)[-1]
            cleaned = parts.replace("dB", "").replace("db", "").replace("+", "").strip()
            try:
                preamp = float(cleaned)
            except ValueError:
                pass
            continue

        # Equalizer APO / GraphWorks / Peace line syntax:
        # e.g.: "Filter 1: ON PK Fc 100.0 Hz Gain +3.0 dB Q 1.41"
        # or:   "Filter: ON PK Fc 100 Hz Gain 3.0 Q 1.41"
        if lower_line.startswith("filter"):
            # Strip "Filter" or "Filter <num>:" prefix
            content = raw_line
            if ":" in content:
                content = content.split(":", 1)[1].strip()
            else:
                tokens = content.split()
                if len(tokens) > 1 and tokens[0].lower() == "filter":
                    content = " ".join(tokens[1:])

            tokens = content.split()
            if not tokens:
                continue

            state = "ON"
            if tokens[0].upper() in ("ON", "OFF"):
                state = tokens[0].upper()
                tokens = tokens[1:]

            if not tokens:
                continue

            raw_type = tokens[0].upper()
            ftype = type_map.get(raw_type, "PK")

            # Extract Fc, Gain, Q by looking for keys or position
            freq = None
            gain = None
            q = None

            for i, token in enumerate(tokens):
                t_lower = token.lower()
                if t_lower == "fc" and i + 1 < len(tokens):
                    try:
                        freq = float(tokens[i + 1].lower().replace("hz", ""))
                    except ValueError:
                        pass
                elif t_lower == "gain" and i + 1 < len(tokens):
                    try:
                        gain = float(tokens[i + 1].lower().replace("db", "").replace("+", ""))
                    except ValueError:
                        pass
                elif t_lower == "q" and i + 1 < len(tokens):
                    try:
                        q = float(tokens[i + 1])
                    except ValueError:
                        pass

            if freq is not None and gain is not None:
                if state == "OFF" and gain == 0.0:
                    continue
                bands.append({
                    "index": len(bands) + 1,
                    "type": ftype,
                    "freq": float(freq),
                    "gain": float(gain),
                    "q": float(q if q is not None else 1.0),
                    "enabled": (state == "ON"),
                })
            continue

        # CSV / TSV format: Type, Freq, Gain, Q
        delimiter = "," if "," in raw_line else ("\t" if "\t" in raw_line else None)
        if delimiter:
            parts = [p.strip() for p in raw_line.split(delimiter)]
            # Skip header line (e.g. "type,freq,gain,q")
            if any(h in parts[0].lower() for h in ("type", "filter", "freq", "index")):
                continue
            try:
                # Handle possible formats:
                # [Index, Type, Freq, Gain, Q] or [Type, Freq, Gain, Q] or [Freq, Gain, Q, Type]
                if len(parts) >= 4:
                    if parts[0].isdigit() and len(parts) >= 5:
                        # Index, Type, Freq, Gain, Q
                        c_type = parts[1].upper()
                        c_freq = float(parts[2].lower().replace("hz", ""))
                        c_gain = float(parts[3].lower().replace("db", "").replace("+", ""))
                        c_q = float(parts[4])
                    else:
                        c_type = parts[0].upper()
                        c_freq = float(parts[1].lower().replace("hz", ""))
                        c_gain = float(parts[2].lower().replace("db", "").replace("+", ""))
                        c_q = float(parts[3])

                    ftype = type_map.get(c_type, "PK")
                    bands.append({
                        "index": len(bands) + 1,
                        "type": ftype,
                        "freq": c_freq,
                        "gain": c_gain,
                        "q": c_q,
                        "enabled": True,
                    })
            except (ValueError, IndexError):
                continue

    if not bands:
        raise ValueError("No valid parametric EQ filters found in input.")

    return {
        "name": name,
        "description": description,
        "preamp": preamp,
        "bands": bands,
    }


def parse_qudelix_profile(raw_input: str | Dict[str, Any]) -> Dict[str, Any]:
    """Parse a Qudelix-5K profile (JSON string, parsed dict, or text) into standard dac-peq preset format."""
    if isinstance(raw_input, dict):
        data = raw_input
    else:
        text = raw_input.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
            except Exception:
                data = None
        else:
            data = None

    if data is not None:
        name = data.get("profile_name") or data.get("name") or "qudelix_import"
        preamp = float(data.get("preamp_db", data.get("preamp", 0.0)))
        raw_bands = data.get("eq_list") or data.get("bands") or []

        q5k_to_type = {
            "PEAK": "PK",
            "PEAKING": "PK",
            "PK": "PK",
            "LOW_SHELF": "LSQ",
            "LOWSHELF": "LSQ",
            "LSQ": "LSQ",
            "HIGH_SHELF": "HSQ",
            "HIGHSHELF": "HSQ",
            "HSQ": "HSQ",
        }

        parsed_bands = []
        for i, b in enumerate(raw_bands):
            enabled = bool(b.get("enable", b.get("enabled", 1)))
            gain = float(b.get("gain", 0.0))
            if not enabled and gain == 0.0:
                continue
            ftype = q5k_to_type.get(str(b.get("type", "PEAK")).upper(), "PK")
            parsed_bands.append({
                "index": i + 1,
                "type": ftype,
                "freq": float(b.get("freq", 1000.0)),
                "gain": gain,
                "q": float(b.get("q", 1.0)),
                "enabled": enabled,
            })

        return {
            "name": name,
            "description": data.get("description", "Imported from Qudelix-5K"),
            "preamp": preamp,
            "bands": parsed_bands,
        }

    lines = raw_input.strip().splitlines()
    name = "qudelix_import"
    preamp = 0.0
    bands = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if "Profile:" in line:
                name = line.split("Profile:", 1)[1].strip()
            continue
        if line.lower().startswith("preamp:"):
            parts = line.split(":", 1)[1].replace("dB", "").strip()
            try:
                preamp = float(parts)
            except ValueError:
                pass
            continue
        if line.lower().startswith("filter"):
            try:
                tokens = line.split()
                state = tokens[2].upper() if len(tokens) > 2 else "ON"
                ftype = tokens[3].upper() if len(tokens) > 3 else "PK"
                fc_idx = tokens.index("Fc") if "Fc" in tokens else -1
                gain_idx = tokens.index("Gain") if "Gain" in tokens else -1
                q_idx = tokens.index("Q") if "Q" in tokens else -1

                freq = float(tokens[fc_idx + 1]) if fc_idx != -1 and fc_idx + 1 < len(tokens) else 1000.0
                gain = float(tokens[gain_idx + 1].replace("+", "")) if gain_idx != -1 and gain_idx + 1 < len(tokens) else 0.0
                q = float(tokens[q_idx + 1]) if q_idx != -1 and q_idx + 1 < len(tokens) else 1.0

                if state == "OFF" and gain == 0.0:
                    continue

                bands.append({
                    "index": len(bands) + 1,
                    "type": ftype,
                    "freq": freq,
                    "gain": gain,
                    "q": q,
                    "enabled": (state == "ON"),
                })
            except Exception:
                continue

    return {
        "name": name,
        "description": "Imported from Qudelix-5K text format",
        "preamp": preamp,
        "bands": bands,
    }


def encode_preset_to_url_params(
    preset: Dict[str, Any],
    bands: List[Dict[str, Any]] | None = None,
    hw_bands: int = 5,
) -> str:
    """Encode a PEQ preset into a deterministic URL query string (compatible with Web Share links)."""
    from urllib.parse import urlencode

    active_bands = bands if bands is not None else preset.get("bands", [])
    name = str(preset.get("name", "Custom PEQ")).strip() or "Custom PEQ"
    preamp = round(float(preset.get("preamp", 0.0)), 1)
    hw = int(hw_bands or len(active_bands) or 5)

    type_map = {
        "PK": "PK", "PEAK": "PK", "PEAKING": "PK",
        "LSQ": "LSQ", "LOW_SHELF": "LSQ", "LOWSHELF": "LSQ", "LS": "LSQ",
        "HSQ": "HSQ", "HIGH_SHELF": "HSQ", "HIGHSHELF": "HSQ", "HS": "HSQ",
    }

    params: List[tuple[str, str]] = [
        ("name", name),
        ("preamp", f"{preamp:.1f}"),
        ("hw", str(hw)),
    ]

    for i, b in enumerate(active_bands):
        ftype = type_map.get(str(b.get("type", "PK")).upper(), "PK")
        freq = round(max(20.0, min(20000.0, float(b.get("freq", 1000.0)))), 1)
        gain = round(max(-18.0, min(18.0, float(b.get("gain", 0.0)))), 2)
        q = round(max(0.1, min(10.0, float(b.get("q", 1.0)))), 2)
        freq_str = str(int(freq)) if freq == int(freq) else f"{freq:.1f}"
        params.append((f"b{i + 1}", f"{ftype},{freq_str},{gain:.1f},{q:.2f}"))

    return urlencode(params)


def decode_preset_from_url_params(
    query_or_url: str,
    default_name: str = "Shared PEQ Profile",
) -> Dict[str, Any]:
    """Decode a PEQ preset from a dac-peq-manager or squig.link share URL / query string."""
    from urllib.parse import parse_qs, urlparse

    raw = (query_or_url or "").strip()
    if not raw:
        raise ValueError("Empty URL or query string.")

    if "?" in raw:
        parsed_url = urlparse(raw)
        query_str = parsed_url.query or raw.split("?", 1)[1]
    elif raw.startswith("http://") or raw.startswith("https://"):
        parsed_url = urlparse(raw)
        query_str = parsed_url.query
    else:
        query_str = raw.lstrip("?#")

    if not query_str:
        raise ValueError("No query parameters found in URL.")

    qs = parse_qs(query_str, keep_blank_values=False)

    name_vals = qs.get("name") or qs.get("share") or qs.get("preset")
    name = name_vals[0].strip() if name_vals and name_vals[0].strip() else default_name
    slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_") or "shared_peq"

    preamp = 0.0
    if "preamp" in qs and qs["preamp"]:
        try:
            preamp = round(max(-18.0, min(18.0, float(qs["preamp"][0]))), 1)
        except ValueError:
            preamp = 0.0

    hw_bands = 5
    if "hw" in qs and qs["hw"]:
        try:
            cand_hw = int(qs["hw"][0])
            if cand_hw in (5, 8, 9, 10):
                hw_bands = cand_hw
        except ValueError:
            pass

    type_map = {
        "PK": "PK", "PEAK": "PK", "PEAKING": "PK",
        "LSQ": "LSQ", "LOW_SHELF": "LSQ", "LOWSHELF": "LSQ", "LS": "LSQ", "LSC": "LSQ",
        "HSQ": "HSQ", "HIGH_SHELF": "HSQ", "HIGHSHELF": "HSQ", "HS": "HSQ", "HSC": "HSQ",
    }

    bands: List[Dict[str, Any]] = []

    # Check indexed band keys b1..b20 or f1..f20
    for idx in range(1, 21):
        key = f"b{idx}" if f"b{idx}" in qs else (f"f{idx}" if f"f{idx}" in qs else None)
        if not key or not qs[key]:
            continue
        tokens = [t.strip() for t in qs[key][0].split(",") if t.strip()]
        if len(tokens) < 3:
            continue
        try:
            if tokens[0].upper() in type_map:
                ftype = type_map[tokens[0].upper()]
                freq = float(tokens[1])
                gain = float(tokens[2])
                q = float(tokens[3]) if len(tokens) >= 4 else 1.0
            else:
                # Format: freq,gain,q[,type]
                freq = float(tokens[0])
                gain = float(tokens[1])
                q = float(tokens[2])
                ftype = type_map.get(tokens[3].upper(), "PK") if len(tokens) >= 4 else "PK"

            bands.append({
                "index": len(bands) + 1,
                "type": ftype,
                "freq": round(max(20.0, min(20000.0, freq)), 1),
                "gain": round(max(-18.0, min(18.0, gain)), 2),
                "q": round(max(0.1, min(10.0, q)), 2),
                "enabled": True,
            })
        except ValueError:
            continue

    # Check semicolon-delimited `eq=` or `filters=` parameter
    if not bands:
        eq_raw = (qs.get("eq") or qs.get("filters") or [None])[0]
        if eq_raw:
            for item in eq_raw.split(";"):
                tokens = [t.strip() for t in item.split(",") if t.strip()]
                if len(tokens) < 3:
                    continue
                try:
                    if tokens[0].upper() in type_map:
                        ftype = type_map[tokens[0].upper()]
                        freq = float(tokens[1])
                        gain = float(tokens[2])
                        q = float(tokens[3]) if len(tokens) >= 4 else 1.0
                    else:
                        freq = float(tokens[0])
                        gain = float(tokens[1])
                        q = float(tokens[2])
                        ftype = type_map.get(tokens[3].upper(), "PK") if len(tokens) >= 4 else "PK"
                    bands.append({
                        "index": len(bands) + 1,
                        "type": ftype,
                        "freq": round(max(20.0, min(20000.0, freq)), 1),
                        "gain": round(max(-18.0, min(18.0, gain)), 2),
                        "q": round(max(0.1, min(10.0, q)), 2),
                        "enabled": True,
                    })
                except ValueError:
                    continue

    if not bands:
        raise ValueError("No valid PEQ bands found in URL parameters.")

    return {
        "name": name,
        "slug": slug,
        "description": f"Shared via URL ({len(bands)} bands)",
        "preamp": preamp,
        "hw_bands": hw_bands,
        "bands": bands,
    }

