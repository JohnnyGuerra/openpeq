"""Unit tests for the Hardware DAC Directory & Compatibility Database."""

from pathlib import Path
from typer.testing import CliRunner

from dac_peq.cli import app
from dac_peq.dac_database import DACDatabase, DACInfo

runner = CliRunner()


def test_dac_database_all():
    db = DACDatabase()
    dacs = db.all()
    assert len(dacs) >= 15
    assert any(d.id == "allegro_mini" for d in dacs)
    assert any(d.id == "jcally_jm6_pro" for d in dacs)
    assert any(d.id == "cablecreation_2in1" for d in dacs)


def test_dac_database_lookup():
    db = DACDatabase()

    # Kiwi Ears Allegro Mini (0x31B2:0x0111)
    allegro = db.lookup(0x31B2, 0x0111)
    assert allegro is not None
    assert allegro.name == "Kiwi Ears Allegro Mini"
    assert allegro.flashable is True
    assert allegro.is_hardware_flashable is True
    assert allegro.is_fixed_mask_rom is False

    # JCALLY JM6 Pro (Conexant CX31993, 0x0572:0x1B08)
    jm6 = db.lookup(0x0572, 0x1B08)
    assert jm6 is not None
    assert "CX31993" in jm6.chipset
    assert jm6.flashable is False
    assert jm6.is_fixed_mask_rom is True

    # None lookups
    assert db.lookup(None, None) is None
    assert db.lookup(0xFFFF, 0xFFFF) is None

    # Shared 0x31B2:0x0111 disambiguation via product_name
    allegro_named = db.lookup(0x31B2, 0x0111, product_name="Kiwi Ears Allegro Mini")
    assert allegro_named is not None
    assert allegro_named.id == "allegro_mini"

    jm12_named = db.lookup(0x31B2, 0x0111, product_name="JCALLY JM12")
    assert jm12_named is not None
    assert jm12_named.id == "jcally_jm12"
    assert jm12_named.name == "JCALLY JM12"


def test_dac_database_lookup_by_string():
    db = DACDatabase()
    assert db.lookup_by_string("") is None
    assert db.lookup_by_string("   ") is None
    assert db.lookup_by_string(None) is None

    match = db.lookup_by_string("CableCreation")
    assert match is not None
    assert match.id == "cablecreation_2in1"
    assert match.architecture == "generic_uac1_pd"
    assert "100W" in match.name


def test_dac_database_search():
    db = DACDatabase()
    res = db.search("CS43131")
    assert len(res) >= 1
    assert any("CS43131" in d.chipset for d in res)

    # Flashable filter
    flashable = db.search("KTMicro", flashable_only=True)
    assert len(flashable) >= 1
    assert all(d.flashable for d in flashable)


def test_dac_database_categories():
    db = DACDatabase()
    flashable = db.list_flashable()
    assert len(flashable) >= 4
    for d in flashable:
        assert d.flashable is True

    mask_rom = db.list_mask_rom()
    assert len(mask_rom) >= 1
    for d in mask_rom:
        assert d.is_fixed_mask_rom is True


def test_cli_dacs_list():
    res = runner.invoke(app, ["dacs", "list"])
    assert res.exit_code == 0
    assert "USB DAC Hardware Compatibility Database" in res.output
    assert "Allegro" in res.output
    assert "JM6" in res.output
    assert "Cable" in res.output


def test_cli_dacs_list_flashable():
    res = runner.invoke(app, ["dacs", "list", "--flashable"])
    assert res.exit_code == 0
    assert "Hardware Flashable DACs" in res.output
    assert "Allegro" in res.output
    assert "CableCreation" not in res.output


def test_cli_dacs_search():
    res = runner.invoke(app, ["dacs", "search", "allegro"])
    assert res.exit_code == 0
    assert "allegro_mini" in res.output
    assert "Allegro" in res.output

    res_split = runner.invoke(app, ["dacs", "search", "splitter"])
    assert res_split.exit_code == 0
    assert "CableCreation" in res_split.output


def test_cli_dacs_info():
    res = runner.invoke(app, ["dacs", "info", "allegro_mini"])
    assert res.exit_code == 0
    assert "Kiwi Ears Allegro Mini" in res.output
    assert "0x31B2:0x0111" in res.output
    assert "Supported (5-Band Hardware Biquad NVRAM)" in res.output

    res_cc = runner.invoke(app, ["dacs", "info", "cablecreation_2in1"])
    assert res_cc.exit_code == 0
    assert "CableCreation" in res_cc.output
    assert "100W" in res_cc.output

    res_bad = runner.invoke(app, ["dacs", "info", "nonexistent_dac_12345"])
    assert res_bad.exit_code != 0


def test_dac_eq_capabilities_schema():
    """Verify declarative eq_capabilities (eqcaps) and GEMINI.md volume-lockout safety rules."""
    db = DACDatabase()

    # Allegro Mini (0x31B2:0x0111) -> 5 bands, no_pregain=True, blocks 0x11 and 0x66
    allegro = db.lookup(0x31B2, 0x0111)
    assert allegro is not None
    caps_allegro = allegro.eq_capabilities
    assert caps_allegro["max_bands"] == 5
    assert caps_allegro["no_pregain"] is True
    assert caps_allegro["supports_hardware_preamp"] is False
    assert "0x11" in caps_allegro["blocked_registers"]
    assert "0x66" in caps_allegro["blocked_registers"]

    # FiiO JA11 (0x2972:0x0102) -> 5 bands, supports hardware preamp
    ja11 = db.lookup(0x2972, 0x0102)
    assert ja11 is not None
    caps_ja11 = ja11.eq_capabilities
    assert caps_ja11["max_bands"] == 5
    assert caps_ja11["supports_hardware_preamp"] is True
    assert caps_ja11["no_pregain"] is False

    # CrinEar Protocol Micro (0x3302:0xC20F) -> 8 bands WalkPlay
    micro = db.lookup(0x3302, 0xC20F)
    assert micro is not None
    assert micro.eq_capabilities["max_bands"] == 8

    # Moondrop FreeDSP (0x31B2:0x0112) -> 9 bands
    moondrop = db.lookup(0x31B2, 0x0112)
    assert moondrop is not None
    assert moondrop.eq_capabilities["max_bands"] == 9

