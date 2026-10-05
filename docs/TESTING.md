# Testing Strategy

## Unit tests

- CRC16 calculation;
- frame serialization;
- frame parsing;
- exception response parsing;
- scaling functions;
- register map loading;
- parameter range validation.

## Golden tests

Use known frames from manual:

- read U00.00;
- set frequency 30 Hz;
- start forward;
- stop deceleration;
- read-only write error.

## Integration tests

Only with isolated test bench:

- motor disconnected or safely coupled;
- emergency stop available;
- known slave address;
- known baud/format;
- no broadcast writes.

## Regression tests

After any firmware or protocol assumption change:

- re-run golden frames;
- update `CHANGELOG.md`;
- mark confidence level in `registers.csv`.