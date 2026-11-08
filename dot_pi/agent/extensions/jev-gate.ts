/**
 * jev-gate — an auditable permission gate for Pi.
 *
 * Replaces the black-box "is this allowed?" decision with two transparent layers:
 *   1. Deterministic deny rules (mirror ~/.claude/hooks/injection-guard.sh and the
 *      settings.json deny list): remote-fetch|shell, outbound mail, 1Password secret
 *      reads, force push / hard reset, publish/delete. These never call a model.
 *   2. jev classifier (TypeSafe, via Pi's model registry) for the gray zone, asking
 *      {allow, confirm, deny} with probabilities. The TypeSafe key is read here with
 *      op-agent (reference in ~/.config/agents/model-typesafe.env) and passed only to
 *      the classifier call. It never enters process.env, so commands run by Pi's bash
 *      tool cannot read it with `env`. A TYPESAFE_API_KEY already in the env still works.
 *
 * Every decision is appended to ~/.pi/agent/jev-gate.log.jsonl so it can be audited
 * and later turned into labelled data. jev errors fail OPEN (allow + log) so the gate
 * never breaks the agent; deterministic denies still apply.
 *
 * A "confirm" verdict is asked in the UI. Without a UI (print / JSON mode) nobody can
 * be asked, so it is denied. JEV_GATE_MODE overrides this: ask | allow | deny.
 */
import { type ExtensionAPI, isToolCallEventType } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const LOG = path.join(os.homedir(), ".pi/agent/jev-gate.log.jsonl");
const GATED = new Set(["bash", "write", "edit"]);
const TYPESAFE_REF_FILE = path.join(os.homedir(), ".config/agents/model-typesafe.env");
const OP_AGENT = path.join(os.homedir(), ".local/bin/op-agent");

// Resolved once per Pi process, like Pi's own "!command" keys: a failure lasts until restart.
let typesafeKey: Promise<string | undefined> | undefined;
function resolveTypesafeKey(): Promise<string | undefined> {
  if (process.env.TYPESAFE_API_KEY) return Promise.resolve(undefined); // Pi's registry reads it
  typesafeKey ??= new Promise((resolve) => {
    let ref: string | undefined;
    try {
      ref = fs.readFileSync(TYPESAFE_REF_FILE, "utf8").match(/^TYPESAFE_API_KEY="?(op:\/\/[^"\s]+)"?\s*$/m)?.[1];
    } catch { /* no reference on this host: deterministic layer only */ }
    if (!ref) return resolve(undefined);
    execFile(OP_AGENT, ["read", ref], { timeout: 15_000, maxBuffer: 64 * 1024 }, (err, stdout) => {
      resolve(err ? undefined : String(stdout).trim() || undefined);
    });
  });
  return typesafeKey;
}

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
  const apiKey = await resolveTypesafeKey();
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
      { signal: ctx.signal, apiKey },
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
    void resolveTypesafeKey(); // Fetch early so the first gated call does not wait on op-agent.
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
      // Interactive (ctx.hasUI, Pi's own flag) -> ask the human. Headless/automation has
      // nobody to ask, so deny; JEV_GATE_MODE=allow opts a trusted run back into auto-allow.
      const mode = process.env.JEV_GATE_MODE ?? (ctx.hasUI ? "ask" : "deny");
      if (mode === "ask" && ctx.hasUI && ctx.ui?.confirm) {
        const ok = await ctx.ui.confirm("jev-gate", `Allow this ${kind}?\n${text.slice(0, 300)}`);
        log({ layer: "jev", tool: kind, text, decision: ok ? "allow" : "deny", via: "confirm->ask", confidence: j.confidence });
        if (!ok) return { block: true, reason: "jev-gate: denied at confirm prompt" };
        return;
      }
      if (mode === "allow") {
        log({ layer: "jev", tool: kind, text, decision: "allow", via: "confirm->auto", confidence: j.confidence });
        return;
      }
      // No UI (the default), JEV_GATE_MODE=deny or an unknown mode, or "ask" with no UI to ask in.
      const why = process.env.JEV_GATE_MODE && mode !== "ask" ? `JEV_GATE_MODE=${mode}` : "no UI to ask";
      log({ layer: "jev", tool: kind, text, decision: "deny", via: "confirm->deny", why, confidence: j.confidence });
      return { block: true, reason: `jev-gate: confirm verdict blocked (${why})` };
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
      if (!j) { ctx.ui.notify("jev unavailable (check ~/.config/agents/model-typesafe.env and op-agent)", "warn"); return; }
      ctx.ui.notify(`jev verdict: ${j.decision} (conf ${j.confidence?.toFixed?.(2)}) p=${JSON.stringify(j.probabilities)}`, "info");
    },
  });
}
