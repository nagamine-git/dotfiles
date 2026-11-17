-- Super+A は描画効果だけを切り替える。CPU・IME・形・モニター設定は変えない。
-- 状態は Hyprland の Lua VM 内だけに置き、reload 時は通常設定からやり直す。
local M = {}
local saved
local keys = { "animations.enabled", "decoration.blur.enabled", "decoration.shadow.enabled" }

function M.toggle()
    if saved then
        hl.config(saved)
        saved = nil
    else
        local before, disabled = {}, {}
        for _, key in ipairs(keys) do
            before[key] = hl.get_config(key)
            disabled[key] = false
        end
        hl.config(disabled)
        saved = before
    end
    hl.notification.create({ text = saved and "描画効果: 軽量" or "描画効果: 復元", timeout = 2000, icon = "ok" })
end

return M
