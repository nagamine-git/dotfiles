/**
 * jev-router — the virtual model `jev/auto`: for each message the owner writes it picks one of the four
 * tiers in .chezmoidata/pi.yaml and an effort. ~/.pi/agent/model-tiers.json carries the tiers and
 * Artificial Analysis's scores. Approved by the owner on 2026-11-15: Fable may be chosen without asking.
 * Pi's own mechanism (docs/virtual-models.md, examples/extensions/jev-router.ts), with Pi's tiers.
 *
 * 1. What the message needs. One call to the Jev classifier (TypeSafe) reads the message and the tail of
 *    the last answer:
 *      level  a score on five ordered levels: light (lookups, status), standard (ordinary work), hard (the
 *             approach is not obvious), deep (system-wide design, analysis) and critical (the highest
 *             stakes, going in circles). The score is the expected level, and CUTS make it one level.
 *      go     is the message only a go-ahead ("OK", "進めて", "反映して")? Then the work goes on where it
 *             is: on the light tier as it was; elsewhere at least at standard, and one rung down from
 *             critical, since the decision is made.
 *      asked  only when the message names a model: does the owner ask for it, or is it the topic?
 *    Measured on the owner's past messages (2026-11-15): four choices (light, standard, deep, continue)
 *    sent 30 of 120 to the peak model at its best effort; the five levels send 5 there.
 * 2. Artificial Analysis's Intelligence Index and cost per task, per model and effort. The daily
 *    `model-radar update` (systemd user timer) writes them to ~/.pi/agent/model-scores.json from AA's API;
 *    without it, the copy in the tier file (docs/model-radar/_state.json) is used. Each level needs a score:
 *      light     the score of the light tier at its configured effort
 *      standard  the score of the default tier at its configured effort (the owner's base: Opus 5.5 medium)
 *      hard      STEP more
 *      deep      more than the default model reaches at any effort
 *      critical  the best score of the peak model
 *    For each model, the cheapest effort that reaches it. New scores move the choice with no code change.
 * 3. Which model: the cheapest of the default and peak models that reaches the level, counting the cost of
 *    changing model. A change of effort keeps the prompt cache; a change of model writes the whole
 *    conversation again (measured 2026-11-15: all six changes of model in the logs read nothing from the
 *    cache, four changes of effort read all of it), so a change costs the context times the new model's
 *    cache-write price. Short conversations move to the cheaper model, long ones stay. Without costs, the
 *    level's own tier (standard and hard: default; deep and critical: peak).
 *      - a light message goes to the light tier only where nothing is cached yet (the first message, or a
 *        session that is there already); later it stays on the model in use, at its cheapest effort
 *      - the peak model is left only after LEAVE_PEAK_AFTER messages in a row that would leave it
 * 4. A model the owner asks for by name (fable/ここぞ, opus, sol/gpt, haiku/軽量で) is used, and so is an
 *    effort written right after the name ("fable high", "Fable5.2medium"). Fable by name is at least deep.
 *    Without the classifier the name alone decides, and Fable by name is critical.
 * 5. No classifier (no key, timeout, error): the tier and effort in use, or default.
 *
 * 6. Claude quota (owner-approved 2026-11-15): at >=95% in either observed 5h/7d window, divert Claude
 *    to Sol's subscription. Observe only this Pi's confirmed Anthropic subscription response headers;
 *    never substitute Claude Code/Codex CLI quota or enable paid API auth. Keep the task's intended level
 *    for effort selection and recovery. Missing headers or elapsed cache age do not end a detour: every
 *    high window must reset or report a newer low value. Resume normal routing on a new user turn.
 *
 * Tool follow-ups and retries normally stay on the model that handled the turn (cache, thinking signatures).
 * Quota may divert a tool follow-up or an explicit subscription-cap retry, never an arbitrary failure,
 * auth/safety stop, cancellation or a Sol failure. No custom retry loop. Compaction also respects quota.
 * The virtual thinking level is a bias: low never uses the peak model, max lowers every cut by MAX_SHIFT.
 * Decisions (tier, effort, level, source, score, never the text) go to ~/.pi/agent/jev-router.log.jsonl.
 * The TypeSafe key is read with op-agent only for a classifier call and never enters process.env.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const HOME_DIR = os.homedir();
const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || path.join(HOME_DIR, ".pi/agent");
const TIERS_FILE = path.join(AGENT_DIR, "model-tiers.json");
const LOG = path.join(AGENT_DIR, "jev-router.log.jsonl");
const RUNTIME_SCORES = path.join(AGENT_DIR, "model-scores.json");
const QUOTA_FILE = path.join(AGENT_DIR, "jev-claude-quota.json");
const QUOTA_THRESHOLD = 0.95; // Owner's cutoff (2026-11-15), inclusive; not a classifier decision.
const TYPESAFE_REF_FILE = path.join(HOME_DIR, ".config/agents/model-typesafe.env");
const TYPESAFE_REF = /^TYPESAFE_API_KEY=(?:"(op:\/\/[^"]+)"|(op:\/\/\S+))\s*$/m;
const OP_AGENT = path.join(HOME_DIR, ".local/bin/op-agent");
const CLASSIFIER_TIMEOUT_MS = 6_000;
const USER_MAX = 6_000;
const CONTEXT_MAX = 1_500;
// Where the classifier's score (0 = light … 4 = critical) passes from one level to the next.
const CUTS = [0.5, 1.5, 2.5, 3.5];
const MAX_SHIFT = 0.25;
const GO_MIN = 0.5;
const ASKED_MIN = 0.6;
const STEP = 5;
const LEAVE_PEAK_AFTER = 2;
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const LEVELS = ["light", "standard", "hard", "deep", "critical"] as const;

type Tier = "default" | "strong" | "peak" | "light";
type Level = (typeof LEVELS)[number];
type TierSpec = { provider: string; id: string; thinking: string };
type Scores = Record<string, Record<string, number | null>>;
type Data = Record<Tier, TierSpec> & { scores?: Scores; costs?: Scores; cache_write?: Record<string, number> };
type Plan = { tier: Tier; effort: string; level?: Level; below?: number };
// Keep the intended Claude route while physically on Sol, so a go-ahead after recovery can resume Fable.
type State = Plan & { claude?: Plan };
const TIER_NAMES: Tier[] = ["default", "strong", "peak", "light"];
const NAMES: Record<Tier, string> = { default: "既定", strong: "強め", peak: "ここぞ", light: "軽量" };
/** The tier a level belongs to. */
const HOME: Record<Level, Tier> = { light: "light", standard: "default", hard: "default", deep: "peak", critical: "peak" };

