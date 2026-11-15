/**
 * live-gate — how Pi may act on the owner's live Chrome and desktop.
 *
 * Two surfaces act with the owner's own logins and windows:
 *   chrome   mcp__chrome__*          Playwright MCP through the Playwright Extension: the running Chrome, the owner's logins
 *   desktop  computer_use_linux_*    @agent-sh/computer-use-linux: screen, pointer and keyboard
 * Each surface has a mode, set per session branch with /live <chrome|desktop|all> <auto|ask|off>:
 *   auto (default, the owner's choice on 2026-11-15)  Pi looks and acts without asking, also without a UI
 *                    (pi -p, subagents). The owner stays able to stop it with /live … off.
 *   ask              Looking runs; the first action asks the owner once for the session (no UI: blocked).
 *   off              Looking runs; acting is blocked.
 * Looking = lists, snapshots, screenshots, accessibility trees, diagnostics. Anything else, including a tool this
 * file does not know, is acting. In every mode the agent is told not to submit, send, purchase, publish or delete
 * there unless the owner asked for exactly that. This is guidance and a kill switch, not a sandbox.
 * Desktop input goes to the target window without taking focus (Hyprland background mode), so the owner can keep
 * working. Decisions are appended to ~/.pi/agent/jev-gate.log.jsonl (layer "live"), without the tool input.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const LOG = path.join(os.homedir(), ".pi/agent/jev-gate.log.jsonl");
const ENTRY = "live-gate";
const MODES = ["auto", "ask", "off"] as const;
type Mode = (typeof MODES)[number];
const DEFAULT: Mode = "auto";
type Surface = { id: string; label: string; prefix: string; looking: Set<string> };
const SURFACES: Surface[] = [
  { id: "chrome", label: "ログイン済みの Chrome", prefix: "mcp__chrome__",
    looking: new Set(["browser_snapshot", "browser_take_screenshot", "browser_console_messages", "browser_network_requests",
      "browser_wait_for",
      // chrome-devtools-mcp, the fallback while the extension's token is missing
      "list_pages", "take_snapshot", "take_screenshot", "list_console_messages", "get_console_message",
      "list_network_requests", "get_network_request", "wait_for"]) },
  { id: "desktop", label: "PC の画面 (デスクトップ)", prefix: "computer_use_linux_",
    looking: new Set(["tools", "doctor", "list_apps", "list_windows", "focused_window", "get_app_state", "get_tree_page",
      "screenshot"]) },
];
const INSTRUCTIONS =
  "The owner's running Chrome (mcp__chrome__*, Playwright through the owner's extension, with the owner's logins) and " +
  "desktop (computer_use_linux_*) are yours to use for the owner's tasks without asking. Look before acting. Never submit, " +
  "send, purchase, publish, delete or change account settings there unless the owner asked for exactly that; stop at the " +
  "confirmation step and report instead. If a surface is blocked (/live off or ask without a UI), do not reach the same " +
  "effect through bash, another browser tool or another harness.";

// Before the package's first tool call: Hyprland input to the target window without focusing it (its README).
process.env.COMPUTER_USE_LINUX_HYPRLAND_BACKGROUND ??= "1";

function log(entry: Record<string, unknown>): void {
  try {
    fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), layer: "live", ...entry }) + "\n");
  } catch { /* never break the agent on a logging failure */ }
}

/** The surface's mode on this branch. An entry from the first version ({allow}) reads as auto or off. */
function modeOf(ctx: any, surface: string): Mode {
  const branch = ctx.sessionManager.getBranch();
  for (let i = branch.length - 1; i >= 0; i--) {
    const e = branch[i];
    if (e.type !== "custom" || e.customType !== ENTRY || e.data?.surface !== surface) continue;
    if (MODES.includes(e.data.mode)) return e.data.mode;
    if (typeof e.data.allow === "boolean") return e.data.allow ? "auto" : "off";
  }
  return DEFAULT;
}

