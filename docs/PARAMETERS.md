# Parameter Groups

## Known groups

| Group | Name | Notes |
|---|---|---|
| F00 | System parameters | Password, PWM, rated power/current/voltage, firmware version |
| F01 | Frequency command | Main/auxiliary frequency source |
| F04 | Digital input | DI functions, multi-step, counter, PLC-related inputs |
| F05 | Digital output | DO functions, brake control, pump status |
| F06 | Analog input | AI scaling |
| F11 | Protection | Fault handling, overload, external fault |
| F12 | Simple PLC | PLC mode, reference sources |
| F13 | PID process | PID setpoint, feedback, limits, filters |
| F14 | Sleep/wake, counter | Sleep frequency, wake-up, counter |
| F15 | Communication | Baud rate, data format, Modbus address, master/slave mode |
| F17 | User-defined parameters | Custom parameter list |
| F22 | Virtual IO | TODO |
| H00 | Pump/fire/cleaning functions | Alternation, cleaning, fire mode, bypass |
| U00 | Monitoring | Output frequency, PID values, DI state, AI values, temperature |
| U01 | Fault history | Last fault, frequency/current/voltage at fault |

## Important parameters for configuration software

### Communication

- F15.00 baud rate
- F15.01 data format
- F15.02 local address
- F15.05 master/slave mode
- F15.06 data source to master

### Frequency control

- F01.00 frequency command selection
- F01.01 main frequency source
- F01.03 auxiliary frequency source

### PID

- F13.00 PID setpoint source
- F13.01 digital PID setpoint
- F13.02 PID feedback source
- F13.03 PID feedback range
- F13.04 PID action direction
- F13.05 PID filter time

### Protection

- F11.11 protection action 2
- F11.12 protection action 3
- F11.18/F11.19 overload threshold

### Pump/fire related

- H00.13 alternation time
- H00.15 cleaning function
- H00.43 fire mode loop
- H00.44 fire mode initial value
- H00.45 fire mode fault handling
- H00.47 fire bypass delay