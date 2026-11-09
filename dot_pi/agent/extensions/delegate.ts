/**
 * delegate — hand one task from Pi to Claude Code or Codex and return its final answer.
 *   claude  `claude -p <task> --output-format json`: model, effort and permission mode are Claude Code's own settings.
 *   codex   `codex exec -s workspace-write -C <cwd> -o <file> <task>`: Codex's OS sandbox, no approval prompt
 *           (config.toml approval_policy = "never"), so what the sandbox blocks fails back to Codex.
 * The task goes as "Task: <task>", as in Pi's subagent example, so it is never read as an option or a subcommand.
 * The children get no herdr pane variables (their hooks would retitle and re-state Pi's pane) and
 * CLAUDE_NOTIFY_PHONE=never (notify.ts already reports Pi's run). Escape stops them; answers are cut at about 50 KB.
 * The child may write anywhere below its directory, so that is Pi's working directory or below it (symlinks
 * resolved), never the home directory itself and never inside a dot directory of home (~/.ssh, ~/.config, ...)
 * unless Pi itself works in there. jev-gate also gates delegate (protected places, the rules, the classifier).
 * Both resolve the directory one way (~ expanded, realpath), so @ and file: paths are not taken. Checking and
 * running are not atomic; inside Pi's project and checked by jev-gate, that window is small enough to leave.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const MAX_OUTPUT = 50 * 1024;
const MAX_CAPTURE = 4 * 1024 * 1024; // kept of each stream; Claude's JSON answer has to fit whole
const HERDR_VARS = ["HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID", "HERDR_SOCKET_PATH", "HERDR_BIN_PATH"];

type Run = { code: number | null; stdout: string; stderr: string; error?: NodeJS.ErrnoException; aborted: boolean };

function run(cmd: string, args: string[], cwd: string, signal?: AbortSignal): Promise<Run> {
  const env: NodeJS.ProcessEnv = { ...process.env, CLAUDE_NOTIFY_PHONE: "never" };
  for (const name of HERDR_VARS) delete env[name];
  return new Promise((resolve) => {
    const out = { stdout: "", stderr: "" };
    const child = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    for (const stream of ["stdout", "stderr"] as const) {
      child[stream].setEncoding("utf8");
      child[stream].on("data", (d: string) => { out[stream] = (out[stream] + d).slice(-MAX_CAPTURE); });
    }
    const stop = () => { child.kill("SIGTERM"); setTimeout(() => child.kill("SIGKILL"), 5000).unref(); };
    if (signal?.aborted) stop();
    signal?.addEventListener("abort", stop, { once: true });
    const done = (code: number | null, error?: NodeJS.ErrnoException) => {
      signal?.removeEventListener("abort", stop);
      resolve({ code, ...out, error, aborted: Boolean(signal?.aborted) });
    };
    child.on("error", (error) => done(null, error));
    child.on("close", (code) => done(code));
  });
}

// The child's directory, or why it may not work there.
function workdir(given: string, piCwd: string): { dir?: string; refused?: string } {
  if (/^(@|file:)/.test(given)) return { refused: `${given} is an @ or file: path (give a plain path)` };
  const home = os.homedir();
  const expanded = given === "~" || given.startsWith("~/") ? home + given.slice(1) : given;
  let dir: string, base: string, realHome: string;
  try {
    [dir, base, realHome] = [path.resolve(piCwd, expanded), piCwd, home].map((p) => fs.realpathSync(p));
    if (!fs.statSync(dir).isDirectory()) throw new Error();
  } catch {
    return { refused: `${given} is not a directory` };
  }
  const under = (top: string, p: string) => p === top || p.startsWith(top + path.sep);
  if (!under(base, dir)) return { refused: `${dir} is outside Pi's working directory ${base}` };
  if (dir === realHome) return { refused: `${dir} is the home directory` };
  const top = path.relative(realHome, dir).split(path.sep)[0];
  const dot = path.join(realHome, top);
  if (top.startsWith(".") && top !== ".." && !under(dot, base)) return { refused: `${dir} is inside ~/${top}` };
  return { dir };
}

function cut(text: string): string {
  const bytes = Buffer.from(text);
  if (bytes.length <= MAX_OUTPUT) return text;
  // stream: true holds back a character cut in half instead of ending on U+FFFD
  return `${new TextDecoder().decode(bytes.subarray(0, MAX_OUTPUT), { stream: true })}\n…(${bytes.length - MAX_OUTPUT} more bytes cut)`;
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "delegate",
    label: "Delegate",
    description:
      "Run one task in Claude Code (claude -p) or Codex (codex exec) and return its final answer. The child starts " +
      "fresh and sees none of this conversation. claude runs with its own settings, hooks, MCP servers and claude.ai " +
      "connectors; codex runs in its OS sandbox (workspace-write) without approval prompts.",
    promptGuidelines: [
      "Use delegate with harness \"claude\" for work that needs what only Claude Code has: the claude.ai connectors " +
        "(Slack, Google, Claude Docs) or Chrome, and for an independent review by another harness.",
      "Use delegate with harness \"codex\" for work that should run inside an OS sandbox (Codex workspace-write).",
      "Write the delegate task self-contained: goal, files, constraints and what to report back.",
    ],
    parameters: Type.Object({
      harness: StringEnum(["claude", "codex"] as const),
      task: Type.String({ description: "Self-contained instructions for the child" }),
      cwd: Type.Optional(Type.String({ description: "Working directory (default: Pi's)" })),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const where = workdir(params.cwd ?? ".", ctx.cwd);
      const cwd = where.dir ?? path.resolve(ctx.cwd, params.cwd ?? ".");
      const fail = (text: string) => ({ content: [{ type: "text" as const, text }], details: { harness: params.harness, cwd }, isError: true });
      if (where.refused) return fail(`delegate: ${where.refused}, so ${params.harness} does not run there`);
      const prompt = `Task: ${params.task}`;
      const tmp = params.harness === "codex" ? fs.mkdtempSync(path.join(os.tmpdir(), "pi-delegate-")) : undefined;
      try {
        const last = tmp && path.join(tmp, "last-message.md");
        const r = params.harness === "claude"
          ? await run("claude", ["-p", prompt, "--output-format", "json"], cwd, signal ?? ctx.signal)
          : await run("codex", ["exec", "-s", "workspace-write", "-C", cwd, "-o", last!, prompt], cwd, signal ?? ctx.signal);
        if (r.error?.code === "ENOENT") return fail(`delegate: ${params.harness} is not on PATH, so it cannot run here`);
        if (r.error) return fail(`delegate: could not start ${params.harness} (${r.error.message})`);
        if (r.aborted) return fail(`delegate: stopped ${params.harness} (aborted)`);
        const stderr = r.stderr.trim().split("\n").slice(-20).join("\n");
        let text = "";
        let isError = r.code !== 0;
        let costUsd: number | undefined;
        if (params.harness === "claude") {
          try {
            const j = JSON.parse(r.stdout);
            text = String(j.result ?? "");
            isError ||= Boolean(j.is_error);
            if (typeof j.total_cost_usd === "number") costUsd = j.total_cost_usd;
          } catch {
            text = r.stdout.trim();
            isError = true;
          }
        } else {
          try { text = fs.readFileSync(last!, "utf8").trim(); } catch { /* Codex wrote no last message */ }
        }
        if (isError) text = `${params.harness} exited with ${r.code}${text ? `:\n${text}` : ""}${stderr ? `\n--- stderr ---\n${stderr}` : ""}`;
        if (costUsd !== undefined) text += `\n\n(Claude Code の費用の見積もり: $${costUsd.toFixed(4)}。サブスクリプションでは API 料金に換算した目安で、請求額ではない)`;
        return { content: [{ type: "text", text: cut(text || "(no answer)") }], details: { harness: params.harness, cwd, exitCode: r.code, costUsd }, isError };
      } finally {
        if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
      }
    },
  });
}
