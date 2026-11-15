/**
 * jev-router — the virtual model `jev/auto`: picks one of the four tiers in .chezmoidata/pi.yaml
 * (copied to ~/.pi/agent/model-tiers.json) for each message the owner writes. Approved by the owner
 * on 2026-11-15: Fable may be chosen without asking.
 *
 * Pi's own mechanism (docs/virtual-models.md, examples/extensions/jev-router.ts), with Pi's tiers:
 *   1. The owner names a model in the message (fable/ここぞ, opus, sol/gpt, haiku/軽量で): that tier.
 *   2. Otherwise the Jev classifier (TypeSafe) rates the message, with the tail of the last answer
 *      for context: light (lookups, status, trivial edits), standard (ordinary work), deep (strategy,
 *      architecture, system-wide design, hard debugging, security policy, or the owner says the work is
 *      going in circles) or continue (a short go-ahead such as "OK", "進めて", "反映して").
 *      deep -> peak, standard -> default, light -> light, continue -> the tier already in use.
 *      Going down needs a clear answer (DOWN_MIN); anything unclear stays on default or the current tier.
 *   3. No classifier (no key, timeout, error): the current tier, or default.
 * Tool follow-ups and retries stay on the model that handled the turn (prompt cache, thinking signatures),
 * and a retry never moves to another model. Requests outside the loop (compaction) use default.
 *
 * The virtual thinking level is a bias: low never picks peak, max picks peak more readily.
 * Decisions (tier, source, probabilities, never the text) go to ~/.pi/agent/jev-router.log.jsonl.
 * The TypeSafe key is read with op-agent only for a classifier call and never enters process.env.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const HOME = os.homedir();
const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || path.join(HOME, ".pi/agent");
const TIERS_FILE = path.join(AGENT_DIR, "model-tiers.json");
const LOG = path.join(AGENT_DIR, "jev-router.log.jsonl");
const TYPESAFE_REF_FILE = path.join(HOME, ".config/agents/model-typesafe.env");
const TYPESAFE_REF = /^TYPESAFE_API_KEY=(?:"(op:\/\/[^"]+)"|(op:\/\/\S+))\s*$/m;
const OP_AGENT = path.join(HOME, ".local/bin/op-agent");
const CLASSIFIER_TIMEOUT_MS = 6_000;
const USER_MAX = 6_000;
const CONTEXT_MAX = 1_500;
const DOWN_MIN = 0.6;
const PEAK_MIN: Record<string, number> = { high: 0.5, max: 0.35 };

type Tier = "default" | "strong" | "peak" | "light";
type TierSpec = { provider: string; id: string; thinking: string };
type State = { tier: Tier };
const TIER_NAMES: Tier[] = ["default", "strong", "peak", "light"];
const NAMES: Record<Tier, string> = { default: "既定", strong: "強め", peak: "ここぞ", light: "軽量" };

// The owner names a tier. Checked in this order, so "fable と opus" goes to peak.
const OVERRIDES: [Tier, RegExp][] = [
  ["peak", /fable|ここぞ/i],
  ["strong", /\bsol\b|\bgpt[-\s]?\d/i],
  ["default", /\bopus\b/i],
  ["light", /\bhaiku\b|軽量(?:モデル)?で/i],
];

function loadTiers(): Record<Tier, TierSpec> | undefined {
  try {
    const data = JSON.parse(fs.readFileSync(TIERS_FILE, "utf8"));
    return TIER_NAMES.every((t) => data?.[t]?.provider && data?.[t]?.id && data?.[t]?.thinking) ? data : undefined;
  } catch {
    return undefined;
  }
}

function text(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.flatMap((b: any) => (b?.type === "text" && typeof b.text === "string" ? [b.text] : [])).join("\n");
}

function lastText(messages: readonly any[], role: string): string {
  return text(messages.filter((m) => m?.role === role).at(-1)?.content);
}

function log(entry: Record<string, unknown>) {
  try {
    fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n");
  } catch { /* logging must never break a request */ }
}

let typesafeKey: Promise<string | undefined> | undefined;
function resolveTypesafeKey(): Promise<string | undefined> {
  if (process.env.TYPESAFE_API_KEY) return Promise.resolve(undefined); // Pi's registry reads it
  if (!typesafeKey) {
    const pending = new Promise<string | undefined>((resolve) => {
      let ref: string | undefined;
      try {
        const m = fs.readFileSync(TYPESAFE_REF_FILE, "utf8").match(TYPESAFE_REF);
        ref = m?.[1] ?? m?.[2];
      } catch { /* no reference on this host */ }
      if (!ref) return resolve(undefined);
      execFile(OP_AGENT, ["read", ref], { timeout: 15_000, maxBuffer: 64 * 1024 }, (err, stdout) => {
        resolve(err ? undefined : String(stdout).trim() || undefined);
      });
    });
    typesafeKey = pending;
    void pending.then((key) => { if (!key && typesafeKey === pending) typesafeKey = undefined; });
  }
  return typesafeKey;
}

type Rating = { probabilities: Record<string, number>; ms: number } | { why: string };

