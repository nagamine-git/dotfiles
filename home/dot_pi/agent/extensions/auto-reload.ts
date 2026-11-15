/**
 * auto-reload — a running Pi picks up changed extensions, MCP servers and tiers by itself.
 *
 * A session keeps the extension code it started with. On 2026-11-15 sessions opened before a change kept the
 * old jev-router and overwrote the quota cache of the new one. Here, when Pi is idle in the interactive UI
 * (agent_settled) and a watched file changed since the session loaded, Pi runs the same reload as /reload.
 * Watched: ~/.pi/agent/extensions (files and one level of directories), mcp.json, model-tiers.json, AGENTS.md.
 * Not settings.json: Pi writes it itself. Print and JSON runs end on their own and are left alone.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const AGENT = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi/agent");
const COMMAND = "auto-reload-now";

/** The newest modification time among the watched files, 0 if none can be read. */
export function newest(agent = AGENT): number {
  const files = ["mcp.json", "model-tiers.json", "AGENTS.md"].map((f) => path.join(agent, f));
  const dir = path.join(agent, "extensions");
  try {
    for (const name of fs.readdirSync(dir)) {
      const p = path.join(dir, name);
      files.push(p);
      try {
        if (fs.statSync(p).isDirectory()) for (const sub of fs.readdirSync(p)) files.push(path.join(p, sub));
      } catch { /* gone meanwhile */ }
    }
  } catch { /* no extensions directory */ }
  let max = 0;
  for (const f of files) {
    try { max = Math.max(max, fs.statSync(f).mtimeMs); } catch { /* not there */ }
  }
  return max;
}

export default function (pi: ExtensionAPI) {
  const loaded = newest();
  let asked = false;

  pi.registerCommand(COMMAND, {
    description: "拡張機能などが更新されたので読み込み直す (auto-reload が使う)",
    handler: async (_args, ctx) => {
      ctx.ui.notify("auto-reload: 拡張機能・MCP・段の設定が更新されたので読み込み直します", "info");
      await ctx.reload();
    },
  });

  pi.on("agent_settled", (event, ctx) => {
    if (asked || event.aborted || ctx.mode !== "tui" || !ctx.isIdle()) return;
    if (newest() <= loaded) return;
    asked = true; // once per load: the reload replaces this instance
    pi.sendUserMessage(`/${COMMAND}`, { expandPromptTemplates: true });
  });
}
