"""Documented F/U address arithmetic, A650 edition 3, appendix A.4.3.

An address does not establish a parameter's existence, scale or write permission.
"""
import re


def parameter_addresses(code: str) -> tuple[int, int | None]:
    """Return RAM and optional EEPROM addresses; H groups remain unspecified."""
    match = re.fullmatch(r"([FU])([0-9]{2})\.([0-9]{2})", code)
    if match is None:
        raise ValueError(f"unsupported parameter code: {code}")
    family, group, index = match.groups()
    group, index = int(group), int(index)
    if family == "F" and group <= 31:
        address = (group << 8) | index
        return address, address | 0x8000
    if family == "U" and group <= 1:
        return ((0x30 + group) << 8) | index, None
    raise ValueError(f"undocumented parameter group: {code}")
