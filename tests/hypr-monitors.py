"""S270ES は 4K120・VRR 無効を明示し、他のモニターの推奨モードは変えない。"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
MONITORS = ROOT / "home/private_dot_config/hypr/monitors.lua.tmpl"
VRR_OFF = ROOT / "home/dot_local/bin/executable_hypr-vrr-off.sh"
CHEZMOI = shutil.which("chezmoi")
S270ES = "desc:IPS Inc. (Intellectual Property Solutions Inc.) S270ES 0000000000001"


def render(hostname):
    data = {"chezmoi": {"hostname": hostname, "os": "linux", "homeDir": "/fixture"}}
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data", json.dumps(data)],
        input=MONITORS.read_text(), capture_output=True, text=True, check=True,
    ).stdout


def rules(text):
    return {
        re.search(r'output = "([^"]*)"', line).group(1): line
        for line in text.splitlines() if line.startswith("hl.monitor(")
    }


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class MonitorConfiguration(unittest.TestCase):
    def test_s270es_uses_explicit_4k120_without_vrr(self):
        for hostname in ("am5-itx", "fp7-e14", "other-linux"):
            with self.subTest(hostname=hostname):
                rule = rules(render(hostname))[S270ES]
                self.assertIn('mode = "3840x2160@120"', rule)
                self.assertIn("vrr = 0", rule)
                self.assertIn("scale = 1.5", rule)
                self.assertIn('position = "auto"', rule)

    def test_other_displays_keep_preferred_mode_and_host_scale(self):
        for hostname, scale in (("am5-itx", "1"), ("fp7-e14", "1.25"), ("other-linux", "1")):
            with self.subTest(hostname=hostname):
                config = rules(render(hostname))
                self.assertEqual(len(config), 3)
                self.assertIn('mode = "preferred"', config["eDP-1"])
                self.assertIn(f"scale = {scale} }}", config["eDP-1"])
                self.assertIn('mode = "preferred"', config[""])
                self.assertIn("scale = 1 }", config[""])

    @unittest.skipUnless(shutil.which("lua"), "Lua が必要")
    def test_rendered_lua_executes_with_monitor_stub(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname):
                lua = 'local count = 0; hl = { monitor = function(rule) assert(type(rule.output) == "string"); count = count + 1 end }\n'
                lua += render(hostname) + '\nassert(count == 3)\n'
                subprocess.run(["lua", "-"], input=lua, capture_output=True, text=True, check=True)

    def test_startup_vrr_helper_skips_explicit_vrr_rule(self):
        self.assertIn('*"vrr ="*)           continue', VRR_OFF.read_text())


if __name__ == "__main__":
    unittest.main()
