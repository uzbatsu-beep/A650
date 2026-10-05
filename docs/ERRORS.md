# Fault and Warning Codes

## Known fault codes from U01.00

| Code | Name |
|---|---|
| Err14 | Module overheat |
| Err15 | EEPROM read/write failure |
| Err16 | Motor auto-tuning cancelled |
| Err17 | Motor auto-tuning error |
| Err18 | Communication timeout |
| Err19 | PID feedback loss |
| Err20 | Continuous operation time reached |
| Err21 | Parameter upload error |
| Err22 | Parameter download error |
| Err23 | Braking block error |
| Err24 | Module temperature break detection |
| Err25 | Load becomes zero |
| Err26 | Ripple current limit error |
| Err27 | Soft-start relay disconnected |
| Err28 | Software version compatibility error |
| Err29 | Reserved |
| Err30 | Instantaneous overvoltage |
| Err39 | Motor PTC temperature too high |
| Err40 | Tuning operation timeout |

## Modbus exception codes

| Code | Meaning |
|---|---|
| 0x01 | Illegal function |
| 0x02 | Illegal data address |
| 0x03 | Illegal data value |
| 0x04 | Operation not executed |

## TODO

- full warning code list;
- mapping from numeric fault register 0x2102 to Err names;
- whether fault reset is via register 0x2000 or another register.