// A model the owner names. Checked in this order, so "fable と opus" is peak.
const NAMED: [Tier, RegExp][] = [
  ["peak", /fable|ここぞ/i],
  ["strong", /\bsol\b|\bgpt[-\s]?\d[\d.]*/i],
  ["default", /\bopus\b/i],
  ["light", /\bhaiku\b|軽量(?:モデル)?で/i],
];
// An effort right after the name and its version: "fable high", "Fable5.2medium", "opus-5-5 xhigh".
const EFFORT_AFTER = /^[\s\-_/:]*(?:\d+(?:[.-]\d+)*)?[\s\-_/:]*(low|medium|high|xhigh|max)(?![a-z])/i;

const WHO = "A solo founder-engineer writes `owner_message` to a coding and thinking agent. ";
const GO_AHEAD = "A short go-ahead, approval, pick among offered options, or acknowledgement (for example OK, yes, A で, " +
  "進めて, 反映して, いいね, ありがとう) that continues or closes the work already under way";
// One description for each of LEVELS, lowest first.
const LEVEL_CRITERIA = [
  "Quick lookups, status checks, simple factual questions, restating or summarizing what was said, " +
    "trivial one-line edits or commands, and running an already decided routine step",
  "Ordinary implementation, fixes with a known cause, reviews, tool research and recommendations, config changes, " +
    "explanations, and multi-step work whose approach is clear",
  "Work whose approach is not obvious: debugging without a known cause or after a fix that did not work, " +
    "changes that cut across several components, a design with trade-offs, security or permission policy, " +
    "a comparison of options that needs real analysis",
  "Architecture or system-wide design, evaluating or rethinking a whole system, product or UI, " +
    "business, market or product analysis, a diagnosis that must weigh many factors",
  "The highest-stakes thinking: which business or strategy to bet on, what the owner should work on, " +
    "a decision that is costly to reverse; or the owner says the work is going in circles, has failed repeatedly, " +
    "must be sharper, or asks for the deepest possible thinking",
];

