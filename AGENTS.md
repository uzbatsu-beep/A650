# Codex instructions — A650

A650 is a Python configurator and research prototype for the ONI A650 frequency inverter, using Modbus RTU and a PySide6 GUI.

## Workflow
- Read README.md, CONTRIBUTING.md, SECURITY.md and relevant docs before changing behavior.
- Start each independent task from the latest main in a NEW descriptive branch; one task = one branch = one pull request. Do not reuse a branch after its PR is merged.
- Make focused changes; avoid unrelated refactoring and dependency upgrades.
- Do not merge PRs, force-push, publish releases, or alter protected branches without explicit user approval.
- In every PR, document purpose, files changed, tests run, limitations, and any hardware validation still required.
- Run `python -m pip install -e ".[dev,build]"` and `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` where dependencies/environment permit. If not run, say so explicitly.
- Treat simulated behavior and GUI smoke tests as distinct from tests against a real ONI A650 device.
- Do not claim hardware compatibility or safe operation based solely on simulation.

## Device safety
- Default to read-only behavior and simulation. Never issue live drive start/stop, frequency changes, parameter writes or other physical-control commands without explicit approval and appropriate safeguards.
- Preserve existing write-confirmation and safety interlocks; never bypass them for convenience.
- Do not invent register addresses, protocol semantics, supported device models, or hardware test results. Mark unverified profiles as experimental and cite documentation where possible.

## Completion
- Keep tests and documentation consistent with changes.
- Report test results precisely, with failures and unresolved risks.
- Leave merge to the repository owner.