export default function (pi: ExtensionAPI) {
  const asking = new Map<string, Promise<boolean>>(); // parallel calls share one dialog

  pi.registerCommand("live", {
    description: "ログイン済みの Chrome と PC 画面: /live [chrome|desktop|all] [auto|ask|off] (auto は確認なし)",
    getArgumentCompletions: (prefix) => ["chrome", "desktop", "all"].flatMap((s) => MODES.map((m) => `${s} ${m}`))
      .filter((v) => v.startsWith(prefix)).map((value) => ({ value, label: value })),
    handler: async (args, ctx) => {
      const [which, word] = args.trim().split(/\s+/);
      const mode = word === "on" ? "auto" : word;
      const targets = SURFACES.filter((s) => which === "all" || s.id === which);
      if (which && (!targets.length || !MODES.includes(mode as Mode))) {
        ctx.ui.notify("Usage: /live [chrome|desktop|all] [auto|ask|off]", "warning");
        return;
      }
      for (const s of which ? targets : []) {
        pi.appendEntry(ENTRY, { surface: s.id, mode });
        log({ surface: s.id, mode, via: "command" });
      }
      const show = { auto: "自動 (確認なし)", ask: "最初の操作で確認", off: "停止" };
      ctx.ui.notify(SURFACES.map((s) => `${s.label}: ${show[modeOf(ctx, s.id)]}`).join("\n"), "info");
    },
  });

  pi.on("before_agent_start", (event) => {
    event.systemPromptOptions.sections.live_gate = INSTRUCTIONS;
  });

  pi.on("tool_call", async (event, ctx) => {
    const s = SURFACES.find((x) => event.toolName.startsWith(x.prefix));
    if (!s) return;
    const action = event.toolName.slice(s.prefix.length);
    if (s.looking.has(action)) return;
    const mode = modeOf(ctx, s.id);
    if (mode === "auto") {
      log({ surface: s.id, action, decision: "allow", via: "auto" });
      return;
    }
    const blocked = (why: string) => ({ block: true, reason: `live-gate: ${why} ` +
      "Do not reach the same effect through bash, another browser tool or another harness; tell the owner what is needed." });
    if (mode === "off") {
      log({ surface: s.id, action, decision: "deny", via: "off" });
      return blocked(`the owner turned acting on the ${s.id} off (/live ${s.id} auto turns it back on).`);
    }
    if (!ctx.hasUI || !ctx.ui?.confirm) {
      log({ surface: s.id, action, decision: "deny", via: "no-ui" });
      return blocked(`acting on the owner's ${s.id} is set to ask, and there is no UI to ask in.`);
    }
    let pending = asking.get(s.id);
    if (!pending) {
      pending = (async () => {
        pi.events.emit("herdr:blocked", { active: true, label: "live-gate: 本人確認待ち" });
        try {
          return Boolean(await ctx.ui.confirm("live-gate: 操作の許可",
            `このセッションで、${s.label}の操作 (クリック・入力・ページ移動など) を許可しますか?\n` +
            "許可すると、このセッションでは以後確認しません (/live で切り替えられます)。\n" +
            `最初の操作: ${action}`, { signal: ctx.signal }));
        } finally {
          pi.events.emit("herdr:blocked", { active: false });
        }
      })();
      asking.set(s.id, pending);
      void pending.then((ok) => {
        asking.delete(s.id);
        if (!ok && ctx.signal?.aborted) return; // the run was stopped, the question was not answered
        pi.appendEntry(ENTRY, { surface: s.id, mode: ok ? "auto" : "off" });
        log({ surface: s.id, action, decision: ok ? "allow" : "deny", via: "confirm" });
      }, () => asking.delete(s.id));
    }
    let ok = false;
    try { ok = await pending; } catch { /* treated as not allowed */ }
    if (!ok) return blocked(`the owner has not allowed acting on the ${s.id} in this session.`);
  });
}
