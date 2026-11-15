/**
 * jev-router — the virtual model `jev/auto`: for each message the owner writes it picks a model and an
 * effort among every Claude and GPT model Pi can call with a subscription.
 * Pi's own mechanism (docs/virtual-models.md, examples/extensions/jev-router.ts). Owner decisions,
 * 2026-11-15: Fable may be chosen without asking; the base is Opus 5.5 medium; Claude and GPT are treated
 * alike; the total score is intelligence^6 x cheapness^2 x speed^1; near ties are settled by silent A/B
 * tests judged by outcomes.
 *
 * 1. What the message needs. One call to the Jev classifier (TypeSafe) reads the message and the tail of
 *    the last answer:
 *      level   a score on five ordered levels: light (lookups, status), standard (ordinary work), hard (the
 *              approach is not obvious), deep (system-wide design, analysis) and critical (the highest
 *              stakes, going in circles). The score is the expected level, and CUTS make it one level.
 *      go      is the message only a go-ahead ("OK", "進めて", "反映して")? Then the work goes on where it
 *              is, at the level it had (critical goes one rung down: the decision is made). After a light
 *              exchange it is routed like any message.
 *      asked   only when the message names a model: does the owner ask for it, or is it the topic?
 *      failed, done, shipped   the outcome of the previous answer, see 5.
 * 2. The data. `model-radar` (systemd timer) writes ~/.pi/agent/model-scores.json: for each model and
 *    effort Artificial Analysis's Intelligence Index, cost per task and seconds per answer, the cost and
 *    seconds corrected by a benchmark run in Pi where one was needed, and the owner's factor per level.
 *    Each level needs a score (the floor), from the tiers in .chezmoidata/pi.yaml:
 *      light     the score of the light tier at its configured effort
 *      standard  the score of the default tier at its configured effort (the owner's base)
 *      hard      STEP more
 *      deep      more than the default model reaches at any effort
 *      critical  the best score of the peak model
 *    `scarce` in the tier file spares a model with a capped quota (Fable): its cost counts double and no
 *    effort above high is chosen, so critical is Fable high unless the owner writes "fable max".
 * 3. The choice. Among all models and efforts whose score reaches the floor, the highest
 *      (score x owner's factor)^6 / (cost^2 x seconds)          (weights from the tier file)
 *    A change of effort keeps the prompt cache; a change of model writes the whole conversation again
 *    (measured 2026-11-15: six changes of model read nothing from the cache, four changes of effort read
 *    all of it). So the model in use is left only when the other is SWITCH_MARGIN times better after the
 *    cost of writing the context there and back is added to its cost. A model whose context window is too
 *    small for the conversation is not a candidate (Pi would compact it).
 * 4. Silent A/B tests. Where the two best for a level are within AB_RATIO (what the owner's factor can
 *    turn around) and one of them has fewer than AB_ENOUGH judged answers, a session is given one of the
 *    two at random for that level, and keeps it. Nothing is announced.
 * 5. Outcomes. The owner's next message tells what the previous answer produced: `failed` (wrong, not
 *    working, redo), `done` (confirmed, accepted, built upon), `shipped` (merged, applied, published,
 *    adopted: a result in use). They are logged with the model, effort and level that answered, never with
 *    text. model-radar turns them into the owner's factor: results in use count double, failures count
 *    double against.
 * 6. A model the owner asks for by name (fable/ここぞ, opus, sol/gpt, haiku/軽量で) is used, and so is an
 *    effort written right after the name ("fable high", "Fable5.2medium"). Fable by name is at least deep.
 * 7. Quota. Every window this Pi's Anthropic subscription responses report counts: 5h and 7d for the account,
 *    7d_<x> for one model (Fable: 7d_oi). A window used ahead of its time makes what it holds dearer by
 *    (used / elapsed share)^2, up to PACE_MAX, so routing leans to the other provider before a cap. At 95% a
 *    model window leaves that model out, and the provider is left out while its subscription is used up: Claude at >=95% of either 5h/7d
 *    window as this Pi's own Anthropic subscription responses report it (never another CLI's cache), or an
 *    explicit subscription-cap error from either provider (for CAP_RETRY_MS: the error carries no reset).
 *    Missing headers or age do not end it: every high window must reset or report a newer low value. Only
 *    subscription models stand in; never a paid API key. With nothing left the request fails.
 * 8. No classifier (no key, timeout, error): the model and effort in use, or default; a name still decides.
 *    No score data: the level's own tier at its configured effort.
 *
 * Tool follow-ups and retries stay on the model that handled the turn (cache, thinking signatures). Only a
 * used-up subscription moves them: never an arbitrary failure, auth or safety stop, or cancellation.
 * Requests outside the loop (compaction) use default. The virtual thinking level is a bias: low stops at
 * hard, max lowers every cut by MAX_SHIFT. Decisions and outcomes go to ~/.pi/agent/jev-router.log.jsonl.
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
const SCORES_FILE = path.join(AGENT_DIR, "model-scores.json");
const LOG = path.join(AGENT_DIR, "jev-router.log.jsonl");
const QUOTA_FILE = path.join(AGENT_DIR, "jev-claude-quota.json");
const QUOTA_THRESHOLD = 0.95; // Owner's cutoff (2026-11-15), inclusive; not a classifier decision.
// After an explicit cap error with no reset time, a provider is tried again after this long.
const CAP_RETRY_MS = 60 * 60_000;
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
// The owner's formula (2026-11-15). The tier file's `weights` replace it.
const WEIGHTS = { intelligence: 6, cost: 2, speed: 1 };
// The owner's factor stays within 0.9..1.1 (model-radar), so it can turn a ratio of (1.1/0.9)^6 around:
// that is where a test can change the choice, and where one is run.
const AB_RATIO = (1.1 / 0.9) ** 6;
const AB_ENOUGH = 30;
const SWITCH_MARGIN = 2;
const WINDOW_SHARE = 0.8;
const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const LEVELS = ["light", "standard", "hard", "deep", "critical"] as const;

type Tier = "default" | "strong" | "peak" | "light";
type Level = (typeof LEVELS)[number];
type TierSpec = { provider: string; id: string; thinking: string };
/** A model the owner wants spared (a capped weekly quota): its cost counts `cost_factor` times, and no effort
 * above `max_effort` is chosen unless the owner writes it after the model's name. */
