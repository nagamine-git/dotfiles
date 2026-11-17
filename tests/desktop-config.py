"""ホスト別に生成・配置したデスクトップ設定を、外部アプリを起動せず検査する。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHEZMOI = shutil.which("chezmoi")
HYPR = ROOT / "home/private_dot_config/hypr"
TARGETS = (
    ".config/hypr/hyprland.lua", ".config/hypr/monitors.lua", ".config/hypr/workspaces.lua",
    ".config/hypr/effects.lua", ".config/waybar/config", ".config/waybar/scripts/gpu_status.py",
    ".local/bin/hypr_perfmodeswitch.sh",
)
RETIRED = (".local/bin/lib_hypr_perfmode.sh", ".config/waybar/scripts/gpu_status.sh")

# 未知のAPIを何でも受け付ける偽物にはせず、使うAPIだけを用意する。
LUA_STUB = '''
local values, bindings, envs, monitors = {}, {}, {}, {}
local function merge(config, prefix)
  for key, value in pairs(config) do
    local path = prefix and (prefix .. "." .. key) or key
    if type(value) == "table" then merge(value, path) else values[path] = value end
  end
end
local function noop() end
local function dispatcher() return function() error("dispatcher must not execute") end end
hl = {
  config = function(config) merge(config) end,
  get_config = function(key) assert(values[key] ~= nil, key); return values[key] end,
  bind = function(key, action) assert(bindings[key] == nil, "duplicate bind: " .. key); bindings[key] = action end,
  env = function(key, value) envs[key] = value end,
  monitor = function(rule) table.insert(monitors, rule) end,
  on = noop, window_rule = noop, layer_rule = noop, workspace_rule = noop,
  device = noop, animation = noop, curve = noop,
  exec_cmd = function() error("must not start applications") end,
  notification = {create = noop},
  dsp = {
    exec_cmd = dispatcher, focus = dispatcher, layout = dispatcher,
    window = {close = dispatcher, fullscreen = dispatcher, float = dispatcher, move = dispatcher,
              drag = dispatcher, resize = dispatcher},
    group = {toggle = dispatcher, next = dispatcher, prev = dispatcher},
    workspace = {toggle_special = dispatcher},
  },
}
'''


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class DesktopConfiguration(unittest.TestCase):
    def render(self, path, hostname):
        return subprocess.run(
            [CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data",
             json.dumps({"chezmoi": {"hostname": hostname, "os": "linux"}})],
            input=path.read_text(), capture_output=True, text=True, check=True,
        ).stdout

    @unittest.skipUnless(shutil.which("lua"), "Lua が必要")
    def test_full_lua_config_and_bound_effects_round_trip(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp)
                for name in ("hyprland", "monitors", "workspaces"):
                    (dest / f"{name}.lua").write_text(self.render(HYPR / f"{name}.lua.tmpl", hostname))
                shutil.copyfile(HYPR / "effects.lua", dest / "effects.lua")
                script = f'package.path = {str(dest / "?.lua")!r}\n' + LUA_STUB
                script += '''
require("hyprland")
assert(type(bindings["SUPER + a"]) == "function")
assert(values["general.border_size"] == 2)
assert(values["decoration.inactive_opacity"] == 1)
assert(values["misc.vrr"] == 0)
assert(#monitors == 3)
assert(monitors[2].mode == "3840x2160@120" and monitors[2].vrr == 0)
local baseline = {}
for key, value in pairs(values) do baseline[key] = value end
bindings["SUPER + a"]()
assert(values["animations.enabled"] == false)
assert(values["decoration.blur.enabled"] == false)
bindings["SUPER + a"]()
for key, value in pairs(baseline) do assert(values[key] == value, "changed: " .. key) end
for key, value in pairs(values) do assert(baseline[key] == value, "added: " .. key) end
assert(#monitors == 3)
'''
                subprocess.run(["lua", "-"], input=script, capture_output=True, text=True, check=True)

    def test_targeted_apply_installs_and_retires_only_requested_files(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                dest = directory / "home"
                for target in (*TARGETS, *RETIRED):
                    (dest / target).parent.mkdir(parents=True, exist_ok=True)
                for target in RETIRED:
                    (dest / target).write_text("old managed file\n")
                untouched = dest / ".local/bin/unified_launcher.sh"
                untouched.write_text("unrelated retired file: not in this apply\n")
                config = directory / "chezmoi.toml"
                config.write_text("")
                subprocess.run(
                    [CHEZMOI, "--source", str(ROOT), "--destination", str(dest), "--config", str(config),
                     "--persistent-state", str(directory / "state.boltdb"), "--override-data",
                     json.dumps({"chezmoi": {"hostname": hostname, "os": "linux"}}),
                     "apply", "--include", "files,remove", *[str(dest / target) for target in (*TARGETS, *RETIRED)]],
                    capture_output=True, text=True, check=True,
                )
                for target in TARGETS:
                    self.assertTrue((dest / target).is_file(), target)
                for target in RETIRED:
                    self.assertFalse((dest / target).exists(), target)
                for target in (".config/waybar/scripts/gpu_status.py", ".local/bin/hypr_perfmodeswitch.sh"):
                    self.assertTrue(os.access(dest / target, os.X_OK), target)
                self.assertTrue(untouched.is_file())


if __name__ == "__main__":
    unittest.main()
