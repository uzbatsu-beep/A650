# Modbus RTU Protocol for ONI A650

## 1. Physical layer

- Interface: RS-485
- Mode: asynchronous half-duplex
- Topology: one master / multiple slaves
- Recommended cable: shielded twisted pair
- Cable shielding: grounded near drive side
- Digital signal cable length: preferably not more than 20 m
- Power and signal cables should not be routed together

## 2. Default communication settings

From manual:

- Default baud rate: 9600
- Default slave address: 1
- Data format: there is a discrepancy in the manual:
  - Appendix A states default terminal format: 1-8-N-1
  - Parameter F15.01 default value 0 is described as 1-8-N-2

Action required: verify on real device.

## 3. Communication parameters

| Parameter | Name | Values |
|---|---|---|
| F15.00 | Baud rate | 0: 4800, 1: 9600, 2: 19200, 3: 38400, 4: 57600, 5: 115200 |
| F15.01 | Data format | 0: 1-8-N-2, 1: 1-8-E-1, 2: 1-8-O-1, 3: 1-8-N-1 |
| F15.02 | Local address | 1..247, 0 is broadcast |

## 4. Modbus frame format

Typical RTU frame:

| Field | Size |
|---|---|
| Start silence | T1-T2-T3-T4 |
| Slave address | 8 bit |
| Function code | 8 bit |
| Data | n × 8 bit |
| CRC16 | 16 bit |
| Stop silence | T1-T2-T3-T4 |

CRC is calculated over address, function code and data.  
Start and stop bits are not included.  
CRC low byte is transmitted first, high byte second.

## 5. Supported function codes

| Code | Meaning |
|---|---|
| 0x03 | Read parameters and drive status |
| 0x06 | Write single function code or control parameter |
| 0x08 | Diagnostic / link test |

Error response uses function code + 0x80.

## 6. Exception codes

| Code | Meaning |
|---|---|
| 0x01 | Illegal function |
| 0x02 | Illegal data address |
| 0x03 | Illegal data value |
| 0x04 | Operation not executed |

Note: manual also mentions detailed error code 0x11 meaning read-only parameter.  
Need clarification how this detailed code is exposed.

## 7. Known register areas

| Address | Name | Access | Notes |
|---|---|---|---|
| 0x2000 | Command / control word | RW | Examples: 0x0001 forward start, 0x0005 stop with deceleration |
| 0x2001 | Frequency setpoint | RW | 3000 = 30.00 Hz |
| 0x2005 | AO output value | ? | Range 0..1000, 1000 = 100.0% |
| 0x2100 | State / function | R | 0x0000 parameter setting, 0x0001 start slave, 0x0002 jog, 0x0003 learning, 0x0004 park slave, 0x0005 park jog, 0x0006 fault |
| 0x2101 | Status bits | R | Bit fields for sign, direction, command source, password, function group |
| 0x2102 | Current fault type | R | Fault code |
| 0x2103 | Current warning type | R | Warning code |
| 0x3000 | U00.00 output frequency | R | 5000 = 50.00 Hz |

## 8. Scaling

Known:

- Frequency registers appear to use 0.01 Hz resolution:
  - 5000 = 50.00 Hz
  - 3000 = 30.00 Hz
- AO register 0x2005:
  - 0..1000
  - 1000 corresponds to 100.0%
- PID display values:
  - PID setting = PID setting percent × F13.03
  - PID feedback = PID feedback percent × F13.03

## 9. Timing

Manual mentions RTU silence intervals T1-T2-T3-T4.  
Exact character times are not fully specified in the provided excerpt.

Default assumption:

- Use standard Modbus RTU inter-frame silence: 3.5 character times.
- Make configurable.

## 10. Unknowns / TODO

- Full parameter-to-register mapping.
- Whether 0x03 is used for both input and holding registers.
- Exact command word bit definition for 0x2000.
- Reverse start command value.
- Jog command value.
- Fault reset command value.
- How to read/write named parameters like F01.01, F13.02.
- Whether broadcast address 0 is safely supported for writes.
