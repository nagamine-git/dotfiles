/**
 * herdr-name — give a Pi agent a meaningful herdr sidebar name instead of
 * "pi-2". Mirrors Claude Code's herdr-agent-summary hook: on each turn it builds
 * a short excerpt of the conversation and hands it to ~/.local/bin/herdr-agent-name,
 * which summarizes it with Claude Haiku (billed on the flat Claude plan, not Pi's
 * metered usage) and reports the name to herdr. Rate-limiting lives in that script.
 *
 * Does nothing outside a herdr pane. Never blocks or throws into the agent.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import { spawn } from "node:child_process";

function buildExcerpt(file: string): string {
  const out: string[] = [];
  let lines: string[];
  try {
    lines = fs.readFileSync(file, "utf8").split("\n");
  } catch {
    return "";
  }
  for (const line of lines) {
    if (!line) continue;
    let d: any;
    try { d = JSON.parse(line); } catch { continue; }
    if (d?.type !== "message") continue;
    const m = d.message ?? {};
    const role = m.role;
    if (role !== "user" && role !== "assistant") continue;
    let text = "";
    const c = m.content;
    if (typeof c === "string") text = c;
    else if (Array.isArray(c)) text = c.filter((b: any) => b?.type === "text").map((b: any) => b.text).join("\n");
    text = (text ?? "").replace(/\s+/g, " ").trim();
    if (!text || text.startsWith("<")) continue;
    out.push(`${role === "user" ? "ユーザー" : "エージェント"}: ${text.slice(0, 400)}`);
  }
  return out.slice(-6).join("\n").slice(-2000);
}

export default function (pi: ExtensionAPI) {
  pi.on("turn_end", async () => {
    const file = process.env.PI_SESSION_FILE;
    const pane = process.env.HERDR_PANE_ID;
    if (!file || !pane || process.env.HERDR_ENV !== "1") return;
    const excerpt = buildExcerpt(file);
    if (!excerpt) return;
    try {
      const child = spawn("herdr-agent-name",
        ["--kind", "pi", "--session", process.env.PI_SESSION_ID ?? pane],
        { stdio: ["pipe", "ignore", "ignore"], detached: true, env: process.env });
      child.on("error", () => {});
      child.stdin.write(excerpt);
      child.stdin.end();
      child.unref();
    } catch { /* never break the agent */ }
  });
}
