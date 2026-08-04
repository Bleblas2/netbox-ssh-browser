# Changelog

All notable changes to NetBox SSH Browser will be documented in this file.

The format is based on Keep a Changelog and the project uses semantic
versioning.

## [Unreleased]

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
