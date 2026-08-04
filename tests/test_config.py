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


if __name__ == "__main__":
    unittest.main()
