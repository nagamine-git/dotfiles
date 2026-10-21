"""Usage display reads disposable cache fixtures without starting a model."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "dot_local/bin"
READER = BIN / "executable_claude-usage-cache"
COLORED = BIN / "executable_claude-usage-colored.tmpl"
NOTIFY = BIN / "executable_claude-usage-notify"


class UsageCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.cache = self.home / ".claude/tmux-rate-limit-cache.json"
        self.cache.parent.mkdir()
        self.env = {**os.environ, "HOME": str(self.home),
                    "PATH": str(self.bin) + ":" + os.environ["PATH"]}
        for name in ("claude", "claude-usage"):
            self.write_executable(name, '#!/bin/sh\ntouch "$HOME/model-called"\nexit 98\n')

    def tearDown(self):
        self.assertFalse((self.home / "model-called").exists())

    def write_executable(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o700)
        return path

    def fixture(self, age=0, **changes):
        data = {"fetched_at": time.time() - age, "util_5h": 0.72,
                "util_7d": 0.18, "reset_5h": int(time.time()) + 3600}
        data.update(changes)
        self.cache.write_text(json.dumps(data))

    def reader(self, *args):
        return subprocess.run([sys.executable, str(READER), *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_missing_and_malformed_are_unknown(self):
        self.assertEqual(self.reader(), "usage:不明 (/usage)")
        for invalid in ("bad", "[]", "null", '{"fetched_at": 1}',
                        '{"fetched_at": NaN, "util_5h": 0.3}'):
            with self.subTest(invalid=invalid):
                self.cache.write_text(invalid)
                self.assertEqual(self.reader(), "usage:不明 (/usage)")
                self.assertEqual(self.reader("--reset-5h"), "0")

    def test_recent_data_is_explicitly_cached(self):
        self.fixture()
        self.assertEqual(self.reader(), "5h:72% 7d:18% [cache 0m]")
        self.assertGreater(int(self.reader("--reset-5h")), time.time())

    def test_stale_data_has_age_and_cannot_start_a_reset_timer(self):
        self.fixture(age=600)
        self.assertEqual(self.reader(), "5h:72% 7d:18% [stale 10m]")
        self.assertEqual(self.reader("--reset-5h"), "0")

    def test_future_timestamps_and_invalid_utilization_are_unknown(self):
        for changes in ({"fetched_at": time.time() + 100}, {"util_5h": -1},
                        {"util_5h": "0.4"}, {"util_5h": float("inf")},
                        {"util_7d": []}):
            with self.subTest(changes=changes):
                self.fixture(**changes)
                self.assertEqual(self.reader(), "usage:不明 (/usage)")

    def test_missing_weekly_limit_is_not_zero_usage(self):
        self.fixture()
        data = json.loads(self.cache.read_text())
        data.pop("util_7d")
        self.cache.write_text(json.dumps(data))
        self.assertEqual(self.reader(), "5h:72% [cache 0m]")

    def test_reset_older_than_observation_is_not_a_new_reset(self):
        self.fixture(reset_5h=int(time.time()) - 100)
        self.assertEqual(self.reader("--reset-5h"), "0")

    def test_linux_display_uses_only_cache_reader(self):
        if not shutil.which("chezmoi"):
            self.skipTest("chezmoi is needed to render the Linux template")
        shutil.copyfile(READER, self.bin / "claude-usage-cache")
        (self.bin / "claude-usage-cache").chmod(0o700)
        context = '{{ with dict "chezmoi" (dict "os" "linux" "hostname" "test") "theme" (dict "colors" (dict "bg_dark" (dict "hex" "000000") "error" (dict "hex" "ff0000") "warning" (dict "hex" "ffff00"))) }}'
        rendered = subprocess.run(["chezmoi", "execute-template"],
                                  input=context + COLORED.read_text() + "{{ end }}",
                                  capture_output=True, text=True, check=True).stdout
        display = self.write_executable("display", rendered)
        for age in (0, 600):
            self.fixture(age=age)
            result = subprocess.run(["bash", str(display)], env=self.env,
                                    capture_output=True, text=True, check=True)
            self.assertIn("5h:72% 7d:18%", result.stdout)
            self.assertIn("stale" if age else "cache", result.stdout)
        self.cache.unlink()
        result = subprocess.run(["bash", str(display)], env=self.env,
                                capture_output=True, text=True, check=True)
        self.assertIn("usage:不明", result.stdout)

    def test_stop_hook_has_no_usage_refresh(self):
        settings = (ROOT / "dot_claude/private_settings.json.tmpl").read_text()
        self.assertTrue("claude-usage --refresh" not in settings,
                        "Stop must not refresh usage by starting a model")

    def notifier(self, reset):
        (self.home / "now").write_text("1000")
        (self.home / "reset").write_text(str(reset))
        self.write_executable("claude-usage-cache", '#!/bin/sh\ncat "$HOME/reset"\n')
        self.write_executable("date", '#!/bin/sh\ncat "$HOME/now"\n')
        self.write_executable("notify-send", '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/notifications"\n')
        self.write_executable("sleep", '''#!/bin/sh
now=$(cat "$HOME/now")
[ "$now" -ge 1300 ] && exit 99
echo $((now + $1)) > "$HOME/now"
echo 0 > "$HOME/reset"
''')
        result = subprocess.run(["bash", str(NOTIFY)], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 99)
        path = self.home / "notifications"
        return path.read_text() if path.exists() else ""

    def test_notifier_announces_only_saved_schedule_and_only_once(self):
        output = self.notifier(reset=1060)
        self.assertEqual(output.count("リセット予定時刻"), 1)
        self.assertIn("/usage", output)
        self.assertNotIn("リセットされました", output)

    def test_notifier_missing_or_stale_cache_does_not_claim_a_reset(self):
        self.assertEqual(self.notifier(reset=0), "")


if __name__ == "__main__":
    unittest.main()
