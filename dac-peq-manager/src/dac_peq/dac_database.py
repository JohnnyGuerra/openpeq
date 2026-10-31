"""Hardware DAC Directory & Compatibility Database for dac-peq-manager.

Catalogues portable USB-C DAC dongles, internal chipsets, max resolutions,
hardware flashability (KTMicro KT02H20 / WalkPlay vs. Conexant CX31993 vs. CS43131),
and recommended host vs. hardware DSP workflows.

--------------------------------------------------------------------------------
ACKNOWLEDGMENTS & HARDWARE ARCHITECTURE CITATIONS:
Hardware profiles, USB VID/PID mappings, and chipset architectures compile public
datasheets, Linux kernel USB audio device quirks, and community research:
  - KTMicro KT02H20: Reverse-engineered by gxcreator, jeromeof, and Ircama.
  - Conexant CX31993: Synaptics CX31993 UAC2 fixed-function audio controller.
  - Cirrus Logic CS43131: MasterHIFI 32-bit/384kHz high-dynamic-range DAC.
  - VIA Labs VL102/VL103: USB PD 100W/60W charging controller in 2-in-1 splitters.
--------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DACInfo:
    """Detailed profile of a USB-C Audio DAC dongle."""
    id: str
    name: str
    brand: str
    chipset: str
    architecture: str
    dac_type: str  # 'hardware_dsp', 'fixed_mask_rom', 'host_dsp_only'
    flashable: bool
    vid: Optional[int] = None
    pid: Optional[int] = None
    vid_hex: Optional[str] = None
    pid_hex: Optional[str] = None
    resolution: str = "24-bit / 96 kHz"
    output_power: str = "30mW @ 32Ω"
    outputs: List[str] = field(default_factory=list)
    trrs_mic: bool = True
    recommendation: str = ""
    quirks: List[str] = field(default_factory=list)
    hardware_bands: Optional[int] = None

    @property
    def is_hardware_flashable(self) -> bool:
        return self.flashable and self.architecture in ("ktmicro_dsp", "moondrop_dsp", "walkplay_dsp")

    @property
    def is_fixed_mask_rom(self) -> bool:
        return self.dac_type == "fixed_mask_rom" or "mask_rom_safety_lock" in self.quirks

    @property
    def eq_capabilities(self) -> Dict[str, Any]:
        """Return declarative hardware EQ capabilities (`eqcaps`) for this device architecture."""
        return get_architecture_eq_capabilities(
            self.architecture,
            hardware_bands=self.hardware_bands,
            vid=self.vid,
            pid=self.pid,
            quirks=self.quirks,
        )


def get_architecture_eq_capabilities(
    architecture: str,
    hardware_bands: Optional[int] = None,
    vid: Optional[int] = None,
    pid: Optional[int] = None,
    quirks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return modernGraphTool / devicePEQ style declarative EQ capabilities for a DSP architecture."""
    arch = (architecture or "").lower()
    quirk_list = quirks or []

    if arch == "ktmicro_dsp":
        # Strict GEMINI.md Rule 1: Kiwi Ears Allegro Mini (0x31B2:0x0111) blocks 0x11 and 0x66 (noPregain)
        is_ja11 = (vid == 0x2972 and pid == 0x0102)
        supports_preamp = bool(is_ja11 and "noPregain" not in quirk_list)
        blocked_regs = [] if is_ja11 else ["0x11", "0x66"]
        return {
            "max_bands": hardware_bands or 5,
            "gain_range_db": [-12.0, 12.0],
            "gain_step_db": 0.1,
            "q_range": [0.1, 10.0],
            "q_step": 0.05,
            "supported_filter_types": ["PK", "LSQ", "HSQ"],
            "supports_hardware_preamp": supports_preamp,
            "no_pregain": not supports_preamp,
            "blocked_registers": blocked_regs,
        }

    if arch == "walkplay_dsp":
        return {
            "max_bands": hardware_bands or 8,
            "gain_range_db": [-12.0, 12.0],
            "gain_step_db": 0.1,
            "q_range": [0.1, 10.0],
            "q_step": 0.05,
            "supported_filter_types": ["PK", "LSQ", "HSQ"],
            "supports_hardware_preamp": True,
            "no_pregain": False,
            "blocked_registers": [],
        }

    if arch == "moondrop_dsp":
        return {
            "max_bands": hardware_bands or 9,
            "gain_range_db": [-12.0, 12.0],
            "gain_step_db": 0.1,
            "q_range": [0.1, 10.0],
            "q_step": 0.05,
            "supported_filter_types": ["PK", "LSQ", "HSQ"],
            "supports_hardware_preamp": True,
            "no_pregain": False,
            "blocked_registers": [],
        }

    # Host DSP (PipeWire / EqualizerAPO / Wavelet / Fixed Mask ROM)
    return {
        "max_bands": hardware_bands or 10,
        "gain_range_db": [-18.0, 18.0],
        "gain_step_db": 0.1,
        "q_range": [0.1, 10.0],
        "q_step": 0.01,
        "supported_filter_types": ["PK", "LSQ", "HSQ"],
        "supports_hardware_preamp": True,
        "no_pregain": False,
        "blocked_registers": ["ALL_HID_WRITES"] if arch == "conexant_fixed" else [],
    }


