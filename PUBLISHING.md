# Publishing NetBox SSH Browser

This document is for project maintainers. End users should install the package
with `pipx install netbox-ssh-browser`.

## Package layout

The distribution name is `netbox-ssh-browser`, the import package is
`netbox_ssh`, and the console command is `nssh`. The entry point is declared in
`pyproject.toml`:

```toml
[project.scripts]
nssh = "netbox_ssh.cli:main"
```

Installers create the platform-appropriate launcher automatically. No symlink,
shell alias, administrator rights, or post-install script is required.

## One-time GitHub setup

1. Create a GitHub repository named `netbox-ssh-browser`.
2. Add the repository URL under `[project.urls]` in `pyproject.toml` after the
   final GitHub owner is known.
3. Push the default branch and confirm that the `Tests` workflow succeeds on
   macOS, Linux, and Windows.
4. In GitHub repository settings, create an environment named `pypi` and
   require manual approval for it.

The canonical working directory currently has no Git metadata. Before running
`git init`, decide whether history from the former directory should be moved or
whether this should intentionally be a new repository.

## One-time PyPI setup

Create a PyPI account and enable two-factor authentication. Do not create a
long-lived upload token in GitHub.

Configure pending Trusted Publishers with these exact values:

| Project | Workflow | Environment |
|---------|----------|-------------|
| `netbox-ssh-browser` | `publish.yml` | `pypi` |

For each publisher, also enter the final GitHub owner and repository name.
Trusted Publishing uses short-lived OIDC credentials, so the workflows need no
PyPI password or API-token secret.

The public PyPI JSON endpoint returned HTTP 404 for `netbox-ssh-browser` on
2026-08-04, which indicates that the name was not registered at that moment.
Availability is not reserved until the first successful publication.

## Validate locally

Run the tests and build both standard distribution formats:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

Test the wheel rather than the source checkout:

```bash
python -m venv /tmp/netbox-ssh-browser-release-test
/tmp/netbox-ssh-browser-release-test/bin/python -m pip install \
  dist/netbox_ssh_browser-0.1.1-py3-none-any.whl
/tmp/netbox-ssh-browser-release-test/bin/nssh --version
```

On Windows, use the equivalent `Scripts\python.exe` and `Scripts\nssh.exe`
paths in a temporary virtual environment.

## Production release

1. Update `__version__` in `src/netbox_ssh/__init__.py`; Hatch reads the
   distribution version from this single source. Confirm the version is new;
   PyPI distributions cannot be replaced.
2. Move completed entries from `Unreleased` in `CHANGELOG.md` into the new
   version section.
3. Run the complete test and build checks locally.
4. Push the release commit and a matching tag such as `v0.1.1`.
5. Create and publish a GitHub Release from that tag, or manually run the
   `Publish package to PyPI` workflow from GitHub Actions.
6. Approve the protected `pypi` environment when GitHub requests it.
7. The `Publish to PyPI` workflow builds, validates, and publishes the wheel and
   source archive through Trusted Publishing.
8. Verify with `pipx install netbox-ssh-browser` in a clean user environment.

Never upload `config.toml` containing a real NetBox token, `manual.json`, cache
files, `.venv`, or generated `dist/` artifacts to GitHub.
