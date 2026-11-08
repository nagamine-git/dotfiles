/**
 * jev-gate — an auditable permission gate for Pi.
 *
 * Replaces the black-box "is this allowed?" decision with two transparent layers:
 *   1. Deterministic deny rules (mirror ~/.claude/hooks/injection-guard.sh and the
 *      settings.json deny list): remote-fetch|shell, outbound mail, 1Password secret
 *      reads, force push / hard reset, publish/delete. These never call a model.
 *   2. jev classifier (TypeSafe, via Pi's model registry) for the gray zone, asking
 *      {allow, confirm, deny} with probabilities. Needs TYPESAFE_API_KEY in the env.
 *
 * Every decision is appended to ~/.pi/agent/jev-gate.log.jsonl so it can be audited
 * and later turned into labelled data. jev errors fail OPEN (allow + log) so the gate
 * never breaks the agent; deterministic denies still apply.
 *
 * Headless behaviour for a "confirm" verdict is set by JEV_GATE_MODE:
 *   ask (default when a UI is present) | allow (default headless) | deny
 */
import { type ExtensionAPI, isToolCallEventType } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const LOG = path.join(os.homedir(), ".pi/agent/jev-gate.log.jsonl");
const GATED = new Set(["bash", "write", "edit"]);

// --- Deterministic rules (fast, no model call) ---------------------------------
const DENY_RULES: { re: RegExp; reason: string }[] = [
  { re: /(curl|wget|fetch)\b[^|]*\|\s*\b(bash|sh|zsh|python|perl|node)\b/, reason: "remote fetch piped to an interpreter (curl|bash class)" },
  { re: /\b(bash|sh|zsh|python|perl|node)\b\s+(-c\s)?[^&;]*[<$]\(\s*(curl|wget)/, reason: "executing a remotely fetched script" },
  { re: /(^|[;|&\s])(sendmail|mailx|ssmtp|swaks|mutt|mail)\s/, reason: "outbound mail (possible exfiltration)" },
  { re: /\bop\s+(item|read|signin|document)\b/, reason: "1Password personal secret read (use op-agent for the Agents vault)" },
  { re: /git\s+push\s+.*(--force|-f)\b/, reason: "git force push" },
  { re: /git\s+reset\s+--hard\s+origin\//, reason: "hard reset to origin" },
  { re: /\b(gh\s+repo\s+delete|npm\s+publish|pnpm\s+publish|yarn\s+publish|cargo\s+publish)\b/, reason: "publish/delete of a package or repo" },
];

function subject(event: any): { kind: string; text: string } {
  if (isToolCallEventType("bash", event)) return { kind: "bash", text: String(event.input.command ?? "") };
  if (isToolCallEventType("write", event)) return { kind: "write", text: String(event.input.path ?? "") };
  if (isToolCallEventType("edit", event)) return { kind: "edit", text: String(event.input.path ?? "") };
  return { kind: event.toolName, text: JSON.stringify(event.input ?? {}) };
}

function log(entry: Record<string, unknown>): void {
  try {
    fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n");
  } catch { /* never break the agent on a logging failure */ }
}

async function askJev(ctx: any, kind: string, text: string): Promise<
  { decision: "allow" | "confirm" | "deny"; probabilities?: Record<string, number>; confidence?: number } | null
> {
  const jev = ctx.modelRegistry.findOfType?.("classifier", "typesafe", "jev-latest");
  if (!jev) return null;
  try {
    const result = await ctx.modelRegistry.classify(
      jev,
      {
        state: { tool: kind, command_or_path: text.slice(0, 8000) },
        questions: {
          verdict: {
            type: "choice",
            instructions:
              "A personal dev agent (single-owner machine, trusted hosts) wants to run this. " +
              "Classify the risk of letting it run without asking the owner.",
            criteria: {
              allow: "Ordinary, reversible dev work: builds, tests, reads, git add/commit, local edits, scoped scripts",
              confirm: "Plausibly fine but worth a glance: deletes, moves, network calls, writes outside the repo, infra/config changes",
              deny: "Clearly dangerous or irreversible: destroying data, leaking secrets, hitting production, wide rm -rf",
            },
          },
        },
      },
      { signal: ctx.signal },
    );
    if (result.stopReason !== "stop") return null;
    const a = result.answers.verdict;
    if (a?.type !== "choice") return null;
    return { decision: a.choice as any, probabilities: a.probabilities, confidence: a.confidence };
  } catch {
    return null;
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_e, ctx) => {
    const jev = ctx.modelRegistry.findOfType?.("classifier", "typesafe", "jev-latest");
    ctx.ui?.notify?.(`jev-gate active · classifier: ${jev ? "jev-latest" : "UNAVAILABLE (deterministic only)"}`, "info");
  });

  pi.on("tool_call", async (event, ctx) => {
    if (!GATED.has(event.toolName)) return;
    const { kind, text } = subject(event);

    // 1) Deterministic deny
    for (const r of DENY_RULES) {
      if (r.re.test(text)) {
        log({ layer: "deterministic", tool: kind, text, decision: "deny", reason: r.reason });
        return { block: true, reason: `jev-gate (rule): ${r.reason}`, terminate: true };
      }
    }

    // 2) jev classifier
    const j = await askJev(ctx, kind, text);
    if (!j) {
      log({ layer: "jev", tool: kind, text, decision: "allow", note: "jev-unavailable-fail-open" });
      return; // fail open
    }

    if (j.decision === "deny") {
      log({ layer: "jev", tool: kind, text, decision: "deny", probabilities: j.probabilities, confidence: j.confidence });
      return { block: true, reason: `jev-gate: classified as deny (p=${JSON.stringify(j.probabilities)})` };
    }

    if (j.decision === "confirm") {
      // Interactive (ctx.hasUI, Pi's own flag) -> ask the human. Headless/automation
      // -> auto-allow (deterministic rules + jev "deny" remain the backstop).
      // Override with JEV_GATE_MODE.
      const mode = process.env.JEV_GATE_MODE ?? (ctx.hasUI ? "ask" : "allow");
      if (mode === "deny") {
        log({ layer: "jev", tool: kind, text, decision: "deny", via: "confirm->deny", confidence: j.confidence });
        return { block: true, reason: "jev-gate: confirm verdict blocked (JEV_GATE_MODE=deny)" };
      }
      if (mode === "ask" && ctx.ui?.confirm) {
        const ok = await ctx.ui.confirm("jev-gate", `Allow this ${kind}?\n${text.slice(0, 300)}`);
        log({ layer: "jev", tool: kind, text, decision: ok ? "allow" : "deny", via: "confirm->ask", confidence: j.confidence });
        if (!ok) return { block: true, reason: "jev-gate: denied at confirm prompt" };
        return;
      }
      log({ layer: "jev", tool: kind, text, decision: "allow", via: "confirm->auto", confidence: j.confidence });
      return;
    }

    log({ layer: "jev", tool: kind, text, decision: "allow", confidence: j.confidence });
  });

  // Manual probe: /jev-test <command>
  pi.registerCommand("jev-test", {
    description: "Classify a command with the jev gate without running it",
    handler: async (args, ctx) => {
      const text = (args || "").trim() || "rm -rf /tmp/does-not-exist";
      const hit = DENY_RULES.find((r) => r.re.test(text));
      if (hit) { ctx.ui.notify(`deterministic DENY: ${hit.reason}`, "warn"); return; }
      const j = await askJev(ctx, "bash", text);
      if (!j) { ctx.ui.notify("jev unavailable (check TYPESAFE_API_KEY)", "warn"); return; }
      ctx.ui.notify(`jev verdict: ${j.decision} (conf ${j.confidence?.toFixed?.(2)}) p=${JSON.stringify(j.probabilities)}`, "info");
    },
  });
}
