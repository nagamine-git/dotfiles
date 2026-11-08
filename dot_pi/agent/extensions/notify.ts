/**
 * notify — Claude Code's Stop / Notification hooks for Pi. When Pi waits for the owner
 * (herdr:blocked, as jev-gate emits around its confirm prompt) or has settled, it runs
 * ~/.local/bin/claude-notify, which pushes to the phone (ntfy, by default only while the
 * screen is locked), shows a desktop notification outside herdr and records the
 * Super+Shift+R target. Inside herdr the desktop toast is herdr's (herdr-agent-state.ts).
 *
 * TUI only: print, JSON and RPC runs have nobody at this terminal. Never blocks or throws into the agent.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { spawn } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

const CLAUDE_NOTIFY = path.join(os.homedir(), ".local/bin/claude-notify");

function notify(mode: "stop" | "notification", body: string): void {
  try {
    const child = spawn(CLAUDE_NOTIFY, [mode, body],
      { stdio: "ignore", detached: true, env: { ...process.env, CLAUDE_NOTIFY_APP: "Pi" } });
    child.on("error", () => {});
    child.unref();
  } catch { /* never break the agent */ }
}

// The last thing Pi said, like claude-notify's last_assistant_text for Claude Code's transcript.
function lastReply(ctx: any): string {
  const branch = ctx.sessionManager?.getBranch?.() ?? [];
  for (let i = branch.length - 1; i >= 0; i--) {
    const m = branch[i]?.type === "message" ? branch[i].message : undefined;
    if (m?.role !== "assistant") continue;
    const c = m.content;
    const blocks = typeof c === "string" ? [c] : Array.isArray(c) ? c.filter((b: any) => b?.type === "text").map((b: any) => b.text) : [];
    const text = blocks.join(" ").replace(/\s+/g, " ").trim();
    if (text) return text.slice(0, 160);
  }
  return "";
}

export default function (pi: ExtensionAPI) {
  let tui = false;
  pi.on("session_start", (_event, ctx) => { tui = ctx.mode === "tui"; });

  pi.events.on("herdr:blocked", (data: any) => {
    if (tui && data?.active) notify("notification", String(data.label ?? ""));
  });

  // An aborted run (Escape) means the owner is at the keyboard already.
  pi.on("agent_settled", (event, ctx) => {
    if (tui && !event.aborted && ctx.isIdle()) notify("stop", lastReply(ctx));
  });
}
