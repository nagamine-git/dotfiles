/**
 * live-gate — the owner's go before Pi acts on the owner's live Chrome or desktop.
 *
 * Two surfaces act with the owner's own logins and windows:
 *   chrome   mcp__chrome__*          chrome-devtools-mcp --autoConnect: the running Chrome, every tab of the profile
 *   desktop  computer_use_linux_*    @agent-sh/computer-use-linux: screen, pointer and keyboard
 * jev-gate's auto mode runs MCP and package tools without a dialog, so without this file a click that submits,
 * buys or publishes would run unseen. Here:
 *   - Looking (lists, snapshots, screenshots, accessibility trees, diagnostics) runs.
 *   - Acting (click, type, key, navigate, drag, upload, run a script, move a window) needs the owner's go,
 *     asked once per session branch and surface. The go is stored on the branch; an abandoned branch's is not read.
 *   - A decline is kept too: the agent is not asked again and cannot ask again. The owner turns a surface on or
 *     off with /live <chrome|desktop|all> <on|off>.
 *   - Without a UI there is nobody to ask, so acting is blocked: an unattended Pi only looks. There is no
 *     environment variable or file that grants the go; only the dialog and /live do.
 *   - A question cut short by Escape decides nothing.
 * A tool this file does not know as looking counts as acting, so a new tool of either package asks first.
 * Decisions are appended to ~/.pi/agent/jev-gate.log.jsonl (layer "live"), without the tool input.
 * This is a floor against accidents, not a sandbox: a go covers the session, not each click.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const LOG = path.join(os.homedir(), ".pi/agent/jev-gate.log.jsonl");
const ENTRY = "live-gate";
type Surface = { id: string; label: string; prefix: string; looking: Set<string> };
const SURFACES: Surface[] = [
  { id: "chrome", label: "ログイン済みの Chrome", prefix: "mcp__chrome__",
    looking: new Set(["list_pages", "select_page", "take_snapshot", "take_screenshot", "list_console_messages",
      "get_console_message", "list_network_requests", "get_network_request", "get_css_styles", "wait_for"]) },
  { id: "desktop", label: "PC の画面 (デスクトップ)", prefix: "computer_use_linux_",
    looking: new Set(["tools", "doctor", "list_apps", "list_windows", "focused_window", "get_app_state", "get_tree_page",
      "screenshot"]) },
];
const INSTRUCTIONS =
  "The owner's running Chrome (mcp__chrome__*) and desktop (computer_use_linux_*) act with the owner's own logins. " +
  "Looking is free; the first action on each asks the owner once for this session. Look before acting, and never submit, " +
  "send, purchase, publish or delete there unless the owner asked for exactly that. A decline is final for the session: " +
  "do not reach the same effect through bash, another browser tool or another harness.";

function log(entry: Record<string, unknown>): void {
  try {
    fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), layer: "live", ...entry }) + "\n");
  } catch { /* never break the agent on a logging failure */ }
}

/** The owner's last word on a surface on this branch: true, false, or undefined when never asked. */
function decided(ctx: any, surface: string): boolean | undefined {
  const branch = ctx.sessionManager.getBranch();
  for (let i = branch.length - 1; i >= 0; i--) {
    const e = branch[i];
    if (e.type === "custom" && e.customType === ENTRY && e.data?.surface === surface && typeof e.data.allow === "boolean") return e.data.allow;
  }
  return undefined;
}

export default function (pi: ExtensionAPI) {
  const asking = new Map<string, Promise<boolean>>(); // parallel calls share one dialog

  pi.registerCommand("live", {
    description: "ログイン済みの Chrome と PC 画面の操作を許可・停止: /live [chrome|desktop|all] [on|off]",
    getArgumentCompletions: (prefix) => ["chrome on", "chrome off", "desktop on", "desktop off", "all on", "all off"]
      .filter((v) => v.startsWith(prefix)).map((value) => ({ value, label: value })),
    handler: async (args, ctx) => {
      const [which, state] = args.trim().split(/\s+/);
      const targets = SURFACES.filter((s) => which === "all" || s.id === which);
      if (which && (!targets.length || !["on", "off"].includes(state))) {
        ctx.ui.notify("Usage: /live [chrome|desktop|all] [on|off]", "warning");
        return;
      }
      for (const s of which ? targets : []) {
        pi.appendEntry(ENTRY, { surface: s.id, allow: state === "on" });
        log({ surface: s.id, decision: state === "on" ? "allow" : "deny", via: "command" });
      }
      const show = (v: boolean | undefined) => (v === true ? "許可" : v === false ? "停止" : "未確認 (最初の操作で確認)");
      ctx.ui.notify(SURFACES.map((s) => `${s.label}: ${show(decided(ctx, s.id))}`).join("\n"), "info");
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
    const blocked = (why: string) => ({ block: true, reason: `live-gate: ${why} ` +
      "Do not reach the same effect through bash, another browser tool or another harness; tell the owner what is needed." });
    let allow = decided(ctx, s.id);
    if (allow === undefined) {
      if (!ctx.hasUI || !ctx.ui?.confirm) {
        log({ surface: s.id, action, decision: "deny", via: "no-ui" });
        return blocked(`acting on the owner's ${s.id} needs the owner's go, and there is no UI to ask in.`);
      }
      let pending = asking.get(s.id);
      if (!pending) {
        pending = (async () => {
          pi.events.emit("herdr:blocked", { active: true, label: "live-gate: 本人確認待ち" });
          try {
            return Boolean(await ctx.ui.confirm("live-gate: 操作の許可",
              `このセッションで、${s.label}の操作 (クリック・入力・ページ移動など) を許可しますか?\n` +
              "許可すると、このセッションでは以後確認しません (/live で止められます)。\n" +
              `最初の操作: ${action}`, { signal: ctx.signal }));
          } finally {
            pi.events.emit("herdr:blocked", { active: false });
          }
        })();
        asking.set(s.id, pending);
        void pending.then((ok) => {
          asking.delete(s.id);
          if (!ok && ctx.signal?.aborted) return; // the run was stopped, the question was not answered
          pi.appendEntry(ENTRY, { surface: s.id, allow: ok });
          log({ surface: s.id, action, decision: ok ? "allow" : "deny", via: "confirm" });
        }, () => asking.delete(s.id));
      }
      try { allow = await pending; } catch { allow = false; }
    }
    if (!allow) return blocked(`the owner has not allowed acting on the ${s.id} in this session (/live ${s.id} on).`);
  });
}
