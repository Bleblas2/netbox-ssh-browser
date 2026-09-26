from __future__ import annotations

import os
import platform
import shlex
from pathlib import Path

from .manual import save_manual_devices


DEFAULT_CONFIG = """[netbox]
url = ""
# Paste only the token value, without the Bearer or Token prefix.
api_token = ""
verify_ssl = true

[sync]
# Try these address sources in order; omitted sources are never used.
# fqdn uses the NetBox device name as a DNS/SSH target only when listed.
# Devices without a selected address are omitted. Empty [] omits all NetBox devices.
# Press S after changing this setting. Manual device targets are unchanged.
# Example: address_order = ["oob_ip", "primary_ip4"]
address_order = ["primary_ip4", "primary_ip6", "oob_ip", "fqdn"]
# Empty [] imports devices with any status.
# Example: device_statuses = ["active", "planned", "staged"]
device_statuses = ["active"]
# Empty [] does not exclude any manufacturer.
# Example: ignored_manufacturers = ["Cisco", "Juniper", "Arista"]
ignored_manufacturers = []
# Glob patterns matched case-insensitively against model, slug, and display.
# Example: ignored_device_types = ["MX*", "ISR4451"]
ignored_device_types = []
# Glob patterns matched case-insensitively against device names.
# Example: ignored_name_patterns = ["*CORE", "TEST-*"]
ignored_name_patterns = []
# Empty [] imports devices with every role.
# Example: device_roles = ["Router", "Core Switch", "Distribution Switch"]
device_roles = []

[tree]
# auto: use regions when present in cached or manual inventory; otherwise list sites.
# regions: preserve the region, country, and location hierarchy.
# sites: list sites directly, regardless of their region assignments.
# Missing layout settings default to auto.
layout = "auto"
# Group name for locations without a region in the regions layout.
unassigned_group = "Other sites"

[ssh]
# Hostname, IP, user@host, or an alias from ~/.ssh/config.
jump_host = ""
"""


def editor_command() -> list[str]:
    """Zwraca standardowy edytor użytkownika odpowiedni dla platformy."""
    fallback = "notepad" if platform.system() == "Windows" else "nano"
    configured = os.environ.get("VISUAL") or os.environ.get("EDITOR") or fallback
    command = shlex.split(configured)
    if not command:
        return [fallback]
    return command


def ensure_config_file(path: Path) -> None:
    """Tworzy bezpieczny minimalny config, jeśli użytkownik jeszcze go nie ma."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    os.chmod(path, 0o600)


def ensure_manual_file(path: Path) -> None:
    """Tworzy pusty manual.json v1 przed pierwszym otwarciem edytora."""
    if not path.exists():
        save_manual_devices(path, [])