type Scarce = Record<string, { cost_factor?: number; max_effort?: string }>;
type Data = Record<Tier, TierSpec> & { weights?: Partial<typeof WEIGHTS>; scarce?: Scarce };
/** A model at an effort, with what is known about it. `write`: USD per 1M tokens written to the cache. */
type Arm = { key: string; provider: string; id: string; effort: string; score: number; cost: number; seconds: number;
  write: number; owner?: Record<string, { f?: number; n?: number }> };
/** `ab`: the arm ("provider/id:effort") this session was given for a level. `detour`: a provider is left out. */
type State = { model: string; effort: string; level?: Level; ab?: Record<string, string>; detour?: true };
const TIER_NAMES: Tier[] = ["default", "strong", "peak", "light"];
/** The tier a level belongs to, where there is no score data. */
const HOME: Record<Level, Tier> = { light: "light", standard: "default", hard: "default", deep: "peak", critical: "peak" };
const key = (m: { provider: string; id: string }) => `${m.provider}/${m.id}`;
const armId = (a: { key: string; effort: string }) => `${a.key}:${a.effort}`;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

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

let armsCache: { mtime: number; arms: Arm[] } = { mtime: -1, arms: [] };
/** Every model and effort in model-radar's file that has a score, a cost and seconds. Read again when it changes. */
function loadArms(): Arm[] {
  let mtime: number;
  try { mtime = fs.statSync(SCORES_FILE).mtimeMs; } catch { return []; }
  if (mtime === armsCache.mtime) return armsCache.arms;
  const arms: Arm[] = [];
  try {
    const d = JSON.parse(fs.readFileSync(SCORES_FILE, "utf8"));
    for (const [id, m] of Object.entries<any>(d?.models ?? {})) {
      if (typeof m?.provider !== "string" || m.in_pi === false) continue;
      const write = finite(m.price?.cache_write) ? m.price.cache_write : finite(m.price?.input) ? m.price.input * 1.25 : 0;
      for (const effort of EFFORTS) {
        const e = m.efforts?.[effort];
        if (!e || e.excluded || !finite(e.score) || !finite(e.cost) || !finite(e.seconds) || e.cost <= 0 || e.seconds <= 0) continue;
        arms.push({ key: `${m.provider}/${id}`, provider: m.provider, id, effort, score: e.score, cost: e.cost,
          seconds: e.seconds, write, owner: e.owner && typeof e.owner === "object" ? e.owner : undefined });
      }
    }
  } catch { /* an unreadable file is no data */ }
  armsCache = { mtime, arms };
  return arms;
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

type Outcome = { failed: number; done: number; shipped: number };
type Rating = { score: number; go: number; asked: number; outcome?: Outcome; ms: number } | { why: string };

/** The classifier's answers, or why there are none. Never throws and never waits past the timeout. */
async function rate(ctx: any, userText: string, assistantText: string, withName: boolean, withOutcome: boolean,
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
  if (withOutcome) {
    const about = WHO + "`previous_answer_tail` is the end of the agent's last answer. ";
    questions.failed = {
      type: "bool",
      instructions: about + "Does `owner_message` report that the agent's previous answer or the work it did FAILED?",
      criteria: {
        true: "The owner says the result is wrong, broken, not working, still failing, not what was asked, or must be " +
          "redone or reverted; reports an error or a bug in what the agent just did; repeats the same request because " +
          "it was not done; or shows frustration with the agent (for example: 違う, 動かない, 直ってない, そうじゃない, " +
          "まだ止まる, やり直して, 戻して)",
        false: "Anything else: approval, a go-ahead, a follow-up or additional request, a request for more detail or " +
          "another format, a question, a new topic, or a change of mind by the owner that is not the agent's failure",
      },
    };
    questions.done = {
      type: "bool",
      instructions: about + "Does `owner_message` confirm that the previous work produced a usable result?",
      criteria: {
        true: "The owner confirms the result works or is good, thanks the agent for it, accepts or adopts it, tells it " +
          "to ship, merge, apply, commit or publish it, or builds the next step directly on it (for example: " +
          "うまくいった, できた, いいね, ありがとう, OK, 反映して, マージして, それで進めて)",
        false: "No confirmation: a complaint or correction, a question that doubts the answer, or an unrelated new request",
      },
    };
    questions.shipped = {
      type: "bool",
      instructions: about + "Does `owner_message` put the result of the previous work to real use?",
      criteria: {
        true: "The owner tells the agent to merge, commit, push, deploy, apply, publish, release or send the result, " +
          "adopts it as the decision, or says it is now in use or has produced a business result such as a customer, " +
          "revenue or a release (for example: マージして, 反映して, 公開して, 送って, これで決定, リリースした)",
        false: "The result is not yet put to use: discussion, questions, more changes, a complaint, or a new topic",
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
    const p = (k: string) => (a[k]?.type === "bool" && typeof a[k].probability === "number" ? a[k].probability : undefined);
    const [failed, done, shipped] = [p("failed"), p("done"), p("shipped")];
    const outcome = failed !== undefined && done !== undefined && shipped !== undefined ? { failed, done, shipped } : undefined;
    return { score: a.level.score, go: a.go.probability, asked, outcome, ms: Date.now() - started };
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

/** The level for the classifier's score. The selector low stops at hard; max leans up. */
export function levelOf(score: number, selector: string): Level {
  const s = score + (selector === "max" ? MAX_SHIFT : 0);
  const level = LEVELS[CUTS.filter((cut) => s >= cut).length];
  return selector === "low" ? atMost(level, "hard") : level;
}

type Floor = { score: number; above?: boolean };
/** The score a level needs; `above` where it has to be passed, not only reached. */
function need(data: Data, arms: Arm[], level: Level): Floor | undefined {
  const at = (t: Tier) => arms.find((a) => a.key === key(data[t]) && a.effort === data[t].thinking)?.score;
  const best = (t: Tier) => {
    const scores = arms.filter((a) => a.key === key(data[t])).map((a) => a.score);
    return scores.length ? Math.max(...scores) : undefined;
  };
  const of = (score: number | undefined, above?: boolean) => (score === undefined ? undefined : { score, above });
  if (level === "light") return of(at("light"));
  if (level === "standard") return of(at("default"));
  if (level === "hard") return of(at("default") === undefined ? undefined : at("default")! + STEP);
  if (level === "deep") return of(best("default"), true);
  return of(best("peak"));
}
const reaches = (a: Arm, f: Floor) => (f.above ? a.score > f.score : a.score >= f.score);

/** The total score: (score x owner's factor)^6 / (cost^2 x seconds). `extra`: USD added to the cost. */
export function total(data: Data, a: Arm, level: Level, extra = 0): number {
  const w = { ...WEIGHTS, ...data.weights };
  const f = a.owner?.[level]?.f;
  return (a.score * (finite(f) && f > 0 ? f : 1)) ** w.intelligence / ((a.cost + extra) ** w.cost * a.seconds ** w.speed);
}

/** `model`: a window that holds one model only (Anthropic's 7d_oi on Fable's responses); else the whole provider. */
type QuotaWindow = { used: number; at: number; reset?: number; model?: string };
type Windows = Record<string, QuotaWindow>;
const QUOTA_WINDOWS = ["5h", "7d"];
// Anthropic's unified windows: 5h and 7d for the account, 7d_<x> for a model (Fable: 7d_oi, seen 2026-11-15).
const WINDOW_KEY = /^anthropic-ratelimit-unified-((?:5h|7d)(?:_[a-z0-9]+)?)-utilization$/;
const WINDOW_SECONDS: Record<string, number> = { "5h": 5 * 3600, "7d": 7 * 86400 };
// Pacing: a window used faster than its time passes makes what it holds dearer, by (used / elapsed share)^2,
// at most PACE_MAX. On pace or behind it costs nothing extra. 95% still leaves it out (QUOTA_THRESHOLD).
const PACE_MAX = 4;

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
    && /(?:usage|weekly|monthly)[ _]limit[ _](?:reached|exceeded)|you['’]ve (?:hit|reached) your (?:usage |weekly )?limit/i.test(error);
}

/** Only this Pi's confirmed Anthropic subscription responses may update the Claude windows. Missing windows
 * never mean zero. A high observation stays latched until its announced reset or a newer low reading;
 * age alone is not recovery. An explicit cap error carries no reset: the provider is left out for
 * CAP_RETRY_MS and then tried again (a provider that is left out sends no headers to watch).
 * No probes, timers, auth files, raw headers, messages or credentials are stored. */
class Quota {
  private windows: Windows = {};

  private read() {
    try {
      if (fs.statSync(QUOTA_FILE).size > 16_384) return;
      const d = JSON.parse(fs.readFileSync(QUOTA_FILE, "utf8"));
      if (d?.source !== "pi-anthropic-subscription-v1" || !d.windows || typeof d.windows !== "object") return;
      for (const [key, w] of Object.entries<any>(d.windows)) {
        if (!/^(?:(?:5h|7d)(?:_[a-z0-9]+)?|limit|openai)$/.test(key)) continue;
        if (!w || !finite(w.used) || w.used < 0 || w.used > 1 || !finite(w.at) || w.at <= 0 || w.at > Date.now()
          || (w.reset !== undefined && (!finite(w.reset) || w.reset <= 0))
          || (w.model !== undefined && (typeof w.model !== "string" || !/^[\w.-]{1,80}$/.test(w.model)))) continue;
        if (!this.windows[key] || w.at >= this.windows[key].at) {
          this.windows[key] = { used: w.used, at: w.at, ...(w.reset !== undefined ? { reset: w.reset } : {}),
            ...(w.model ? { model: w.model } : {}) };
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
    for (const name of Object.keys(headers)) {
      const key = WINDOW_KEY.exec(name)?.[1];
      if (!key) continue;
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

  /** `model`: the model whose response carried the windows; a suffixed window belongs to it. */
  observe(windows: Windows, model?: string) {
    if (!Object.keys(windows).length) return;
    this.read();
    for (const [key, w] of Object.entries(windows)) {
      const own = key.includes("_") && model ? { ...w, model } : w;
      if (!this.windows[key] || w.at >= this.windows[key].at) this.windows[key] = own;
    }
    if (this.windows.limit && QUOTA_WINDOWS.every((key) => windows[key] && windows[key].used < QUOTA_THRESHOLD
      && windows[key].at >= this.windows.limit.at)) {
      // A dated tombstone also clears an older cap held by another Pi process.
      this.windows.limit = { used: 0, at: Date.now() };
    }
    this.save();
  }

  /** An explicit subscription-cap error from a provider. */
  limit(provider: string) {
    this.read();
    const retry = { used: 1, at: Date.now(), reset: Math.ceil((Date.now() + CAP_RETRY_MS) / 1000) };
    if (provider === "openai") this.windows.openai = retry;
    // An existing high Claude window already tells when to resume: keep it.
    else if (provider === "anthropic" && !this.high().some((k) => k !== "openai")) this.windows.limit = retry;
    else return;
    this.save();
  }

  private live(w: QuotaWindow): boolean {
    return w.reset === undefined || Date.now() < w.reset * 1000;
  }

  private high(): string[] {
    return Object.entries(this.windows).filter(([, w]) => !w.model && w.used >= QUOTA_THRESHOLD && this.live(w)).map(([k]) => k);
  }

  /** Models whose own window is used up: { model id: window }. */
  modelsOut(): Record<string, string> {
    this.read();
    return Object.fromEntries(Object.entries(this.windows).filter(([, w]) => w.model && w.used >= QUOTA_THRESHOLD && this.live(w))
      .map(([k, w]) => [w.model!, k]));
  }

  /** How much dearer a model is for being ahead of its windows' pace: max over the provider's windows and its own. */
  pace(provider: string, model: string): number {
    if (provider !== "anthropic") return 1;
    let m = 1;
    for (const [key, w] of Object.entries(this.windows)) {
      const length = WINDOW_SECONDS[key.slice(0, 2)];
      if (!length || (w.model && w.model !== model) || w.reset === undefined || !this.live(w)) continue;
      const elapsed = Math.min(1, Math.max(0.05, 1 - (w.reset - Date.now() / 1000) / length));
      m = Math.max(m, Math.min(PACE_MAX, (w.used / elapsed) ** 2));
    }
    return m;
  }

  /** The windows that keep each provider out. `wasAway`: a lost cache on resume is not proof a detour can end. */
  blocked(wasAway = false): { anthropic: string[]; openai: string[] } {
    this.read();
    const high = this.high();
    const anthropic = high.filter((k) => k !== "openai");
    return { anthropic: anthropic.length ? anthropic : wasAway && !Object.keys(this.windows).length ? ["unknown"] : [],
      openai: high.filter((k) => k === "openai") };
  }
}

type Env = { ctx: any; arms: Arm[]; tokens: number; out: Set<string>; why: string[] };
type Choice = { key: string; effort: string; ab?: [string, string]; assigned?: string };

export default function (pi: ExtensionAPI) {
  const data = loadTiers();
  if (!data) return; // No tier data on this host: jev/auto is not offered.

  const find = (ctx: any, k: string) => {
    const i = k.indexOf("/");
    const m = ctx.modelRegistry.find(k.slice(0, i), k.slice(i + 1));
    return m && (!ctx.modelRegistry.hasConfiguredAuth || ctx.modelRegistry.hasConfiguredAuth(m)) ? m : undefined;
  };
  const tierOf = (k: string | undefined): Tier | undefined => TIER_NAMES.find((t) => key(data[t]) === k);
  /** States written before 2026-11-15 named a tier. */
  const norm = (s: any): State | undefined => (!s ? undefined : typeof s.model === "string" ? s
    : data[s.tier as Tier] ? { model: key(data[s.tier as Tier]), effort: s.effort, ...(s.level ? { level: s.level } : {}) } : undefined);

  const quota = new Quota();
  let pending: Windows | undefined;
  pi.on("after_provider_response", (event) => {
    // This event has no physical-model field. Stage ONLY parsed quota data, then confirm its provider.
    pending = event.status >= 200 && event.status < 300 ? quota.parse(event.headers) : undefined;
  });
  pi.on("provider_stream_event", (event, ctx) => {
    const windows = pending;
    pending = undefined;
    if (event.provider === "anthropic" && windows
      && subscription(ctx, ctx.modelRegistry.find(event.provider, event.model))) quota.observe(windows, event.model);
  });
  pi.on("message_end", (event, ctx) => {
    const m = event.message as any;
    if (m.role !== "assistant") return;
    pending = undefined;
    if ((m.provider === "anthropic" || m.provider === "openai") && usageLimit(m)
      && subscription(ctx, ctx.modelRegistry.find(m.provider, m.model))) quota.limit(m.provider);
  });

  /** What a decision is made on: the data, the size of the conversation, and the providers that are used up. */
  const env = (ctx: any, state?: State): Env => {
    const b = quota.blocked(Boolean(state?.detour));
    const out = new Set<string>();
    const why: string[] = [];
    for (const provider of ["anthropic", "openai"] as const) {
      const t = TIER_NAMES.map((n) => data[n]).find((n) => n.provider === provider);
      if (b[provider].length && t && subscription(ctx, ctx.modelRegistry.find(t.provider, t.id))) {
        out.add(provider);
        why.push(...b[provider]);
      }
    }
    const tokens = ctx.getContextUsage?.()?.tokens;
    const spent = quota.modelsOut();
    for (const [model, window] of Object.entries(spent)) why.push(`${model} ${window}`);
    const arms = loadArms().flatMap((a) => {
      if (spent[a.id]) return [];
      const s = data.scarce?.[a.id];
      if (s && EFFORTS.includes(s.max_effort ?? "") && EFFORTS.indexOf(a.effort) > EFFORTS.indexOf(s.max_effort!)) return [];
      const scarce = s && finite(s.cost_factor) && s.cost_factor > 0 ? s.cost_factor : 1;
      return [{ ...a, cost: a.cost * scarce * quota.pace(a.provider, a.id) }];
    });
    return { ctx, arms, tokens: finite(tokens) ? tokens : 0, out, why };
  };

  /** Never a paid API key in place of a subscription: other providers than the default's only with one. */
  const eligible = (e: Env, a: { key: string; provider: string }) => {
    if (e.out.has(a.provider)) return false;
    const m = find(e.ctx, a.key);
    if (!m || !(subscription(e.ctx, m) || (!e.out.size && a.provider === data.default.provider))) return false;
    return !(finite(m.contextWindow) && m.contextWindow > 0 && e.tokens > m.contextWindow * WINDOW_SHARE);
  };

  /** No score data: the level's own tier at its configured effort. */
  const byTier = (e: Env, level: Level, current?: string): Choice => {
    let home = HOME[level];
    if (home === "light" && current && current !== key(data.light)) home = "default"; // something is cached elsewhere
    for (const t of [home, "default", "strong"] as Tier[]) {
      if (eligible(e, { key: key(data[t]), provider: data[t].provider })) return { key: key(data[t]), effort: data[t].thinking };
    }
    throw new Error(e.out.size ? "jev/auto: the subscription is used up and no other subscription model is available (no API fallback)"
      : `jev/auto: ${key(data.default)} has no credentials`);
  };

  /** The best effort of one model for a level: the best total among those that reach it, else its best score. */
  const onModel = (e: Env, k: string, level: Level): Arm | undefined => {
    const own = e.arms.filter((a) => a.key === k);
    const floor = need(data, e.arms, level);
    const ok = floor ? own.filter((a) => reaches(a, floor)) : [];
    const top = (list: Arm[], f: (a: Arm) => number) => list.reduce<Arm | undefined>((b, a) => (!b || f(a) > f(b) ? a : b), undefined);
    return ok.length ? top(ok, (a) => total(data, a, level)) : top(own, (a) => a.score);
  };

  /** The model and effort for a level. `current`: the model in use. `assigned`: this session's A/B arm for the level. */
  const choose = (e: Env, level: Level, current?: string, assigned?: string): Choice => {
    const pool = e.arms.filter((a) => eligible(e, a));
    const floor = need(data, e.arms, level);
    if (!pool.length || !floor) return byTier(e, level, current);
    const t = (a: Arm, extra = 0) => total(data, a, level, extra);
    const ok = pool.filter((a) => reaches(a, floor)).sort((a, b) => t(b) - t(a));
    if (!ok.length) { // nothing reaches the level: the best score there is
      const best = pool.reduce((b, a) => (a.score > b.score || (a.score === b.score && t(a) > t(b)) ? a : b));
      return { key: best.key, effort: best.effort };
    }
    let pick = ok[0];
    let ab: [string, string] | undefined;
    const mine = assigned ? ok.find((a) => armId(a) === assigned) : undefined;
    const judged = (a: Arm) => a.owner?.[level]?.n ?? 0;
    if (mine) pick = mine;
    else if (ok[1] && t(ok[1]) * AB_RATIO >= t(ok[0]) && Math.min(judged(ok[0]), judged(ok[1])) < AB_ENOUGH) {
      ab = [armId(ok[0]), armId(ok[1])];
      pick = ok[Math.random() < 0.5 ? 0 : 1];
    }
    const given = mine || ab ? armId(pick) : undefined;
    const stay = current && pick.key !== current ? ok.find((a) => a.key === current) : undefined; // its best effort: ok is sorted
    // Leaving a model writes the conversation to the other's cache, and again on the way back.
    if (stay && !(t(pick, (e.tokens / 1e6) * (pick.write + stay.write)) > SWITCH_MARGIN * t(stay))) pick = stay;
    return { key: pick.key, effort: pick.effort, ab, assigned: given };
  };

  const canon = (s: State | undefined) => (s ? JSON.stringify([s.model, s.effort, s.level ?? null,
    Object.entries(s.ab ?? {}).sort(), s.detour ?? null]) : "");
  const short = (k: string) => k.slice(k.indexOf("/") + 1).replace(/^claude-/, "");

  function finish(request: any, ctx: any, e: Env, c: Choice, level: Level | undefined, source: string,
    extra: Record<string, unknown> = {}) {
    const m = find(ctx, c.key);
    if (!m) throw new Error(`jev/auto: ${c.key} is not available`);
    const old = norm(request.state);
    const ab = c.assigned && level ? { ...old?.ab, [level]: c.assigned } : old?.ab;
    const state: State = { model: c.key, effort: c.effort, ...(level ? { level } : {}),
      ...(ab && Object.keys(ab).length ? { ab } : {}), ...(e.out.size ? { detour: true as const } : {}) };
    log({ model: c.key, effort: c.effort, level: level ?? null, from: old?.model ?? null, source, ...extra,
      selector: request.thinkingLevel, reason: request.reason, ...(e.tokens ? { tokens: e.tokens } : {}),
      ...(c.ab ? { ab: c.ab } : {}), ...(e.why.length ? { quota: e.why } : {}),
      ...((pace) => (pace > 1 ? { pace: Math.round(pace * 100) / 100 } : {}))(quota.pace(m.provider, m.id)) });
    if (ctx.hasUI && (old?.model !== state.model || old?.effort !== state.effort || old?.detour !== state.detour)) {
      ctx.ui?.setStatus?.("jev-router", `auto→${short(c.key)} ${c.effort}${state.detour ? " (枠退避)" : ""}`);
      if (state.detour && !old?.detour) {
        ctx.ui?.notify?.(`jev/auto: 利用枠 (${e.why.join(", ")}) に達したので、${[...e.out].join("・")} を外して振り分けます。`, "warning");
      } else if (old?.detour && !state.detour) {
        ctx.ui?.notify?.("jev/auto: 利用枠の回復を確認したので、通常の振り分けに戻ります。", "info");
      }
    }
    const route = { model: m, thinkingLevel: c.effort };
    if (request.reason === "direct") return route;
    return typeof request.state?.model === "string" && canon(old) === canon(state) ? route : { ...route, state };
  }

  pi.registerVirtualModel<State>({
    provider: "jev",
    id: "auto",
    name: "Auto (Jev router)",
    thinkingLevels: ["low", "high", "max"],
    contextWindow: 1_000_000,
    maxTokens: 128_000,
    async route(request: any, ctx: any) {
      const fallback = find(ctx, key(data.default));
      if (!fallback) throw new Error(`jev/auto: ${key(data.default)} has no credentials`);
      const old = norm(request.state);
      const e = env(ctx, old);
      if (request.reason === "direct") {
        if (!e.out.has(data.default.provider)) return { model: fallback, thinkingLevel: data.default.thinking };
        return finish(request, ctx, e, choose(e, "standard"), "standard", "direct");
      }
      const sticky = request.reason === "retry" ? request.failed ?? request.previous : request.previous;
      if (request.reason !== "user" && sticky) {
        const provider = sticky.model.provider;
        const cap = request.reason === "retry" && subscription(ctx, sticky.model) && usageLimit(sticky.message);
        if (cap) quota.limit(provider);
        const now = cap ? env(ctx, old) : e;
        // Only a used-up subscription moves a turn. Arbitrary failures (auth, safety, cancellation) never do.
        if (!request.signal?.aborted && (request.reason !== "retry" || cap) && now.out.has(provider)) {
          const level = old?.level ?? "standard";
          return finish(request, ctx, now, choose(now, level, undefined, old?.ab?.[level]), level,
            cap ? "subscription limit" : "continuation");
        }
        return { model: sticky.model, thinkingLevel: sticky.thinkingLevel };
      }

      // A session that came to jev/auto from another model has its cache there.
      const current = old?.model ?? (request.previous?.model ? key(request.previous.model) : undefined);
      const selector = request.thinkingLevel;
      const userText = lastText(request.messages, "user");
      const name = named(userText);
      const answered = old?.level ? old : undefined; // the answer before this message was routed here
      const r = await rate(ctx, userText, lastText(request.messages, "assistant"), Boolean(name), Boolean(answered), request.signal);
      if (!("why" in r) && r.outcome && answered) {
        log({ kind: "outcome", model: answered.model, effort: answered.effort, level: answered.level, ...r.outcome,
          ab: answered.ab?.[answered.level!] === armId({ key: answered.model, effort: answered.effort }) });
      }

      /** A tier's model at the effort written after its name, else its best for the level. */
      const tierChoice = (tier: Tier, lv: Level | undefined, effort?: string): Choice => {
        const k = key(data[tier]);
        if (!eligible(e, { key: k, provider: data[tier].provider })) return choose(e, lv ?? "standard", undefined, lv && old?.ab?.[lv]);
        return { key: k, effort: effort ?? (lv && onModel(e, k, lv)?.effort) ?? data[tier].thinking };
      };
      const usable = (k: string) => eligible(e, { key: k, provider: k.slice(0, k.indexOf("/")) });

      let c: Choice;
      let level: Level | undefined;
      let source: string;
      if ("why" in r) {
        source = r.why;
        if (name) {
          level = name.tier === "peak" ? "critical" : name.tier === "default" ? "standard" : name.tier === "light" ? "light" : undefined;
          c = tierChoice(name.tier, level, name.effort);
          source = `named (${r.why})`;
        } else if (current && usable(current)) {
          level = old?.level;
          const t = tierOf(current);
          c = { key: current, effort: old?.model === current ? old.effort : t ? data[t].thinking : request.previous?.thinkingLevel ?? "medium" };
        } else {
          level = old?.level ?? "standard";
          c = e.out.size ? choose(e, level) : { key: key(data.default), effort: data.default.thinking };
        }
      } else if (name && r.asked >= ASKED_MIN) {
        const rated = levelOf(r.score, selector);
        level = name.tier === "peak" ? atLeast(rated, "deep") : name.tier === "default" ? atMost(rated, "hard")
          : name.tier === "light" ? "light" : rated;
        if (selector === "low") level = atMost(level, "hard");
        c = tierChoice(name.tier, level, name.effort);
        source = "named";
      } else if (r.go >= GO_MIN && current && old?.level && rank(old.level) >= rank("standard")) {
        // The work goes on where it is, at the level it had: one rung down from critical (the decision is made).
        level = atMost(old.level, selector === "low" ? "hard" : "deep");
        const floor = need(data, e.arms, level);
        const here = e.arms.filter((a) => a.key === current && floor && reaches(a, floor) && eligible(e, a))
          .sort((a, b) => total(data, b, level!) - total(data, a, level!))[0];
        if (here) c = { key: here.key, effort: here.effort };
        else if (usable(current) && !e.arms.some((a) => a.key === current)) c = { key: current, effort: old.effort }; // no data on it
        else c = choose(e, level, current, old.ab?.[level]); // it does not reach the level, or is used up
        source = "go-ahead";
      } else {
        level = levelOf(r.score, selector);
        c = choose(e, level, current, old?.ab?.[level]);
        source = "classifier";
      }
      const rating = "why" in r ? {} : { score: r.score, go: r.go, asked: name ? r.asked : undefined, ms: r.ms };
      return finish(request, ctx, e, c, level, source, rating);
    },
  });
}
