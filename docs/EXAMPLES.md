# Protocol Examples — ONI A650 Modbus RTU

All examples use slave address `0x01`. CRC16 (Modbus RTU, polynomial 0xA001, low byte first)
is verified for every frame below. Machine-readable copies: `data/frames/*.json`.

Verification legend:
- **manual** — frame bytes taken verbatim from the manual and CRC-checked ✅
- **computed** — semantics from the manual, frame bytes reconstructed with correct CRC
  (the original EXAMPLES.md was truncated mid-frame; these are rebuilt deterministically)
- **hypothesis** — needs confirmation on a real device

## 1. Read output frequency U00.00 (register 0x3000) — *manual* ✅

Request:

```text
01 03 30 00 00 01 8B 0A
```

Response (50.00 Hz → raw 5000 = 0x1388):

```text
01 03 02 13 88 B5 12
```

Notes: register address is sent as the plain register number (`0x3000`), i.e. **no
holding/input offset**. This frame's CRC matches the manual exactly, which confirms
standard Modbus RTU framing on the A650.

## 2. Start forward — write command word 0x2000 = 0x0001 — *computed*

Request:

```text
01 06 20 00 00 01 43 CA
```

Response (echo):

```text
01 06 20 00 00 01 43 CA
```

## 3. Stop with deceleration — write command word 0x2000 = 0x0005 — *computed*

Request:

```text
01 06 20 00 00 05 42 09
```

Response (echo):

```text
01 06 20 00 00 05 42 09
```

## 4. Set frequency 30.00 Hz — write 0x2001 = 3000 (0x0BB8) — *computed*

Request:

```text
01 06 20 01 0B B8 D4 88
```

Response (echo):

```text
01 06 20 01 0B B8 D4 88
```

Exception response if the value is out of range (Illegal Data Value):

```text
01 86 03 02 61
```

## 5. Write to a read-only register → exception — *hypothesis*

Attempt to write monitor register 0x3000:

Request:

```text
01 06 30 00 00 00 F1 94
```

Expected exception (placeholder — standard Illegal Data Address; the manual also
mentions a detailed code 0x11 "read-only", exposure mechanism unknown):

```text
01 86 02 C3 A1
```

**TODO on bench:** confirm whether the drive answers 0x02, 0x03, or something else
(and how the detailed 0x11 is conveyed).

## 6. Link test (FC 0x08) — *hypothesis*

The manual lists diagnostic function 0x08 but no example frames are documented yet.
**TODO:** capture on real device.

## Open questions affecting these frames

- Command-word bit map for 0x2000 (reverse, jog, fault-reset values unknown).
- Whether named parameters (Fxx.yy) map to registers flatly (hypothesis: F01.01 → 0x0001)
  or via group windows — blocks all parameter read/write examples.
- F15.01 default data format discrepancy (1-8-N-1 vs 1-8-N-2).
