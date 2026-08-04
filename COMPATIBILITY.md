# Compatibility

## Python

NetBox SSH Browser requires Python 3.11 or newer. The automated test suite is
currently run with Python 3.13.

## Operating Systems

| Operating System | Status | Cache Location |
|------------------|--------|----------------|
| macOS | Supported and tested | `~/Library/Caches/netbox-ssh-browser/` |
| Linux | Supported | `~/.cache/netbox-ssh-browser/` |
| Windows | Expected to work; system `ssh` is required | `%LOCALAPPDATA%` via `platformdirs` |

## NetBox

The application uses stable NetBox REST API endpoints for status, regions,
sites, and devices. It supports legacy API tokens and NetBox 4.5+ v2 Bearer
tokens beginning with `nbt_`.

NetBox object permissions and constrained permissions are enforced by NetBox
before inventory reaches the application.

## Terminals

The Textual interface requires a terminal with standard ANSI and alternate
screen support. It is tested in iTerm2 on macOS and is not implemented as an
iTerm2 plugin.

Opening multiple selected devices as tabs is currently supported only when
`nssh` runs inside iTerm2 on macOS. Other terminals retain the portable
single-device SSH behavior.
