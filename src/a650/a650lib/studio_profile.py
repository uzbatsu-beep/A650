"""Offline reader for OniDriveStudio's INI-based .ods configuration.

Reconstructed from the supplied EXE (VERSIONINFO 1.2.7.0). This never opens
hardware and does not convert stored integers into engineering or wire values.
Real-file interoperability still needs validation; see docs/ODS_FORMAT.md.
"""
from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass
from pathlib import Path
import re


class StudioProfileError(ValueError):
    pass


@dataclass
class StudioProfile:
    model: str
    general: dict[str, str]
    parameter_set: dict[str, int]
    parameter_read: dict[str, int]
    checked: frozenset[str]


_MODELS = {"ПЧ ONI A650", "ПЧ ONI A650M"}
_CODE = re.compile(r"[FHU][0-9]{2}\.[0-9]{2}")
_INTEGER = re.compile(r"-?[0-9]+")


def read_studio_profile(path: str | Path, *, expected_model: str | None = None) -> StudioProfile:
    """Inspect a profile without applying its values or connection settings."""
    with Path(path).open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise StudioProfileError("profile exceeds the 2 MiB inspection limit")
    if data.startswith(b"PK"):
        raise StudioProfileError("ZIP/OpenDocument is not an OniDriveStudio INI profile")
    parser = ConfigParser(interpolation=None, delimiters=("=",), strict=True)
    parser.optionxform = str
    try:
        parser.read_string(data.decode("utf-8-sig"))
    except (UnicodeError, ConfigError) as exc:
        raise StudioProfileError("invalid UTF-8 INI profile") from exc
    if parser.defaults():
        raise StudioProfileError("inherited DEFAULT values are unsupported")
    if not parser.has_section("General"):
        raise StudioProfileError("missing General section")
    general = dict(parser["General"])
    model = general.get("Model", "")
    if model not in _MODELS:
        raise StudioProfileError("missing or unsupported equipment model")
    if expected_model is not None and model != expected_model:
        raise StudioProfileError("equipment model mismatch")

    def parameters(section):
        result = {}
        if not parser.has_section(section):
            return result
        for code, text in parser[section].items():
            if not _CODE.fullmatch(code) or not _INTEGER.fullmatch(text):
                raise StudioProfileError(f"invalid parameter entry in {section}")
            value = int(text)
            if not -(2**31) <= value < 2**31:
                raise StudioProfileError("stored value outside signed 32-bit range")
            result[code] = value
        return result

    selected = parameters("Check Parameter")
    if any(value not in (0, 1) for value in selected.values()):
        raise StudioProfileError("invalid selection flag")
    return StudioProfile(model, general, parameters("Parameter Set"),
                         parameters("Parameter Read"),
                         frozenset(code for code, value in selected.items() if value))