function loadTiers(): Data | undefined {
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

type Rating = { score: number; go: number; asked: number; ms: number } | { why: string };

/** The classifier's answers, or why there are none. Never throws and never waits past the timeout. */
async function rate(ctx: any, userText: string, assistantText: string, withName: boolean,
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
  const questions: Record<string, unknown> = {
    level: {
      type: "score",
      instructions: WHO + "How much thinking does a good answer need? " +
        "Judge the thinking the answer needs, not the length of the message.",
      criteria: LEVEL_CRITERIA,
    },
    go: {
      type: "bool",
      instructions: WHO + "Is `owner_message` only a go-ahead for the work already under way?",
      criteria: { true: GO_AHEAD, false: "It asks for something new, changes the direction, or asks a question" },
    },
  };
  if (withName) {
    questions.asked = {
      type: "bool",
      instructions: WHO + "Does the owner ask that a particular model (for example Fable, Opus, Sol or GPT, Haiku) " +
        "answer this message or be consulted for it?",
      criteria: {
        true: "The owner tells the agent to use, call or consult a named model for this request " +
          "(for example: fable で, fable に聞いて, opus でお願い, haiku で要約)",
        false: "No model is named, or a model is only the topic of the message: its settings, price, tiers, " +
          "behaviour or whether to use it in general",
      },
    };
  }
  try {
    const apiKey = await Promise.race([resolveTypesafeKey(), ended]);
    if (!apiKey && !process.env.TYPESAFE_API_KEY) return { why: "classifier unavailable" };
    const result = await Promise.race([ctx.modelRegistry.classify(jev, {
      state: { owner_message: userText.slice(0, USER_MAX), previous_answer_tail: assistantText.slice(-CONTEXT_MAX) },
      questions,
    }, { signal: controller.signal, apiKey }), ended]);
    const a = result?.answers;
    if (result?.stopReason !== "stop" || a?.level?.type !== "score" || typeof a.level.score !== "number"
      || a?.go?.type !== "bool" || typeof a.go.probability !== "number") return { why: "classifier unavailable" };
    const asked = a.asked?.type === "bool" && typeof a.asked.probability === "number" ? a.asked.probability : 1;
    return { score: a.level.score, go: a.go.probability, asked, ms: Date.now() - started };
  } catch {
    return { why: controller.signal.aborted ? "classifier timed out or was canceled" : "classifier unavailable" };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}

const rank = (level: Level) => LEVELS.indexOf(level);
const atLeast = (level: Level, floor: Level): Level => (rank(level) < rank(floor) ? floor : level);
const atMost = (level: Level, ceiling: Level): Level => (rank(level) > rank(ceiling) ? ceiling : level);

/** The model the owner names in the message, and the effort written right after the name. */
export function named(message: string): { tier: Tier; effort?: string } | undefined {
  for (const [tier, re] of NAMED) {
    const m = re.exec(message);
    if (m) return { tier, effort: EFFORT_AFTER.exec(message.slice(m.index + m[0].length))?.[1].toLowerCase() };
  }
  return undefined;
}

/** The level for the classifier's score. The selector low stops at hard (no peak model); max leans up. */
export function levelOf(score: number, selector: string): Level {
  const s = score + (selector === "max" ? MAX_SHIFT : 0);
  const level = LEVELS[CUTS.filter((cut) => s >= cut).length];
  return selector === "low" ? atMost(level, "hard") : level;
}

/** The model for a level, before the hysteresis for leaving the peak model: the cheapest of the default
 * and peak models that reaches the level, counting the cost of changing model (`tokens` of context written
 * again at the new model's cache-write price). Without costs, the level's own tier. */
export function cheapest(data: Data, level: Level, current: Tier | undefined, tokens: number, allowPeak: boolean): Tier {
  // A light message goes to the light tier only where nothing large is cached on another model.
  if (level === "light" && (!current || current === "light")) return "light";
  const n = need(data, level);
  const options = (["default", "peak"] as Tier[]).filter((t) => t !== "peak" || allowPeak).map((tier) => {
    const effort = effortFor(data, tier, level);
    const score = scoreOf(data, data[tier].id, effort);
    const cost = costOf(data, data[tier].id, effort);
    const reaches = n !== undefined && score !== undefined && (n.above ? score > n.score : score >= n.score);
    const change = current && current !== tier && current !== "light" ? (tokens / 1e6) * (data.cache_write?.[data[tier].id] ?? 0) : 0;
    return { tier, score: score ?? -1, total: cost === undefined ? undefined : cost + change, reaches };
  });
  const home = allowPeak && level !== "light" ? HOME[level] : "default";
  const reaching = options.filter((o) => o.reaches);
  if (!reaching.length) {
    // Nothing reaches (or no scores): the best score, or the level's own tier.
    const scored = options.filter((o) => o.score >= 0).sort((a, b) => b.score - a.score);
    return n && scored.length ? scored[0].tier : home;
  }
  if (reaching.some((o) => o.total === undefined)) return reaching.some((o) => o.tier === home) ? home : reaching[0].tier;
  reaching.sort((a, b) => a.total! - b.total! || (a.tier === home ? -1 : 1));
  return reaching[0].tier;
}

function scoreOf(data: Data, id: string, effort: string): number | undefined {
  const v = data.scores?.[id]?.[effort];
  return typeof v === "number" ? v : undefined;
}

function costOf(data: Data, id: string, effort: string): number | undefined {
  const v = data.costs?.[id]?.[effort];
  return typeof v === "number" && v >= 0 ? v : undefined;
}

let runtimeMtime = -1;
/** Merge the daily AA snapshot (`model-radar update`) over the tier file's copy, when it changes. */
function refreshScores(data: Data) {
  let mtime: number;
  try { mtime = fs.statSync(RUNTIME_SCORES).mtimeMs; } catch { return; }
  if (mtime === runtimeMtime) return;
  runtimeMtime = mtime;
  try {
    const d = JSON.parse(fs.readFileSync(RUNTIME_SCORES, "utf8"));
    if (!d?.models || typeof d.models !== "object") return;
    for (const [id, m] of Object.entries<any>(d.models)) {
      const efforts = m?.efforts && typeof m.efforts === "object" ? m.efforts : {};
      const scores: Record<string, number> = {};
      const costs: Record<string, number> = {};
      for (const e of EFFORTS) {
        if (finite(efforts[e]?.score)) scores[e] = efforts[e].score;
        if (finite(efforts[e]?.cost)) costs[e] = efforts[e].cost;
      }
      if (!Object.keys(scores).length) continue;
      (data.scores ??= {})[id] = scores;
      (data.costs ??= {})[id] = costs;
      const write = m?.price?.cache_write ?? (finite(m?.price?.input) ? m.price.input * 1.25 : undefined);
      if (finite(write)) (data.cache_write ??= {})[id] = write;
    }
  } catch { /* keep what was loaded */ }
}

function bestOf(data: Data, id: string): number | undefined {
  const all = EFFORTS.flatMap((e) => scoreOf(data, id, e) ?? []);
  return all.length ? Math.max(...all) : undefined;
}

/** The score a level needs; `above` where it has to be passed, not only reached. */
function need(data: Data, level: Level): { score: number; above?: boolean } | undefined {
  const of = (score: number | undefined, above?: boolean) => (score === undefined ? undefined : { score, above });
  const standard = scoreOf(data, data.default.id, data.default.thinking);
  if (level === "light") return of(scoreOf(data, data.light.id, data.light.thinking));
  if (level === "standard") return of(standard);
  if (level === "hard") return of(standard === undefined ? undefined : standard + STEP);
  if (level === "deep") return of(bestOf(data, data.default.id), true);
  return of(bestOf(data, data.peak.id));
}

/** The lowest effort of the tier's model that reaches what the level needs: its best where none does,
 * the tier's configured effort where a score is missing or there is no level. */
export function effortFor(data: Data, tier: Tier, level: Level | undefined): string {
  const spec = data[tier];
  const known = EFFORTS.filter((e) => scoreOf(data, spec.id, e) !== undefined);
  const n = level && need(data, level);
  if (!n || !known.length) return spec.thinking;
  const score = (e: string) => scoreOf(data, spec.id, e) as number;
  const best = Math.max(...known.map(score));
  const reaching = known.filter((e) => (n.above ? score(e) > n.score : score(e) >= n.score));
  if (!reaching.length) return known.find((e) => score(e) === best)!;
  // The cheapest that reaches; in effort order where a cost is missing.
  const costs = reaching.map((e) => costOf(data, spec.id, e));
  if (costs.some((c) => c === undefined)) return reaching[0];
  return reaching[costs.indexOf(Math.min(...(costs as number[])))];
}

type QuotaWindow = { used: number; at: number; reset?: number };
type Windows = Record<string, QuotaWindow>;
const QUOTA_WINDOWS = ["5h", "7d"];
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Consult the registry's effective auth, not auth.json or a CLI's unrelated quota cache. */
function subscription(ctx: any, m: any): boolean {
  return Boolean(m && ctx.modelRegistry.isUsingOAuth?.(m) === true
    && ctx.modelRegistry.getProvider?.(m.provider)?.auth?.oauth?.isSubscription === true);
}

/** Only explicit subscription-cap errors qualify. A 429, overload, auth/billing/safety error never does. */
function usageLimit(message: any): boolean {
  const error = message?.errorMessage;
  return message?.stopReason === "error" && typeof error === "string"
    && !/auth|credential|billing|budget|payment|permission|forbidden|safety|policy|cancel|abort/i.test(error)
    && /(?:usage|weekly|monthly) limit (?:reached|exceeded)|you['’]ve (?:hit|reached) your (?:usage |weekly )?limit/i.test(error);
}

/** Only this Pi's confirmed Anthropic subscription responses may update this cache. Missing windows
 * never mean zero. A high observation stays latched until its announced reset or a newer low reading;
 * age alone is not recovery. A cap without a reset stays latched until both windows report low again.
 * No probes, timers, auth files, raw headers, messages or credentials are stored. */
class ClaudeQuota {
  private windows: Windows = {};

  private read() {
    try {
      if (fs.statSync(QUOTA_FILE).size > 16_384) return;
      const d = JSON.parse(fs.readFileSync(QUOTA_FILE, "utf8"));
      if (d?.source !== "pi-anthropic-subscription-v1" || !d.windows || typeof d.windows !== "object") return;
      for (const key of [...QUOTA_WINDOWS, "limit"]) {
        const w = d.windows[key];
        if (!w || !finite(w.used) || w.used < 0 || w.used > 1 || !finite(w.at) || w.at <= 0 || w.at > Date.now()
          || (w.reset !== undefined && (!finite(w.reset) || w.reset <= 0))) continue;
        if (!this.windows[key] || w.at >= this.windows[key].at) {
          this.windows[key] = { used: w.used, at: w.at, ...(w.reset !== undefined ? { reset: w.reset } : {}) };
        }
      }
    } catch { /* unavailable cache: do not erase an in-memory high observation */ }
  }

  private save() {
    const tmp = `${QUOTA_FILE}.${process.pid}.${Date.now()}.tmp`;
    try {
      fs.writeFileSync(tmp, JSON.stringify({ source: "pi-anthropic-subscription-v1", windows: this.windows }) + "\n", { mode: 0o600 });
      fs.renameSync(tmp, QUOTA_FILE);
    } catch { /* routing still uses the in-memory observation */ }
    finally { try { fs.unlinkSync(tmp); } catch { /* already renamed or never created */ } }
  }

  parse(headers: Record<string, string>): Windows {
    const windows: Windows = {};
    for (const key of QUOTA_WINDOWS) {
      const prefix = `anthropic-ratelimit-unified-${key}-`;
      const value = headers[prefix + "utilization"];
      if (typeof value !== "string" || !/^\d+(?:\.\d+)?$/.test(value)) continue;
      const used = Number(value);
      if (!finite(used) || used < 0 || used > 1) continue;
      const rawReset = headers[prefix + "reset"];
      const reset = typeof rawReset === "string" && /^\d+$/.test(rawReset) ? Number(rawReset) : undefined;
      windows[key] = { used, at: Date.now(), ...(finite(reset) && reset > 0 ? { reset } : {}) };
    }
    return windows;
  }

  observe(windows: Windows) {
    if (!Object.keys(windows).length) return;
    this.read();
    for (const [key, w] of Object.entries(windows)) {
      if (!this.windows[key] || w.at >= this.windows[key].at) this.windows[key] = w;
    }
    if (this.windows.limit && QUOTA_WINDOWS.every((key) => windows[key] && windows[key].used < QUOTA_THRESHOLD
      && windows[key].at >= this.windows.limit.at)) {
      // A dated tombstone also clears an older cap held by another Pi process.
      this.windows.limit = { used: 0, at: Date.now() };
    }
    this.save();
  }

  limit() {
    this.read();
    // An existing high window already tells us when to resume. Do not replace it with an indefinite cap.
    if (!this.blocked().length) {
      this.windows.limit = { used: 1, at: Date.now() };
      this.save();
    }
  }

  blocked(wasAway = false): string[] {
    this.read();
    const high = Object.entries(this.windows).filter(([, w]) => w.used >= QUOTA_THRESHOLD
      && (w.reset === undefined || Date.now() < w.reset * 1000)).map(([key]) => key);
    // A lost cache on resume is not proof that a detour can end.
    return high.length ? high : wasAway && !Object.keys(this.windows).length ? ["unknown"] : [];
  }
}

export default function (pi: ExtensionAPI) {
  const data = loadTiers();
  if (!data) return; // No tier data on this host: jev/auto is not offered.

  const model = (ctx: any, tier: Tier, effort: string) => {
    const t = data[tier];
    const m = ctx.modelRegistry.find(t.provider, t.id);
    if (!m || (ctx.modelRegistry.hasConfiguredAuth && !ctx.modelRegistry.hasConfiguredAuth(m))) return undefined;
    return { model: m, thinkingLevel: effort };
  };
  const tierOf = (m: any): Tier | undefined =>
    TIER_NAMES.find((t) => m && data[t].provider === m.provider && data[t].id === m.id);

  const quota = new ClaudeQuota();
  let pending: Windows | undefined;
  pi.on("after_provider_response", (event) => {
    // This event has no physical-model field. Stage ONLY parsed quota data, then confirm its provider.
    pending = event.status >= 200 && event.status < 300 ? quota.parse(event.headers) : undefined;
  });
  pi.on("provider_stream_event", (event, ctx) => {
    const windows = pending;
    pending = undefined;
    if (event.provider === "anthropic" && windows
      && subscription(ctx, ctx.modelRegistry.find(event.provider, event.model))) quota.observe(windows);
  });
  pi.on("message_end", (event, ctx) => {
    const m = event.message as any;
    if (m.role !== "assistant") return;
    pending = undefined;
    if (m.provider === "anthropic" && usageLimit(m)
      && subscription(ctx, ctx.modelRegistry.find(m.provider, m.model))) quota.limit();
  });

  const claude = TIER_NAMES.map((t) => data[t]).find((t) => t.provider === "anthropic");
  const blocked = (ctx: any, state?: State) => claude && subscription(ctx, ctx.modelRegistry.find(claude.provider, claude.id))
    ? quota.blocked(Boolean(state?.claude)) : [];
  const same = (a: Plan | undefined, b: Plan | undefined): boolean => a === b || Boolean(a && b
    && a.tier === b.tier && a.effort === b.effort && a.level === b.level && (a.below ?? 0) === (b.below ?? 0));

  function finish(request: any, ctx: any, plan: Plan, source: string, rating: Record<string, unknown> = {}) {
    const old = request.state as State | undefined;
    const quotaHigh = blocked(ctx, old);
    const high = data![plan.tier].provider === "anthropic" ? quotaHigh : [];
    if (quotaHigh.length && plan.tier === "strong" && !subscription(ctx, model(ctx, "strong", plan.effort)?.model)) {
      throw new Error("jev/auto: Claude quota >=95%; Sol subscription unavailable (no API or Claude fallback)");
    }
    let state: State = plan;
    if (high.length) {
      const sol = model(ctx, "strong", effortFor(data!, "strong", plan.level ?? "standard"));
      if (!sol || sol.model.provider !== "openai" || !/^gpt-.*sol$/i.test(sol.model.id) || !subscription(ctx, sol.model)) {
        // In particular, never turn a missing subscription into an API bill, or bounce back to Claude.
        throw new Error("jev/auto: Claude quota >=95%; Sol subscription unavailable (no API or Claude fallback)");
      }
      state = { tier: "strong", effort: sol.thinkingLevel, level: plan.level, below: 0, claude: plan };
      source += " (Claude quota)";
    }
    let route = model(ctx, state.tier, state.effort);
    if (!route) {
      if (quotaHigh.length) throw new Error("jev/auto: Claude quota >=95%; Sol subscription unavailable (no Claude fallback)");
      source += ` (${state.tier} unavailable)`;
      state = { tier: "default", effort: effortFor(data!, "default", plan.level ?? "standard"), level: plan.level, below: 0 };
      route = model(ctx, state.tier, state.effort);
      if (!route) throw new Error("jev/auto: default model has no credentials");
    }
    log({ tier: state.tier, effort: state.effort, level: state.level ?? null, from: old?.tier ?? null,
      source, ...rating, selector: request.thinkingLevel, reason: request.reason,
      ...(high.length ? { quota: high, intended: plan.tier } : {}) });
    if (ctx.hasUI && (old?.tier !== state.tier || old?.effort !== state.effort || Boolean(old?.claude) !== Boolean(state.claude))) {
      ctx.ui?.setStatus?.("jev-router", `auto→${NAMES[state.tier]} ${state.effort}${state.claude ? " (Claude枠退避)" : ""}`);
      if (state.claude && !old?.claude) {
        const quality = state.level && rank(state.level) >= rank("deep") ? " 深い判断は Fable 復帰後の再確認を推奨します。" : "";
        ctx.ui?.notify?.(`jev/auto: Claude の利用枠 (${high.join(", ")}) により ${data!.strong.id} へ退避します。${quality}`, "warning");
      } else if (old?.claude && !state.claude) {
        ctx.ui?.notify?.("jev/auto: Claude のリセット時刻または新しい利用率を確認し、通常の振り分けに戻ります。", "info");
      } else if (state.tier === "peak" && old?.tier !== "peak") {
        ctx.ui?.notify?.(`jev/auto: ${data!.peak.id} (${state.effort}) に上げます (${source})`, "info");
      }
    }
    if (request.reason === "direct") return route;
    return same(old, state) && same(old?.claude, state.claude) ? route : { ...route, state };
  }

  pi.registerVirtualModel<State>({
    provider: "jev",
    id: "auto",
    name: "Auto (Jev router)",
    thinkingLevels: ["low", "high", "max"],
    contextWindow: 1_000_000,
    maxTokens: 128_000,
    async route(request: any, ctx: any) {
      refreshScores(data);
      const fallback = model(ctx, "default", data.default.thinking);
      if (!fallback) throw new Error(`jev/auto: ${data.default.provider}/${data.default.id} has no credentials`);
      if (request.reason === "direct") {
        return blocked(ctx).length ? finish(request, ctx, { tier: "default", effort: data.default.thinking, level: "standard" }, "direct") : fallback;
      }
      const sticky = request.reason === "retry" ? request.failed ?? request.previous : request.previous;
      if (request.reason !== "user" && sticky) {
        const cap = request.reason === "retry" && sticky.model.provider === "anthropic"
          && subscription(ctx, sticky.model) && usageLimit(sticky.message);
        if (cap) quota.limit();
        // Arbitrary failed retries (including auth/safety/cancellation) NEVER change provider.
        // Sol continuations also stay on Sol, even after a reset; return to Claude on a new user turn.
        if (!request.signal?.aborted && (request.reason !== "retry" || cap)
          && sticky.model.provider === "anthropic" && blocked(ctx, request.state).length) {
          const plan = request.state?.claude ?? request.state ?? { tier: tierOf(sticky.model) ?? "default",
            effort: sticky.thinkingLevel, level: "standard", below: 0 };
          return finish(request, ctx, plan, cap ? "subscription limit" : "continuation");
        }
        return { model: sticky.model, thinkingLevel: sticky.thinkingLevel };
      }

      const state = (request.state?.claude ?? request.state) as Plan | undefined;
      // A session that came to jev/auto from a tier's model has its cache there.
      const current = state?.tier ?? tierOf(request.previous?.model);
      const selector = request.thinkingLevel;
      const userText = lastText(request.messages, "user");
      const name = named(userText);
      const r = await rate(ctx, userText, lastText(request.messages, "assistant"), Boolean(name), request.signal);

      let tier: Tier;
      let level: Level | undefined;
      let effort: string;
      let below = 0;
      let source: string;
      if ("why" in r) {
        source = r.why;
        if (name) {
          tier = name.tier;
          level = tier === "peak" ? "critical" : tier === "default" ? "standard" : tier === "light" ? "light" : undefined;
          effort = name.effort ?? effortFor(data, tier, level);
          source = `named (${r.why})`;
        } else {
          tier = current ?? "default";
          level = state?.level;
          effort = state?.tier === tier ? state.effort : data[tier].thinking;
          below = state?.below ?? 0;
        }
      } else if (name && r.asked >= ASKED_MIN) {
        const rated = levelOf(r.score, selector);
        tier = name.tier;
        level = tier === "peak" ? atLeast(rated, "deep") : tier === "default" ? atMost(rated, "hard")
          : tier === "light" ? "light" : undefined;
        effort = name.effort ?? effortFor(data, tier, level);
        source = "named";
      } else if (r.go >= GO_MIN) {
        // The work goes on where it is: on the light tier as it was (a thanks there is no reason to move),
        // elsewhere at least at standard, and one rung down from critical.
        level = current === "light" ? "light"
          : state?.level ? atMost(atLeast(state.level, "standard"), "deep") : state ? undefined : "standard";
        tier = current ?? HOME[level ?? "standard"];
        effort = level ? effortFor(data, tier, level) : state?.tier === tier ? state.effort : data[tier].thinking;
        below = state?.below ?? 0;
        source = "go-ahead";
      } else {
        level = levelOf(r.score, selector);
        const tokens = finite(ctx.getContextUsage?.()?.tokens) ? ctx.getContextUsage().tokens : 0;
        tier = cheapest(data, level, current, tokens, selector !== "low");
        // Hysteresis: leave the peak model only after LEAVE_PEAK_AFTER messages in a row that would leave it.
        if (current === "peak" && tier !== "peak" && (state?.below ?? 0) + 1 < LEAVE_PEAK_AFTER && selector !== "low") {
          tier = "peak";
          below = (state?.below ?? 0) + 1;
        }
        effort = effortFor(data, tier, level);
        source = "classifier";
      }
      if (selector === "low" && tier === "peak") {
        tier = "default";
        level = level ? atMost(level, "hard") : "standard";
        effort = effortFor(data, tier, level);
        below = 0;
      }
      const rating = "why" in r ? {} : { score: r.score, go: r.go, asked: name ? r.asked : undefined, ms: r.ms };
      return finish(request, ctx, { tier, effort, ...(level ? { level } : {}), below }, source, rating);
    },
  });
}
