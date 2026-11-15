"""Synthetic fixtures based on disassembly; not exports from the vendor app."""
import pytest

from a650.a650lib.studio_profile import read_studio_profile, StudioProfileError


BASE = """; Synthetic reconstruction, not a vendor-exported file
[General]
Model = ПЧ ONI A650
Address = 1
Port = COM17
Baud = 3
[Parameter Set]
F13.01 = 500
[Parameter Read]
F13.01 = 450
[Check Parameter]
F13.01 = 1
"""


def test_bom_and_separate_set_read_values(tmp_path):
    path = tmp_path / "profile.ods"
    path.write_bytes(BASE.encode("utf-8-sig"))
    profile = read_studio_profile(path, expected_model="ПЧ ONI A650")
    assert profile.parameter_set == {"F13.01": 500}
    assert profile.parameter_read == {"F13.01": 450}
    assert profile.checked == {"F13.01"}
    # Baud is a persisted control state, not necessarily the literal speed.
    assert profile.general["Baud"] == "3"


def test_rejects_different_model(tmp_path):
    path = tmp_path / "profile.ods"
    path.write_text(BASE, encoding="utf-8")
    with pytest.raises(StudioProfileError, match="mismatch"):
        read_studio_profile(path, expected_model="ПЧ ONI A650M")


@pytest.mark.parametrize("content", [
    b"PK\x03\x04", b"\xff\xff", b"[General]\nPort=COM1",
    BASE.replace("F13.01 = 500", "F13.01 = 50.0").encode(),
    BASE.replace("F13.01 = 500", "F13.01 = 500\nF13.01 = 200").encode(),
    BASE.replace("F13.01 = 1", "F13.01 = 2").encode(),
    BASE.replace("F13.01 = 500", "F13.01 = 2147483648").encode(),
    ("[DEFAULT]\nF00.00=1234\n" + BASE).encode(),
])
def test_rejects_ambiguous_or_invalid_input(tmp_path, content):
    path = tmp_path / "invalid.ods"
    path.write_bytes(content)
    with pytest.raises(StudioProfileError):
        read_studio_profile(path)


def test_omitted_parameters_are_not_filled_with_zero(tmp_path):
    path = tmp_path / "minimal.ods"
    path.write_text("[General]\nModel=ПЧ ONI A650", encoding="utf-8")
    profile = read_studio_profile(path)
    assert profile.parameter_set == {}
    assert profile.parameter_read == {}
    assert not profile.checked
