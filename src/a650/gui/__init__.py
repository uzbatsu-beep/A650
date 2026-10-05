"""Qt (PySide6) graphical interface for the a650 configurator.

Layers (docs/ARCHITECTURE.md): gui -> controller -> client -> modbus/transport.
The GUI never touches the wire directly; all I/O goes through DriveController,
which runs every Modbus exchange on a single worker thread so the UI stays
responsive even with a 9600-baud bus or an unpowered drive.
"""
