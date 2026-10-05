# Wiring and Hardware Notes

## RS-485

- Use shielded twisted pair.
- Ground shield near drive side.
- Keep communication cables away from power cables.
- Digital signal cables should not exceed 20 m where possible.
- Use proper termination/biasing for multi-drop networks.

## Analog inputs

- AI1/AI2 can be voltage or current inputs.
- Voltage input: 0-10 V DC.
- Current input: 0/4-20 mA.
- AI3 may support -10..10 V DC depending on model/wiring.
- DIP switches/selectors may configure AI type.

## Digital inputs

- Programmable DI1..DI7.
- One input can be configured as pulse input HI.
- Internal 24 V source available.
- External source voltage should be 20..30 V if used.
- Remove +24V/PLC jumper when using external supply.

## Digital outputs

- Two transistor outputs, NPN open collector.
- Two relay outputs.
- Relay rating from manual: 220 V AC, 3 A; 30 V DC, 1 A.

## Grounding

- Drive and motor must be reliably grounded.
- Total leakage current may exceed 3.5 mA.
- Use shortest possible ground cable.
- Ground point should be close to drive.