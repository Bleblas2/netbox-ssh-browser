from __future__ import annotations

import os
import platform
import shlex
import subprocess
from collections.abc import Sequence

from .model import Device


ITERM_TABS_SCRIPT = r'''
on run argv
    if (count of argv) is 0 then return
    tell application "iTerm2"
        if (count of windows) is 0 then
            create window with default profile
        end if
        tell current window
            repeat with command_text in argv
                create tab with default profile command (command_text as text)
            end repeat
        end tell
        activate
    end tell
end run
'''


def is_iterm2() -> bool:
    """Sprawdza, czy aplikacja działa wewnątrz sesji iTerm2 na macOS."""
    return platform.system() == "Darwin" and os.environ.get("TERM_PROGRAM") == "iTerm.app"


def _validate_ssh_target(value: object, setting: str) -> str:
    """Sprawdza cel SSH przed przekazaniem go klientowi systemowemu."""
    if not isinstance(value, str):
        raise ValueError(f"{setting} must be text")
    if (
        not value
        or value.startswith("-")
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127
               for character in value)
    ):
        raise ValueError(f"{setting} must be a non-empty SSH target without whitespace")
    return value


def ssh_arguments(device: Device, jump_host: str | None = None) -> list[str]:
    target = _validate_ssh_target(device.ssh_target, "SSH target")
    if device.use_jump_host:
        if not jump_host:
            raise ValueError("No SSH jump host is configured.")
        jump_host = _validate_ssh_target(jump_host, "SSH jump host")
        # The second client runs on the jump host. This works on bastions that
        # prohibit TCP forwarding and lets the target prompt for a password.
        remote_command = f"ssh {shlex.quote(target)}"
        return ["ssh", "-tt", jump_host, remote_command]
    return ["ssh", target]


def run_system_ssh(
    devices: Sequence[Device], jump_host: str | None = None
) -> list[tuple[Device, int]]:
    """Uruchamia systemowy OpenSSH, przenośnie także na Linuxie i WSL."""
    environment = os.environ.copy()
    environment.pop("NETBOX_API_TOKEN", None)
    environment.pop("NETBOX_URL", None)
    results = []
    for device in devices:
        result = subprocess.run(
            ssh_arguments(device, jump_host), check=False, env=environment
        )
        results.append((device, result.returncode))
    return results


def open_iterm_tabs(devices: Sequence[Device], jump_host: str | None = None) -> None:
    """Otwiera osobną kartę iTerm2 dla każdego urządzenia.

    Polecenie SSH jest cytowane jako pojedynczy argument powłoki, a sam
    AppleScript jest stałą w kodzie. Dane urządzenia nie są wstawiane do kodu
    skryptu, tylko przekazywane przez argv programu osascript.
    """
    if not devices:
        return
    if not is_iterm2():
        raise RuntimeError("Opening multiple sessions requires iTerm2 on macOS.")

    commands = [shlex.join(ssh_arguments(device, jump_host)) for device in devices]
    environment = os.environ.copy()
    environment.pop("NETBOX_API_TOKEN", None)
    environment.pop("NETBOX_URL", None)
    result = subprocess.run(
        ["osascript", "-e", ITERM_TABS_SCRIPT, *commands],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or f"osascript exited with status {result.returncode}"
        raise RuntimeError(message)
