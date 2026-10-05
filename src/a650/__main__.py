"""Allow `python -m a650` to launch the CLI / interactive console."""
import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