async function rate(ctx: any, userText: string, assistantText: string, current: Tier | undefined,
  signal?: AbortSignal): Promise<Rating> {
  const jev = ctx.modelRegistry.findOfType?.("classifier", "typesafe", "jev-latest");
  if (!jev) return { why: "classifier unavailable" };
  const started = Date.now();
  const controller = new AbortController();
  const stop = () => controller.abort();
  const timer = setTimeout(stop, CLASSIFIER_TIMEOUT_MS);
  signal?.addEventListener("abort", stop, { once: true });
  if (signal?.aborted) stop();
  const ended = new Promise<never>((_resolve, reject) => {
    if (controller.signal.aborted) return reject(new Error("ended"));
    controller.signal.addEventListener("abort", () => reject(new Error("ended")), { once: true });
  });
  try {
    const apiKey = await Promise.race([resolveTypesafeKey(), ended]);
    if (!apiKey && !process.env.TYPESAFE_API_KEY) return { why: "classifier unavailable" };
    const result = await Promise.race([ctx.modelRegistry.classify(jev, {
      state: {
        owner_message: userText.slice(0, USER_MAX),
        previous_answer_tail: assistantText.slice(-CONTEXT_MAX),
        current_tier: current ?? "none",
      },
      questions: { tier: {
        type: "choice",
        instructions: "A solo founder-engineer writes `owner_message` to a coding and thinking agent. " +
          "Which model tier should answer it? Judge the thinking the answer needs, not the length of the message.",
        criteria: {
          light: "Quick lookups, status checks, simple factual questions, short summaries, " +
            "trivial one-line edits or commands, and running an already decided routine step",
          standard: "Ordinary implementation, fixes, reviews, tool research and recommendations, config changes, " +
            "explanations, and multi-step work whose approach is clear",
          deep: "Business strategy, product or pricing decisions, architecture or cross-cutting design, " +
            "evaluating a whole system or UI, subtle or long-failing debugging, security or permission policy, " +
            "or the owner says the work is going in circles, is still broken, or asks for the deepest thinking",
          continue: "A short go-ahead, approval or acknowledgement (for example OK, yes, 進めて, 反映して, いいね) " +
            "that continues the work already under way",
        },
      } },
    }, { signal: controller.signal, apiKey }), ended]);
    const a = result?.answers?.tier;
    if (result?.stopReason !== "stop" || a?.type !== "choice") return { why: "classifier unavailable" };
    return { probabilities: a.probabilities ?? { [a.choice]: 1 }, ms: Date.now() - started };
  } catch {
    return { why: controller.signal.aborted ? "classifier timed out or was canceled" : "classifier unavailable" };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}

/** Tier for a rating: going up needs PEAK_MIN, going down needs DOWN_MIN; otherwise default (or stay). */
export function pick(p: Record<string, number>, current: Tier | undefined, level: string): Tier {
  const top = Object.entries(p).sort((a, b) => b[1] - a[1])[0]?.[0];
  if (top === "continue") return current ?? "default";
  const peakMin = PEAK_MIN[level];
  if (peakMin !== undefined && (p.deep ?? 0) >= peakMin) return "peak";
  if (top === "light" && (p.light ?? 0) >= DOWN_MIN) return "light";
  if (top === "light" || top === "standard" || top === "deep") return "default";
  return current ?? "default";
}

export default function (pi: ExtensionAPI) {
  const tiers = loadTiers();
  if (!tiers) return; // No tier data on this host: jev/auto is not offered.

  const model = (ctx: any, tier: Tier) => {
    const t = tiers[tier];
    const m = ctx.modelRegistry.find(t.provider, t.id);
    if (!m || (ctx.modelRegistry.hasConfiguredAuth && !ctx.modelRegistry.hasConfiguredAuth(m))) return undefined;
    return { model: m, thinkingLevel: t.thinking };
  };

  pi.registerVirtualModel<State>({
    provider: "jev",
    id: "auto",
    name: "Auto (Jev router)",
    thinkingLevels: ["low", "high", "max"],
    contextWindow: 1_000_000,
    maxTokens: 128_000,
    async route(request: any, ctx: any) {
      const fallback = model(ctx, "default");
      if (!fallback) throw new Error(`jev/auto: ${tiers.default.provider}/${tiers.default.id} has no credentials`);
      if (request.reason === "direct") return fallback;
      const sticky = request.reason === "retry" ? request.failed ?? request.previous : request.previous;
      if (request.reason !== "user" && sticky) return { model: sticky.model, thinkingLevel: sticky.thinkingLevel };

      const current = request.state?.tier as Tier | undefined;
      const userText = lastText(request.messages, "user");
      let tier: Tier | undefined;
      let source = "override";
      let probabilities: Record<string, number> | undefined;
      let ms: number | undefined;
      for (const [t, re] of OVERRIDES) if (re.test(userText)) { tier = t; break; }
      if (!tier) {
        const r = await rate(ctx, userText, lastText(request.messages, "assistant"), current, request.signal);
        if ("why" in r) {
          tier = current ?? "default";
          source = r.why;
        } else {
          tier = pick(r.probabilities, current, request.thinkingLevel);
          source = "classifier";
          probabilities = r.probabilities;
          ms = r.ms;
        }
      }
      if (tier === "peak" && request.thinkingLevel === "low") tier = "default";
      let route = model(ctx, tier);
      if (!route) { source += ` (${tier} unavailable)`; tier = "default"; route = fallback; }
      log({ tier, from: current ?? null, source, probabilities, ms, level: request.thinkingLevel });
      if (tier !== current && ctx.hasUI) {
        ctx.ui?.setStatus?.("jev-router", `auto→${NAMES[tier]}`);
        if (tier === "peak") ctx.ui?.notify?.(`jev/auto: ${tiers.peak.id} に上げます (${source})`, "info");
      }
      return tier === current ? route : { ...route, state: { tier } };
    },
  });
}
