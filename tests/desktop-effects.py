"""描画効果の往復で既存値を復元し、形・入力・モニター設定には触れない。"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
EFFECTS = ROOT / "home/private_dot_config/hypr/effects.lua"
HYPR = ROOT / "home/private_dot_config/hypr/hyprland.lua.tmpl"
WRAPPER = ROOT / "home/dot_local/bin/executable_hypr_perfmodeswitch.sh"


@unittest.skipUnless(shutil.which("lua"), "Lua が必要")
class Effects(unittest.TestCase):
    def run_lua(self, assertions):
        script = f'''
local values = {{
  ["animations.enabled"] = true,
  ["decoration.blur.enabled"] = true,
  ["decoration.shadow.enabled"] = false,
}}
local calls = 0
hl = {{
  get_config = function(key) assert(values[key] ~= nil, key); return values[key] end,
  config = function(config)
    calls = calls + 1
    for key, value in pairs(config) do
      assert(values[key] ~= nil, "Unrelated option changed: " .. key)
      assert(type(value) == "boolean")
      values[key] = value
    end
  end,
  notification = {{create = function(message) assert(type(message.text) == "string") end}},
}}
local effects = dofile({str(EFFECTS)!r})
{assertions}
'''
        result = subprocess.run(["lua", "-"], input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_toggle_only_effects_and_restore_actual_values(self):
        self.run_lua('''
effects.toggle()
for _, value in pairs(values) do assert(value == false) end
effects.toggle()
assert(values["animations.enabled"] == true)
assert(values["decoration.blur.enabled"] == true)
assert(values["decoration.shadow.enabled"] == false)
assert(calls == 2)
''')

    def test_each_cycle_captures_new_values(self):
        self.run_lua('''
effects.toggle(); effects.toggle()
values["animations.enabled"] = false
values["decoration.shadow.enabled"] = true
effects.toggle(); effects.toggle()
assert(values["animations.enabled"] == false)
assert(values["decoration.shadow.enabled"] == true)
''')

    def test_reload_discards_transient_state(self):
        self.run_lua(f'''
effects.toggle()
-- Hyprland は reload 時に Lua VM と通常設定を作り直す。
values["animations.enabled"] = true
values["decoration.blur.enabled"] = false
local reloaded = dofile({str(EFFECTS)!r})
reloaded.toggle(); reloaded.toggle()
assert(values["animations.enabled"] == true)
assert(values["decoration.blur.enabled"] == false)
''')

    def test_failed_apply_does_not_change_toggle_state(self):
        self.run_lua('''
local apply = hl.config
hl.config = function(_) error("failed config") end
assert(pcall(effects.toggle) == false)
hl.config = apply
effects.toggle()
for _, value in pairs(values) do assert(value == false) end
effects.toggle()
assert(values["animations.enabled"] == true)
''')

    def test_bind_and_compatibility_wrapper_use_same_module(self):
        self.assertIn('require("effects").toggle', HYPR.read_text())
        self.assertIn('require("effects").toggle()', WRAPPER.read_text())
        for stale in ("fcitx5", "sudo", "scaling_governor", "/tmp/hypr_perf_mode", "HYPR_NORMAL_BATCH"):
            self.assertNotIn(stale, WRAPPER.read_text())


if __name__ == "__main__":
    unittest.main()
