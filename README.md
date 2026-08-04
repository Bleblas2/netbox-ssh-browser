# NetBox SSH Browser

NetBox SSH Browser gives network engineers fast, organized SSH access to large
device inventories without maintaining terminal bookmarks or copying host
addresses from NetBox. It turns NetBox data into an interactive terminal
browser organized by region, country, city, branch, Device Role, and device, so
the right host remains only a few keystrokes away.

The application is especially useful in enterprise networks where devices and
primary IP addresses change over time. A manual **Sync from NetBox** refreshes
the local inventory on demand, while a separate manual inventory lets engineers
add hosts that are not yet present in NetBox. Devices can be searched by name
or address, opened directly with the system OpenSSH client, or selected in
batches and launched in separate iTerm2 tabs on macOS.

NetBox SSH Browser keeps the last successful inventory in a private local cache
for quick access when NetBox is unavailable. It does not implement an SSH
client, store SSH credentials, modify NetBox, or synchronize automatically in
the background.

## Contents

- [What It Does](#what-it-does)
- [Safety Model](#safety-model)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [First Run](#first-run)
- [Navigation](#navigation)
- [Manual Inventory](#manual-inventory)
- [Inventory Rules](#inventory-rules)
- [Local Cache](#local-cache)
- [Development](#development)
- [Compatibility](#compatibility)
- [Acknowledgements](#acknowledgements)

## What It Does

- Reads regions, sites, and devices from the NetBox REST API.
- Builds a navigable location tree from NetBox region and site relationships.
- Groups countries under parent regions, branches under cities, and devices
  under Device Roles.
- Searches all cached devices by name or primary IP address.
- Connects to `primary_ip4`, then `primary_ip6`, and finally the device name
  when no primary IP is assigned.
- Uses the current shell user and the existing OpenSSH configuration.
- Keeps the last successful inventory available when NetBox is offline.

## Safety Model

- Synchronization is manual and runs only after pressing `S`.
- The application performs read-only `GET` requests to NetBox.
- NetBox remains responsible for authentication and object permissions.
- The API token is read from the private user configuration or, when set, from
  `NETBOX_API_TOKEN`. It is never written to cache or logs.
- The NetBox token and URL are removed from the child SSH process environment.
- SSH is started as an argument list without `shell=True`.
- Host keys, SSH Agent, ProxyJump, keys, and connection options remain managed
  by the system OpenSSH client and `~/.ssh/config`.
- A failed or interrupted sync never overwrites the previous valid cache.
- The cache directory is mode `0700` and the cache file is mode `0600`.
- The application does not require `sudo` or write to system directories.

## Requirements

- Python 3.11 or newer.
- A NetBox REST API token with view permissions for DCIM regions, sites, and
  devices.
- The system `ssh` command.
- A terminal with standard TUI support, such as iTerm2, Terminal.app, or a
  Linux terminal emulator.

NetBox API v1 and v2 tokens are supported. Tokens beginning with `nbt_` use
Bearer authentication; legacy tokens use Token authentication.

## Installation

The recommended installation method is `pipx`. It gives the application an
isolated environment and automatically exposes the `nssh` command on `PATH`.

### macOS

```bash
brew install pipx
pipx ensurepath
pipx install netbox-ssh-browser
```

Open a new terminal after `pipx ensurepath`.

### Linux

On Ubuntu 23.04 or newer:

```bash
sudo apt update
sudo apt install pipx
pipx ensurepath
pipx install netbox-ssh-browser
```

On Fedora, replace the first two commands with `sudo dnf install pipx`. Open a
new terminal after updating `PATH`.

### Windows

In PowerShell, install `pipx` with Scoop:

```powershell
scoop install pipx
pipx ensurepath
pipx install netbox-ssh-browser
```

Alternatively, install pipx through Python with `py -m pip install --user pipx`,
run the resulting `pipx.exe ensurepath`, and restart PowerShell.

### Verify, upgrade, and uninstall

```bash
nssh --version
pipx upgrade netbox-ssh-browser
pipx uninstall netbox-ssh-browser
```

`pipx` normally places the command link in `~/.local/bin` on macOS and Linux,
and `%USERPROFILE%\.local\bin` on Windows. The isolated application code is
stored under the platform-specific `PIPX_HOME`:

- macOS: `~/Library/Application Support/pipx/venvs/netbox-ssh-browser`
- Linux: `~/.local/share/pipx/venvs/netbox-ssh-browser`
- Windows: `%LOCALAPPDATA%\pipx\venvs\netbox-ssh-browser`

Use these commands to see the exact resolved locations on any machine:

```bash
pipx environment --value PIPX_HOME
pipx environment --value PIPX_BIN_DIR
```

### Local development

Create an isolated editable installation:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

You can also expose the development command with a symbolic link:

```bash
ln -s \
  "/absolute/path/to/netbox-ssh-browser/.venv/bin/nssh" \
  "$HOME/bin/nssh"
```

The link remains valid only while the project and `.venv` stay at the same
location.

For release preparation and PyPI publication, see
[PUBLISHING.md](PUBLISHING.md).

## Configuration

Store the NetBox URL and API token in the private user configuration:

```toml
[netbox]
url = "https://netbox.example.com"
api_token = "your-token"
verify_ssl = true
```

The token must contain only its value, without the `Bearer` or `Token` prefix.
The application selects the correct authorization scheme. `NETBOX_URL` and
`NETBOX_API_TOKEN` remain optional environment overrides.

Start `nssh` and press `C` to create and edit the private user configuration.
On macOS and Linux it can also be initialized manually:

```bash
mkdir -p ~/.config/netbox-ssh-browser
nano ~/.config/netbox-ssh-browser/config.toml
chmod 600 ~/.config/netbox-ssh-browser/config.toml
```

The configuration file can also be selected explicitly:

```bash
export NETBOX_SSH_CONFIG="/path/to/config.toml"
```

Configuration precedence is:

1. `NETBOX_SSH_CONFIG`.
2. `~/.config/netbox-ssh-browser/config.toml`.
3. `config.toml` in the current working directory.

Environment variables override corresponding TOML values. Keep the user
configuration private with mode `0600` and never commit a real token.

### NetBox settings

```toml
[netbox]
url = "https://netbox.example.com"
verify_ssl = true
```

For a trusted development environment with a self-signed certificate,
certificate verification can be disabled:

```toml
[netbox]
verify_ssl = false
```

Disabling verification reduces transport security. Production deployments
should use `verify_ssl = true` with a valid certificate or trusted corporate
CA.

### Inventory filters

```toml
[sync]
device_statuses = ["active"]
ignored_manufacturers = ["Example Manufacturer"]
device_roles = [
  "Access Switch",
  "Core Router",
  "Edge Router",
]
```

- `device_statuses` contains NetBox status slugs. An empty list downloads all
  statuses.
- `device_roles` contains exact Device Role names, compared
  case-insensitively. An empty list includes every role.
- `ignored_manufacturers` accepts manufacturer names, slugs, or display values,
  compared case-insensitively. An empty list excludes nothing.
- Status filters are sent to the NetBox API. Role and manufacturer filters are
  applied before the cache is written.

## First Run

1. Set `url` and `api_token` in the private user `config.toml`.
2. Run the application:

   ```bash
   nssh
   ```

3. The initial device list is empty because synchronization is never automatic.
4. Press `S` to sync inventory from NetBox.
5. Review the status bar for connection, authentication, permission, SSL, and
   timeout errors.
6. Select a country, branch, and device with the arrow keys and Enter.

The `/api/status/` endpoint is checked first. Inventory is saved only after all
required API requests and filters complete successfully.

## Navigation

| Key | Action |
|-----|--------|
| `Up` / `Down` | Move between selectable entries |
| `Enter` | Open a location or start SSH for a device |
| `Ctrl+T` / `Space` | Select or unselect a device for a multi-session launch |
| `Ctrl+U` | Clear all selected devices |
| `Esc` | Close search or return to the previous level |
| `/` | Search all cached devices by name or primary IP |
| `S` | Sync from NetBox |
| `+` | Add a manual device to the current branch |
| `C` | Edit the active `config.toml` in the shell editor |
| `M` | Edit `manual.json` in the shell editor |
| `Q` | Quit |

Non-selectable headings reduce unnecessary navigation steps:

```text
Region Group A
  Country A
  Country B

City A
  branch-a-01
  branch-a-02

Access Switch
  switch-01    192.0.2.10
  switch-02    switch-02.example.com
```

The headings are skipped by arrow-key navigation. Selecting a device
immediately suspends the TUI and starts the system SSH client. When SSH exits,
the previous TUI view is restored. Returning from a site or branch also restores
the previously highlighted entry, which makes sequential device checks easier.

On macOS in iTerm2, select devices with `Ctrl+T` (or `Space`) and press `Enter`
to open every selected SSH connection
in a separate tab of the current iTerm2 window. The `nssh` tab remains open.
The first launch may cause macOS to request permission to automate iTerm2.
`Ctrl+U` clears the selection. Single-device SSH remains terminal-independent.
On Linux, WSL, Windows, and macOS terminals other than iTerm2, only a single
system SSH session is available; attempting a multi-session launch displays a
clear compatibility message.

`C` and `M` temporarily suspend the TUI and launch `$VISUAL`, then `$EDITOR`,
or `nano` when neither variable is configured. The editor process does not
inherit the NetBox URL or API token. Configuration and manual inventory are
reloaded after the editor exits successfully. Missing files are initialized
with safe minimal content before the editor starts.

## Manual Inventory

Manual devices are stored independently from the NetBox cache. Navigate to a
specific branch and press `+`, then provide:

- device name,
- IP address or hostname,
- Device Role.

The current breadcrumb supplies the region, country, city, and branch. Manual
devices use a `◇` symbol, appear in global `/` search, and connect through the
same system SSH client. NetBox devices remain read-only in the application.

The file can also be edited manually. Its format is:

```json
{
  "version": 1,
  "devices": [
    {
      "region": "Region Group A",
      "country": "Country A",
      "city": "City A",
      "branch": "branch-a-01",
      "role": "Access Switch",
      "name": "manual-switch-01",
      "target": "192.0.2.50"
    }
  ]
}
```

Paths missing from the NetBox cache are created in memory from `manual.json`.
Synchronization never modifies this file. Invalid JSON or an unsupported format
causes a clear startup error instead of silently discarding entries.

`platformdirs` selects the persistent user-data location:

- macOS: `~/Library/Application Support/netbox-ssh-browser/manual.json`
- Linux: `~/.local/share/netbox-ssh-browser/manual.json`
- Windows: the `netbox-ssh-browser` data directory under `%LOCALAPPDATA%`

The directory is mode `0700` and the file is mode `0600` where supported.

## Inventory Rules

- NetBox API pagination is followed until every permitted object is downloaded.
- Device status filters are queried separately and results are deduplicated by
  NetBox object ID.
- Devices not assigned to a visible site and region cannot be placed in the
  location tree and are skipped.
- Empty regions, countries, cities, branches, and Device Role groups are removed.
- A site is not duplicated when its name matches the final region name.
- IP prefixes are stripped before invoking SSH; for example,
  `192.0.2.10/24` becomes `192.0.2.10`.
- SSH target priority is `primary_ip4`, `primary_ip6`, then `device.name`.
- The cache contains only objects visible to the NetBox user associated with
  the API token.
- Manual devices are merged only in memory and are never written to the NetBox
  cache.

## Local Cache

The application uses `platformdirs` to select the native per-user cache path:

- macOS: `~/Library/Caches/netbox-ssh-browser/devices.json`
- Linux: `~/.cache/netbox-ssh-browser/devices.json`
- Windows: the `netbox-ssh-browser` cache directory under `%LOCALAPPDATA%`

The JSON cache contains the sync timestamp, location tree, Device Roles, device
names, and primary IP addresses. It never contains the NetBox API token or SSH
credentials.

The current cache format is version 2. Unsupported or malformed cache files are
treated as missing. There is no migration from previous cache locations or
formats; press `S` to build a new cache.

## Development

The implementation is split by responsibility under `src/netbox_ssh`:

- `cli.py` loads configuration and starts the Textual application.
- `config.py` merges TOML settings and environment variables.
- `netbox.py` handles authentication, pagination, status filtering, and API
  requests.
- `service.py` coordinates synchronization and inventory filtering.
- `model.py` builds and prunes the location tree.
- `cache.py` validates and atomically writes cache version 2.
- `manual.py` validates, stores, and merges persistent manual devices.
- `tui.py` implements navigation, search, background sync, and SSH handoff.
- `terminal.py` contains the optional multi-tab iTerm2 integration.

Run local checks before submitting changes:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

## Compatibility

See [COMPATIBILITY.md](COMPATIBILITY.md) for the supported Python, operating
system, terminal, and NetBox versions.

## Acknowledgements

Development of NetBox SSH Browser was assisted by OpenAI Codex.
