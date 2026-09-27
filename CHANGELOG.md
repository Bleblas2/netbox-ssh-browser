# Changelog

All notable changes to NetBox SSH Browser will be documented in this file.

The project uses semantic versioning. Release notes group new features,
enhancements, bug fixes, and upgrade notes by version.

## [Unreleased]

## v0.1.6 (2026-09-27)

### New Features

#### Sites Without Regions and Configurable Tree Layouts ([#11](https://github.com/Bleblas2/netbox-ssh-browser/issues/11))

Devices assigned to sites without a region are now accessible in the location
tree, including inventories which combine regional and unassigned sites.
The new `[tree] layout` setting controls how locations are displayed:

- `auto` (default): use the region hierarchy when available; otherwise list sites.
- `regions`: preserve regional navigation and group sites without an available
  region under `Other sites`, configurable through `[tree] unassigned_group`.
- `sites`: list sites directly, regardless of their region assignments.

Existing configurations use `auto` without requiring changes. Layouts can be
switched using cached inventory, and jump-host selections remain attached to
the same devices across layout changes and synchronization.

### Enhancements

- Add missing tree and address defaults without overwriting user settings;
  skip configuration updates when write access is unavailable.

- Add OOB IP support and configurable address priority through
  `[sync] address_order`, with optional `fqdn` (device name) selection and
  omission of devices without an enabled address source.

- [#11](https://github.com/Bleblas2/netbox-ssh-browser/issues/11) - Allow manual
  devices without region, country, or city values, and adapt location labels
  and device creation to the active layout. Existing manual inventory files
  remain readable.

### Security

- Restrict API requests, pagination, and redirects to the configured NetBox
  scheme, host, and port to prevent token disclosure.
- Validate API pagination responses and SSH targets, including jump hosts;
  hide the API token from configuration representations.

### Bug Fixes

- Correctly resolve relative API pagination links.
- Put the comment for automatically added `address_order` on a separate line.
- Handle malformed configuration sections and an empty `XDG_CONFIG_HOME` safely.

### Upgrade Notes

This release introduces cache v3, which stores regions, sites, and devices
independently of the selected tree layout. Cache v2 is not converted: press `S`
to synchronize once before using NetBox inventory offline. Manual inventory
files remain compatible.

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