class DACDatabase:
    """Catalog of known USB DAC dongles and DSP architectures."""

    def __init__(self, data_file: Optional[Path] = None):
        if data_file is None:
            cur = Path(__file__).resolve().parent
            data_file = cur / "data" / "dacs.json"
        self.data_file = data_file
        self._dacs: List[DACInfo] = []
        self._load()

    def _load(self) -> None:
        if not self.data_file.exists():
            return
        with open(self.data_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
            self._dacs = [DACInfo(**item) for item in raw]

    def all(self) -> List[DACInfo]:
        """Return all catalogued DAC devices."""
        return list(self._dacs)

    def lookup(
        self,
        vid: Optional[int],
        pid: Optional[int],
        product_name: Optional[str] = None,
    ) -> Optional[DACInfo]:
        """Lookup DAC with multi-pass matching, disambiguating by product name when provided."""
        if vid is None:
            return None

        clean_prod = product_name.strip().lower() if product_name and product_name.strip() else None

        # 1. If product_name is provided and non-empty:
        # Check for entry with d.vid == vid and d.pid == pid and (d.name.lower() in product_name.lower() or product_name.lower() in d.name.lower())
        if clean_prod is not None:
            for d in self._dacs:
                if d.vid == vid and d.pid == pid:
                    d_name = d.name.lower()
                    if d_name in clean_prod or clean_prod in d_name:
                        return d

        # 2. Exact match: d.vid == vid and d.pid == pid and d.pid is not None
        if pid is not None:
            for d in self._dacs:
                if d.vid == vid and d.pid == pid and d.pid is not None:
                    return d

        # 3. If product_name provided: entry where d.vid == vid and (d.name.lower() in product_name.lower() or product_name.lower() in d.name.lower())
        if clean_prod is not None:
            for d in self._dacs:
                if d.vid == vid:
                    d_name = d.name.lower()
                    if d_name in clean_prod or clean_prod in d_name:
                        return d

        # 4. Fallback wildcard match: entry where d.vid == vid and d.pid is None
        for d in self._dacs:
            if d.vid == vid and d.pid is None:
                return d

        return None

    def lookup_by_string(self, text: str) -> Optional[DACInfo]:
        """Lookup DAC by matching product name or chipset string."""
        if not text or not text.strip():
            return None
        text_lower = text.strip().lower()
        for d in self._dacs:
            if d.name.lower() in text_lower or text_lower in d.name.lower():
                return d
            if d.chipset.lower() in text_lower:
                return d
        return None

    def search(self, query: str, flashable_only: bool = False) -> List[DACInfo]:
        """Search catalogued DACs by name, brand, chipset, architecture, or features."""
        words = query.lower().split()
        results: List[DACInfo] = []
        for d in self._dacs:
            if flashable_only and not d.flashable:
                continue
            haystack = (
                f"{d.id} {d.name} {d.brand} {d.chipset} {d.architecture} "
                f"{d.recommendation} {' '.join(d.quirks)} {' '.join(d.outputs)} "
                f"{d.vid_hex or ''} {d.pid_hex or ''}"
            ).lower()
            if all(w in haystack for w in words):
                results.append(d)
        return results

    def list_flashable(self) -> List[DACInfo]:
        """Return all hardware-flashable KTMicro / WalkPlay DSP devices."""
        return [d for d in self._dacs if d.flashable]

    def list_mask_rom(self) -> List[DACInfo]:
        """Return all fixed mask ROM devices (Conexant CX31993, etc.)."""
        return [d for d in self._dacs if d.is_fixed_mask_rom]
