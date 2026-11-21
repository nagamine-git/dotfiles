// OpenClaw の各ターンのモデルを、Pi の jev/auto と同じ判断 (分類器・利用枠・点数) で選ぶ。
// Pi を PI_JEV_ROUTE_ONLY で呼び、選択だけを受け取る (モデル本体は呼ばない)。失敗時は設定の既定モデルのまま。
import { execFile } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const HOME = homedir();
// Pi の名前 → この OpenClaw (2026.11.5) の目録にある名前。無いものは同系統の一つ前の版。
const FALLBACK = "anthropic/claude-sonnet-5-5";
const ALIAS = { "openai/gpt-6.2-astra": "openai/gpt-6-astra", "openai/gpt-6.2-sol": "openai/gpt-6.1-sol" };

function route(prompt) {
  const dir = mkdtempSync(join(tmpdir(), "jev-route-"));
  const out = join(dir, "choice.json");
  return new Promise((resolve) => {
    execFile(join(HOME, ".local/bin/pi-jev"), ["-p", "--model", "jev/auto", "--no-tools", "--no-mcp", "--no-skills",
      "--no-context-files", "--no-prompt-templates", "--session-dir", join(HOME, ".local/state/openclaw-host/jev-route"),
      "--", prompt.slice(0, 6000)],
    { cwd: dir, timeout: 15000, env: { HOME, PATH: process.env.PATH, LANG: "C.UTF-8", PI_JEV_ROUTE_ONLY: out } }, () => {
      try { resolve(JSON.parse(readFileSync(out, "utf8"))); } catch { resolve(undefined); }
      rmSync(dir, { recursive: true, force: true });
    }).stdin?.end();
  });
}

export default definePluginEntry({
  id: "jev-route",
  name: "Jev route",
  description: "Pick each turn's model with Pi's jev/auto router",
  register(api) {
    api.on("before_model_resolve", async (event) => {
      const text = typeof event?.prompt === "string" ? event.prompt.trim() : "";
      if (!text) return undefined;
      const choice = await route(text);
      if (!choice?.model) return undefined;
      const ref = ALIAS[choice.model] ?? choice.model;
      const slash = ref.indexOf("/");
      api.logger?.info?.(`jev-route: ${choice.model} ${choice.effort} (${choice.level}) -> ${ref}`);
      // 2026.11.5 applies the override only when fallbacksOverride is present. Fall back to the configured default.
      const fallbacks = ref === FALLBACK ? [] : [FALLBACK];
      return { providerOverride: ref.slice(0, slash), modelOverride: ref.slice(slash + 1), fallbacksOverride: fallbacks };
    });
  },
});
