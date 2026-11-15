import pytest

from a650.a650lib.addresses import parameter_addresses


@pytest.mark.parametrize("code,expected", [
    ("F01.02", (0x0102, 0x8102)),  # explicit EEPROM example in A.4.3
    ("F13.01", (0x0D01, 0x8D01)),
    ("F15.02", (0x0F02, 0x8F02)),
    ("F31.99", (0x1F63, 0x9F63)),
    ("U00.00", (0x3000, None)),
    ("U01.12", (0x310C, None)),
])
def test_decimal_parameter_numbers(code, expected):
    assert parameter_addresses(code) == expected


@pytest.mark.parametrize("code", ["H00.13", "F32.00", "U02.00", "F01.100", "F1.02", "F01.-1"])
def test_unsupported_address_is_not_guessed(code):
    with pytest.raises(ValueError):
        parameter_addresses(code)
