# Safety Notes

This software controls a variable frequency drive connected to electric motors and pumps.

## General rules

- Do not enable write operations by default.
- Require explicit confirmation before writing parameters.
- Require explicit confirmation before start/run commands.
- Provide emergency stop command.
- Show current drive state before allowing control actions.
- Log all write operations.
- Validate all values against allowed ranges.
- Do not use broadcast address 0x00 for writes unless intentionally designed.

## Before first connection

Verify:

- supply voltage matches drive rating;
- motor cables are connected correctly;
- control terminals are wired correctly;
- RS-485 polarity A/B is correct;
- drive firmware version is known;
- backup of parameters is possible or not required;
- mechanical load can safely stop/start.

## Parameter writing risks

Incorrect parameters can cause:

- motor overspeed;
- pump dry running;
- valve shock;
- network overload;
- brake resistor overheating;
- unexpected restart after power loss;
- fire-mode misbehavior.

## Recommended software behavior

Default mode:

- read-only.

Write mode must require:

- user acknowledgment;
- device fingerprint check;
- current state check;
- parameter diff preview;
- rollback plan if supported.