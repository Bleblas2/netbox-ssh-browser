import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from netbox_ssh.config import Config
from netbox_ssh.config_upgrade import upgrade_config_file
from netbox_ssh.inventory import DEFAULT_ADDRESS_ORDER


class ConfigUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.toml"

    def test_startup_adds_missing_defaults_and_preserves_comments_and_values(self):
        original = '# My settings\n[netbox]\napi_token = "test-token" # keep\n[sync]\ndevice_roles = []\n'
        self.path.write_text(original)
        with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(self.path)}, clear=True):
            config = Config.from_env()
        text = self.path.read_text()
        self.assertTrue(text.startswith(original))
        data = tomllib.loads(text)
        self.assertEqual(data["sync"]["address_order"], list(DEFAULT_ADDRESS_ORDER))
        self.assertEqual(data["tree"], {"layout": "auto", "unassigned_group": "Other sites"})
        self.assertEqual(config.address_order, DEFAULT_ADDRESS_ORDER)
        before = self.path.read_bytes()
        with patch("netbox_ssh.config_upgrade.os.replace") as replace:
            upgrade_config_file(self.path)
        replace.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_preserves_custom_and_empty_settings_and_unusual_toml(self):
        cases = [
            '[sync]\naddress_order = [] # intentional\n[tree]\nlayout = "sites"\n',
            'sync = { address_order = ["oob_ip"] }\ntree = { layout = "regions" }\n',
            'sync.address_order = ["fqdn"]\ntree.layout = "sites"\n',
            '["tree"] # quoted\nunassigned_group = "Custom"\n["sync"]\n',
            'notes = """\n[tree]\nlayout = "regions"\n"""\n',
        ]
        for original in cases:
            with self.subTest(original=original):
                self.path.write_text(original)
                before = tomllib.loads(original)
                upgrade_config_file(self.path)
                after = tomllib.loads(self.path.read_text())
                for section, value in before.items():
                    if isinstance(value, dict):
                        for key, item in value.items():
                            self.assertEqual(after[section][key], item)
                    else:
                        self.assertEqual(after[section], value)
                self.assertIn("address_order", after["sync"])
                self.assertIn("layout", after["tree"])
                self.assertIn("unassigned_group", after["tree"])
                if "# intentional" in original:
                    self.assertIn("# intentional", self.path.read_text())

    def test_no_write_permission_keeps_file_and_loads_defaults(self):
        self.path.write_text('[tree]\nlayout = "sites"\n')
        original = self.path.read_bytes()
        with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(self.path)}, clear=True), patch(
            "netbox_ssh.config_upgrade.os.access", return_value=False
        ), patch("netbox_ssh.config_upgrade.tempfile.mkstemp") as create:
            with self.assertWarns(UserWarning):
                config = Config.from_env()
        create.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(config.tree_layout, "sites")
        self.assertEqual(config.address_order, DEFAULT_ADDRESS_ORDER)

    def test_failed_atomic_replace_keeps_original_and_removes_temporary_file(self):
        self.path.write_text('# private\n[netbox]\napi_token = "test-secret"\n')
        original = self.path.read_bytes()
        with patch("netbox_ssh.config_upgrade.os.replace", side_effect=PermissionError("test-secret")):
            with self.assertWarns(UserWarning) as warning:
                upgrade_config_file(self.path)
        self.assertNotIn("test-secret", str(warning.warning))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('.config-*')), [])

    def test_invalid_config_is_not_modified(self):
        for text in ('[tree', '[tree]\nlayout = "invalid"\n'):
            self.path.write_text(text)
            with patch.dict(os.environ, {"NETBOX_SSH_CONFIG": str(self.path)}, clear=True):
                with self.assertRaises(ValueError):
                    Config.from_env()
            self.assertEqual(self.path.read_text(), text)

    def test_missing_file_is_not_created(self):
        upgrade_config_file(self.path)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
