# ONI A650 Known Modbus Registers

Status: partial. Verified against manual examples only.

| Address | Hex | Name | Access | Type | Scale | Unit | Source | Confidence |
|---|---|---|---|---|---|---|---|---|
| 0x2000 | 8192 | Command/control word | RW | uint16 | raw | - | Manual example | Medium |
| 0x2001 | 8193 | Frequency setpoint | RW | uint16 | 0.01 | Hz | Manual example | High |
| 0x2005 | 8197 | AO output | R/W? | uint16 | 0.1 | % | Manual appendix | Medium |
| 0x2100 | 8448 | Drive state/function | R | enum16 | raw | - | Manual appendix | High |
| 0x2101 | 8449 | Status bits | R | bitfield16 | raw | - | Manual appendix | High |
| 0x2102 | 8450 | Current fault | R | uint16 | raw | Err code | Manual appendix | High |
| 0x2103 | 8451 | Current warning | R | uint16 | raw | Warn code | Manual appendix | High |
| 0x3000 | 12288 | U00.00 output frequency | R | uint16 | 0.01 | Hz | Manual example | High |