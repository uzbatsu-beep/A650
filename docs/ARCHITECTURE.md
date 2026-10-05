# Software Architecture

## Layers

1. Transport layer
   - serial port management;
   - RS-485 half-duplex control;
   - timeouts;
   - retries.

2. Modbus RTU layer
   - frame building;
   - CRC16;
   - parsing responses;
   - exception handling.

3. A650 protocol layer
   - register map;
   - scaling;
   - command words;
   - fault decoding.

4. Parameter catalog layer
   - load parameters.csv;
   - validate ranges;
   - group parameters;
   - diff/preview changes.

5. Application layer
   - CLI/GUI;
   - profile save/load;
   - monitoring dashboard;
   - safe write workflow.

## Core objects

- `SerialTransport`
- `ModbusRtuClient`
- `A650RegisterMap`
- `A650ParameterCatalog`
- `A650Device`
- `ProfileManager`
- `SafetyGuard`

## Design rules

- All register definitions must come from `data/registers.csv`.
- All parameter definitions must come from `data/parameters.csv`.
- No hard-coded magic addresses in business logic.
- Every write operation must produce an audit log entry.
- Read-only mode is default.