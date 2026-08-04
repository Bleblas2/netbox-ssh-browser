import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netbox_ssh.editor import editor_command, ensure_config_file, ensure_manual_file
from netbox_ssh.manual import load_manual_devices


class EditorTests(unittest.TestCase):
    def test_editor_precedence_and_nano_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "netbox_ssh.editor.platform.system", return_value="Darwin"
        ):
            self.assertEqual(editor_command(), ["nano"])
        with patch.dict(os.environ, {"EDITOR": "vim -f"}, clear=True):
            self.assertEqual(editor_command(), ["vim", "-f"])
        with patch.dict(
            os.environ, {"EDITOR": "vim", "VISUAL": "code --wait"}, clear=True
        ):
            self.assertEqual(editor_command(), ["code", "--wait"])

    def test_uses_notepad_as_windows_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "netbox_ssh.editor.platform.system", return_value="Windows"
        ):
            self.assertEqual(editor_command(), ["notepad"])

    def test_initializes_missing_files_without_overwriting_existing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            config_path = root / "config.toml"
            manual_path = root / "manual.json"
            ensure_config_file(config_path)
            ensure_manual_file(manual_path)
            self.assertIn("verify_ssl = true", config_path.read_text(encoding="utf-8"))
            self.assertEqual(load_manual_devices(manual_path), [])
            config_path.write_text("custom = true\n", encoding="utf-8")
            ensure_config_file(config_path)
            self.assertEqual(config_path.read_text(encoding="utf-8"), "custom = true\n")


if __name__ == "__main__":
    unittest.main()
