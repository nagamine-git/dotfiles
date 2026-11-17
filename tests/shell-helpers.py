"""画像コピーとtmux選択の小さな契約。クリップボード・通知・実tmuxには触れない。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "home/dot_local/bin"

RECORDER = f'''#!{sys.executable}
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
stdin = sys.stdin.buffer.read().hex() if name in ("wl-copy", "fzf") else ""
with pathlib.Path(os.environ["HELPER_LOG"]).open("a") as f:
    f.write(json.dumps({{"command": name, "args": sys.argv[1:], "stdin": stdin}}) + "\\n")
if name == "file":
    print(os.environ.get("TEST_MIME", "image/png"))
    sys.exit(int(os.environ.get("TEST_FILE_EXIT", "0")))
if name == "wl-copy":
    sys.exit(int(os.environ.get("TEST_COPY_EXIT", "0")))
if name == "notify-send":
    sys.exit(int(os.environ.get("TEST_NOTIFY_EXIT", "0")))
if name == "tmux" and sys.argv[1] == "list-windows":
    print(os.environ.get("TEST_WINDOWS", "$1:2 work:editor\\n$3:4 other:shell"))
    sys.exit(int(os.environ.get("TEST_LIST_EXIT", "0")))
if name == "fzf":
    print(os.environ.get("TEST_CHOICE", "$3:4 other:shell"))
    sys.exit(int(os.environ.get("TEST_FZF_EXIT", "0")))
'''


class Helpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        self.log = self.directory / "calls.jsonl"
        for name in ("file", "wl-copy", "notify-send", "tmux", "fzf"):
            path = self.bin / name
            path.write_text(RECORDER)
            path.chmod(0o700)
        self.env = {**os.environ, "PATH": f"{self.bin}:/usr/bin:/bin", "HELPER_LOG": str(self.log)}
        self.image = self.directory / "image with spaces.png"
        self.image.write_bytes(b"fixture image\x00\xff\n")

    def run_helper(self, name, *args, **environment):
        return subprocess.run(
            ["bash", str(BIN / f"executable_{name}"), *map(str, args)],
            env={**self.env, **environment}, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=5,
        )

    def calls(self, command):
        if not self.log.exists():
            return []
        return [row for line in self.log.read_text().splitlines()
                if (row := json.loads(line))["command"] == command]

    def test_image_copy_preserves_binary_data_and_mime(self):
        result = self.run_helper("imgcopy", self.image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("file")[0]["args"], ["-b", "--mime-type", "--", str(self.image)])
        self.assertEqual(self.calls("wl-copy")[0]["args"], ["--type", "image/png"])
        self.assertEqual(self.calls("wl-copy")[0]["stdin"], self.image.read_bytes().hex())
        self.assertIn("コピー: image with spaces.png", self.calls("notify-send")[0]["args"][-1])

    def test_copy_failure_is_not_success(self):
        result = self.run_helper("imgcopy", self.image, TEST_COPY_EXIT="7")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.calls("notify-send"), [])

    def test_mime_probe_failure_does_not_copy_or_notify_success(self):
        result = self.run_helper("imgcopy", self.image, TEST_FILE_EXIT="9")
        self.assertEqual(result.returncode, 9)
        self.assertEqual(self.calls("wl-copy"), [])
        self.assertEqual(self.calls("notify-send"), [])

    def test_notification_failure_does_not_undo_successful_copy(self):
        result = self.run_helper("imgcopy", self.image, TEST_NOTIFY_EXIT="1")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.calls("wl-copy")), 1)

    def test_missing_file_is_rejected(self):
        result = self.run_helper("imgcopy", self.directory / "missing.png")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("wl-copy"), [])
        self.assertEqual(self.calls("file"), [])

    def test_missing_argument_is_rejected(self):
        result = self.run_helper("imgcopy")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("wl-copy"), [])

    def test_non_image_is_rejected(self):
        result = self.run_helper("imgcopy", self.image, TEST_MIME="text/plain")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls("wl-copy"), [])
        self.assertIn("not an image", result.stderr)

    def test_filename_metacharacters_remain_literal(self):
        image = self.directory / "literal ; $(touch DO_NOT_CREATE).png"
        image.write_bytes(b"fixture")
        result = self.run_helper("imgcopy", image)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("file")[0]["args"][-1], str(image))
        self.assertIn(image.name, self.calls("notify-send")[0]["args"][-1])
        self.assertFalse((self.directory / "DO_NOT_CREATE").exists())
        self.assertFalse((ROOT / "DO_NOT_CREATE").exists())

    def test_tmux_selection_switches_only_stable_id(self):
        result = self.run_helper("tmux-fzf-window", TEST_CHOICE="$3:4 display name with spaces")
        self.assertEqual(result.returncode, 0, result.stderr)
        switches = [c for c in self.calls("tmux") if c["args"][0] == "switch-client"]
        self.assertEqual([c["args"] for c in switches], [["switch-client", "-t", "$3:4"]])

    def test_tmux_cancel_ignores_even_partial_selection(self):
        result = self.run_helper("tmux-fzf-window", TEST_FZF_EXIT="130", TEST_CHOICE="$3:4 partial")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(any(c["args"][0] == "switch-client" for c in self.calls("tmux")))

    def test_tmux_empty_selection_does_nothing(self):
        result = self.run_helper("tmux-fzf-window", TEST_CHOICE="")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(any(c["args"][0] == "switch-client" for c in self.calls("tmux")))

    def test_tmux_list_failure_never_switches(self):
        result = self.run_helper("tmux-fzf-window", TEST_LIST_EXIT="1")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(any(c["args"][0] == "switch-client" for c in self.calls("tmux")))

    @unittest.skipUnless(shutil.which("chezmoi"), "chezmoi が必要")
    def test_targeted_install_preserves_paths_and_executable_mode(self):
        for host, os_name in (("am5-itx", "linux"), ("fp7-e14", "linux"), ("m1pro-mbp14", "darwin")):
            with self.subTest(host=host):
                fixture = self.directory / host
                dest = fixture / "home"
                (dest / ".local/bin").mkdir(parents=True)
                config = fixture / "chezmoi.toml"
                config.write_text("")
                targets = [dest / ".local/bin" / name for name in ("imgcopy", "tmux-fzf-window")]
                subprocess.run(
                    ["chezmoi", "--source", str(ROOT), "--destination", str(dest), "--config", str(config),
                     "--persistent-state", str(fixture / "state.boltdb"), "--override-data",
                     json.dumps({"chezmoi": {"hostname": host, "os": os_name}}), "apply", "--include", "files",
                     *map(str, targets)], capture_output=True, text=True, check=True,
                )
                for target in targets:
                    self.assertTrue(os.access(target, os.X_OK))
                    self.assertEqual(target.read_bytes(), (BIN / f"executable_{target.name}").read_bytes())


if __name__ == "__main__":
    unittest.main()
