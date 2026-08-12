from __future__ import annotations

import argparse
import sys

from . import __version__
from .cache import load_cache
from .config import Config
from .jump_state import load_jump_devices
from .manual import load_manual_devices
from .service import filter_device_roles
from .tui import NetBoxSSHApp

__all__ = ["filter_device_roles", "main"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Obsługuje standardowe opcje CLI bez uruchamiania pełnego TUI."""
    parser = argparse.ArgumentParser(
        prog="nssh",
        description="Browse NetBox devices and open system SSH sessions.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Wczytuje lokalny stan i przekazuje sterowanie aplikacji Textual."""
    _parse_args(argv)
    try:
        config = Config.from_env()
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    try:
        manual_devices = load_manual_devices(config.manual_path)
        jump_devices = load_jump_devices(
            config.jump_state_path
            or config.manual_path.with_name("jump-host-devices.json")
        )
    except ValueError as error:
        print(f"Local data error: {error}", file=sys.stderr)
        return 1
    NetBoxSSHApp(
        config, load_cache(config.cache_path), manual_devices, jump_devices
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
