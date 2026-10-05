"""Offline demo: build the golden frames and decode a mock response.

No hardware needed:  python examples/python/offline_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from a650.a650lib.register_map import RegisterMap
from a650.a650lib.safety import SafetyGuard
from a650.modbus.crc import append_crc
from a650.modbus.rtu import ReadRegistersRequest, WriteRegisterRequest, parse_response

rmap = RegisterMap.load()
guard = SafetyGuard()

# Build documented frames
print("read U00.00 :", ReadRegistersRequest(1, 0x3000, 1).to_bytes().hex(" ").upper())
print("start fwd   :", WriteRegisterRequest(1, 0x2000, 0x0001).to_bytes().hex(" ").upper())
print("stop        :", WriteRegisterRequest(1, 0x2000, 0x0005).to_bytes().hex(" ").upper())
print("setpoint30  :", WriteRegisterRequest(1, 0x2001, 3000).to_bytes().hex(" ").upper())

# Simulate a device response for the read request (50.00 Hz)
mock = append_crc(bytes.fromhex("0103021388"))
resp = parse_response(mock, expected_slave=1)
reg = rmap.get(0x3000)
print(f"decoded     : {reg.to_engineering(resp.values[0])} {reg.unit} "
      f"(confidence={reg.confidence}, verified={reg.verified_on_device})")

# Safety demonstration
try:
    guard.check_write(slave=1, address=0x2001, value=3000)
except Exception as e:
    print("safety      : write blocked ->", e)
