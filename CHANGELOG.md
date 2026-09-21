# Changelog

All notable changes to NetBox SSH Browser will be documented in this file.

The format is based on Keep a Changelog and the project uses semantic
versioning.

## [Unreleased]

## [0.1.5] - 2026-09-21

### Changed

- Expanded README coverage of SSH jump hosts, including setup, per-device
  selection, persistent settings, and authentication on the jump host.
- Added a recent-changes summary to the README covering jump-host support,
  inventory filters, and navigation improvements.

### Fixed

- The `nssh --version` test now reads the package version instead of expecting
  a hard-coded release number, preventing version bumps from blocking the
  publication workflow with a stale test assertion.

## [0.1.4] - 2026-08-13

### Changed

- Jump-host connections now run the target SSH client on the jump host
  (`ssh -tt jump-host "ssh target"`) instead of using OpenSSH ProxyJump.
  This supports interactive target password prompts and jump hosts that
  prohibit TCP forwarding.
- Both single-device connections and iTerm2 multi-tab launches use the same
  jump-host connection behavior. Passwords are not stored by the application.

## [0.1.3] - 2026-08-12

### Added

- Configurable SSH jump host through `[ssh] jump_host` in `config.toml`.
  The value accepts a hostname, IP address, `user@host`, or an SSH config alias.
- Per-device jump-host selection for NetBox and manual devices: press `J` to
  toggle the setting; marked devices display a `J` indicator.
- Persistent jump-host choices in `jump-host-devices.json`, retained across
  application restarts and inventory synchronization.
- Jump-host support for single-device SSH and iTerm2 multi-tab launches.
- Case-insensitive glob filters for device types (`ignored_device_types`)
  and device names (`ignored_name_patterns`), such as `MX*` and `TEST-*`.

## [0.1.2] - 2026-08-04

### Changed

- Windows installation documentation now covers installing Python with
  WinGet and restarting PowerShell after both Python and pipx update `PATH`.

### Fixed

- Empty top-level regions are removed after their empty descendant locations
  are pruned from the synchronized inventory tree.
- NetBox devices without a name no longer fail synchronization; their API
  display value or object ID is used as a safe fallback label.

## [0.1.1] - 2026-08-04

### Added

- Linux and WSL single-device connections through the system OpenSSH client.
- Commented multi-value examples in newly generated user configuration files.

### Changed

- Navigation now restores the previously highlighted entry when returning from
  a site or branch.
- Non-iTerm2 terminals now report that multi-session launches are unavailable
  while retaining portable single-device SSH.
- Newly generated configuration files include an empty NetBox URL field and
  explain that empty filter lists import all matching inventory.

## [0.1.0] - 2026-08-04

### Added

- Textual device browser grouped by NetBox regions, sites, and Device Roles.
- Manual NetBox synchronization with local cache.
- Device filtering by status, role, and manufacturer.
- Global device search and manual device inventory.
- System OpenSSH handoff and optional multi-tab iTerm2 sessions.
- User-editable configuration and manual inventory from the TUI.
