import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netbox_ssh.config import Config


class ConfigTests(unittest.TestCase):
    def test_loads_roles_from_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "netbox-ssh-browser"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(
                '[netbox]\nverify_ssl = true\n'
                '[sync]\ndevice_roles = ["Router", "Switch"]\n',
                encoding="utf-8",
            )
            environment = {
                "XDG_CONFIG_HOME": str(root),
                "XDG_CACHE_HOME": str(root / "cache"),
            }
            with patch.dict(os.environ, environment, clear=True):
                config = Config.from_env()
            self.assertEqual(config.device_roles, ("Router", "Switch"))
            self.assertEqual(config.device_statuses, ())
            self.assertEqual(config.ignored_manufacturers, ())
            self.assertEqual(config.manual_path.name, "manual.json")
            self.assertEqual(config.jump_state_path.name, "jump-host-devices.json")

    def test_default_reads_all_device_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "XDG_CONFIG_HOME": directory,
                "XDG_CACHE_HOME": str(Path(directory) / "cache"),
            }
            with patch.dict(os.environ, environment, clear=True), patch(
                "pathlib.Path.cwd", return_value=Path(directory)
            ):
                config = Config.from_env()
            self.assertEqual(config.device_roles, ())
            self.assertEqual(config.device_statuses, ())
            self.assertEqual(config.ignored_manufacturers, ())

    def test_loads_jump_host_and_glob_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                '[sync]\nignored_device_types = ["MX*"]\n'
                'ignored_name_patterns = ["*CORE"]\n[ssh]\njump_host = "jump-alias"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "missing")}, clear=True), patch(
                "pathlib.Path.cwd", return_value=root
            ):
                config = Config.from_env()
            self.assertEqual(config.ignored_device_types, ("MX*",))
            self.assertEqual(config.ignored_name_patterns, ("*CORE",))
            self.assertEqual(config.jump_host, "jump-alias")

    def test_uses_local_config_when_user_config_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                "[netbox]\nverify_ssl = false\n", encoding="utf-8"
            )
            environment = {
                "XDG_CONFIG_HOME": str(root / "missing-user-config"),
                "XDG_CACHE_HOME": str(root / "cache"),
            }
            with patch.dict(os.environ, environment, clear=True), patch(
                "pathlib.Path.cwd", return_value=root
            ):
                config = Config.from_env()
            self.assertFalse(config.verify_ssl)
            self.assertEqual(config.config_path, root / "config.toml")

    def test_reads_token_from_config_and_environment_can_override_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                '[netbox]\napi_token = "file-token"\n', encoding="utf-8"
            )
            environment = {
                "XDG_CONFIG_HOME": str(root / "missing-user-config"),
                "XDG_CACHE_HOME": str(root / "cache"),
            }
            with patch.dict(os.environ, environment, clear=True), patch(
                "pathlib.Path.cwd", return_value=root
            ):
                self.assertEqual(Config.from_env().api_token, "file-token")

            environment["NETBOX_API_TOKEN"] = "environment-token"
            with patch.dict(os.environ, environment, clear=True), patch(
                "pathlib.Path.cwd", return_value=root
            ):
                self.assertEqual(Config.from_env().api_token, "environment-token")

    def test_rejects_non_table_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(path)}, clear=True):
                for section in ("netbox", "sync", "ssh", "tree"):
                    for value in ('"wrong"', "123", "[]"):
                        with self.subTest(section=section, value=value):
                            content = f"{section} = {value}\n"
                            path.write_text(content)
                            with self.assertRaisesRegex(ValueError, f"{section} must be a TOML table"):
                                Config.from_env()
                            self.assertEqual(path.read_text(), content)

    def test_empty_xdg_config_home_uses_home_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            expected = home / ".config" / "netbox-ssh-browser" / "config.toml"
            expected.parent.mkdir(parents=True)
            expected.write_text('[tree]\nlayout = "sites"\n', encoding="utf-8")
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": "", "XDG_CACHE_HOME": str(root / "cache")}, clear=True), patch(
                "netbox_ssh.config.Path.home", return_value=home
            ), patch("netbox_ssh.config.Path.cwd", return_value=root):
                config = Config.from_env()
            self.assertEqual(config.config_path, expected)
            self.assertEqual(config.tree_layout, "sites")

    def test_config_repr_does_not_include_api_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[netbox]\napi_token = "never-print-this-token"\n')
            with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(path)}, clear=True):
                config = Config.from_env()
            self.assertNotIn("never-print-this-token", repr(config))

    def test_jump_host_config_must_be_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            for value in ("123", "true", "[]"):
                with self.subTest(value=value):
                    path.write_text(f"[ssh]\njump_host = {value}\n")
                    with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(path)}, clear=True):
                        with self.assertRaisesRegex(ValueError, "ssh.jump_host must be text"):
                            Config.from_env()

    def test_tree_defaults_and_validation(self):
        cases = [
            ("", "auto", "Other sites"),
            ("[tree]\n", "auto", "Other sites"),
            ('[tree]\nunassigned_group = "Unassigned"\n', "auto", "Unassigned"),
            ('[tree]\nlayout = "sites"\n', "sites", "Other sites"),
            ('[tree]\nlayout = "regions"\n', "regions", "Other sites"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(path)}, clear=True):
                for content, layout, group in cases:
                    with self.subTest(content=content):
                        path.write_text(content)
                        config = Config.from_env()
                        self.assertEqual(config.tree_layout, layout)
                        self.assertEqual(config.tree_unassigned_group, group)
                for content in ('[tree]\nlayout = "wrong"', '[tree]\nlayout = 3',
                                '[tree]\nunassigned_group = " "', 'tree = "sites"'):
                    with self.subTest(content=content):
                        path.write_text(content)
                        with self.assertRaises(ValueError):
                            Config.from_env()


if __name__ == "__main__":
    unittest.main()
