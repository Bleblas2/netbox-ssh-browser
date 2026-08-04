# Compatibility

## Python

NetBox SSH Browser requires Python 3.11 or newer. The automated test suite runs
with Python 3.11 and 3.13 on macOS, Linux, and Windows.

## Operating Systems

| Operating System | Status | Cache Location |
|------------------|--------|----------------|
| macOS | Supported and tested | `~/Library/Caches/netbox-ssh-browser/` |
| Linux | Supported | `~/.cache/netbox-ssh-browser/` |
| Ubuntu on WSL2 | Supported and manually tested | `~/.cache/netbox-ssh-browser/` |
| Windows | Supported and manually tested | `%LOCALAPPDATA%` via `platformdirs` |

## NetBox

The application uses stable NetBox REST API endpoints for status, regions,
sites, and devices. It supports legacy API tokens and NetBox 4.5+ v2 Bearer
tokens beginning with `nbt_`.

NetBox object permissions and constrained permissions are enforced by NetBox
before inventory reaches the application.

## Terminals

The Textual interface requires a terminal with standard ANSI and alternate
screen support. It is manually tested in iTerm2 on macOS, Ubuntu under WSL2,
and Windows Terminal with PowerShell. It is not implemented as an iTerm2
plugin.

Opening multiple selected devices as tabs is currently supported only when
`nssh` runs inside iTerm2 on macOS. Other terminals retain the portable
single-device SSH behavior through their system `ssh` command. On Linux and
Ubuntu under WSL2, multiple selections display an explanatory message instead
of attempting to invoke the macOS-only integration.
