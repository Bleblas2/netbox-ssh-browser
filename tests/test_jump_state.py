import stat
import tempfile
import unittest
from pathlib import Path

from netbox_ssh.jump_state import load_jump_devices, save_jump_devices


class JumpStateTests(unittest.TestCase):
    def test_round_trip_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "jump-host-devices.json"
            save_jump_devices(path, {"netbox:2", "netbox:1"})
            self.assertEqual(load_jump_devices(path), {"netbox:1", "netbox:2"})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(load_jump_devices(Path("/definitely/missing/state.json")), set())


if __name__ == "__main__":
    unittest.main()
