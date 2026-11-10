/** Usage-aware delegation, not an automatic model/provider switch.
 * Reads only the existing cache reader and guarded model-route check. No auth files,
 * refresh probes, model requests, polling, API fallback, or checks at startup.
 */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { homedir } from "node:os";
import { join } from "node:path";

const TTL = 300; // Same five-minute freshness bound as claude-usage-cache; not a quota threshold.
const RULES = [
  "追加の delegate / subagent 並列化や任意の委譲の前に usage_status で利用枠を確認する。単独で済む作業は委譲せず、必要な部分だけを一度にまとめて渡す。",
  "振り分けは必要な機能・品質を先に決める。claude.ai コネクタ・Chrome・別ハーネスでの独立レビューは delegate claude、OS sandbox が必要なら delegate codex。この制約を残り枠だけで入れ替えない。",
  "両方で要件を満たせる任意の作業だけ、確認できた枠に余裕がある側を選ぶ。各時間窓を別々に見て、使用済みと残量を逆にしない。割合を同じ仕事量・金額と見なさず、不明・古い・欠けた窓を残量ありと推測しない。",
  "Claude の値は既存ヘッダーキャッシュの参考情報で、Claude Code のプラン内残量や Fable 固有枠の証明ではない。Codex は CLI アカウントの一般枠。Pi の直接呼出しと同じアカウント・課金経路か未確認なので、その枠として代用しない。",
  "利用枠の有効期限が過ぎたら usage_status で再確認する。確認不能なら任意の並列化を抑え、制約を伝える。必須機能や本人が指定したハーネスを勝手に変えない。",
  "現在のモデル・effort は維持する。Fable 等への昇格・effort 引き上げ・有料 API への切替は本人の明示が必要。サブスク枠と API 換算額を混同せず、利用枠の削減を未測定で主張しない。",
  "承認待ち・拒否・安全上の停止や版・認証・予算の検査を別ハーネスで回避しない。利用上限や実行失敗後の無断の再送・自動フォールバックもしない。",
];
const CAVEAT = "CC は参考のヘッダーキャッシュ（プラン内残量・Fable 固有枠は未確認）、Codex は CLI アカウントの一般枠。Pi 直接呼出しの残量・API 料金とは別。古い・不明の値から空き枠を推測しない。";

type Window = { used_percent: number; remaining_percent: number; resets_at: number | null; window_duration_mins?: number };
type Usage = { state: "cached" | "known" | "stale" | "unknown" | "blocked"; observed_at: number | null;
  expires_at: number | null; windows: Record<string, Window> };
type Result = { code: number; stdout: string; killed?: boolean; truncated?: boolean };
const unknown = (state: "unknown" | "blocked" = "unknown"): Usage => ({ state, observed_at: null, expires_at: null, windows: {} });
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const timestamp = (v: unknown): v is number => number(v) && v > 0 && Number.isFinite(new Date(v * 1000).getTime());
const now = () => Date.now() / 1000;
const aged = (v: Usage): Usage => v.expires_at !== null && now() >= v.expires_at ? { ...v, state: "stale" } : v;

function data(result: Result | undefined): Record<string, unknown> | undefined {
  if (!result || result.code !== 0 || result.killed || result.truncated) return;
  try { const d = JSON.parse(result.stdout); return record(d) ? d : undefined; } catch { return; }
}

function window(value: unknown, codex = false): Window | undefined {
  if (!record(value) || !number(value.used_percent) || value.used_percent > 100
      || !number(value.remaining_percent) || Math.abs(value.remaining_percent - (100 - value.used_percent)) > 0.00001
      || (value.resets_at != null && !timestamp(value.resets_at))) return;
  if (codex && (!Number.isSafeInteger(value.window_duration_mins) || (value.window_duration_mins as number) <= 0)) return;
  return { used_percent: value.used_percent, remaining_percent: value.remaining_percent,
    resets_at: (value.resets_at as number | null | undefined) ?? null,
    ...(codex ? { window_duration_mins: value.window_duration_mins as number } : {}) };
}

function observation(state: "cached" | "known" | "stale", at: unknown, windows: Record<string, Window>, expiry?: unknown): Usage {
  if (!number(at) || at === 0 || at > now() || !Object.keys(windows).length) return unknown();
  let expires = at + TTL;
  if (expiry !== undefined) {
    if (!number(expiry) || expiry > expires) return unknown();
    expires = expiry;
  }
  for (const w of Object.values(windows)) if (w.resets_at !== null) expires = Math.min(expires, w.resets_at);
  return { state: state === "stale" || now() >= expires ? "stale" : state,
    observed_at: at, expires_at: expires, windows };
}

function claudeUsage(result: Result | undefined): Usage {
  const d = data(result);
  if (!d || !["cached", "stale"].includes(String(d.state)) || !record(d.windows)) return unknown();
  const windows: Record<string, Window> = {};
  for (const key of ["5h", "7d"]) {
    if (d.windows[key] == null) continue;
    const w = window(d.windows[key]);
    if (!w) return unknown();
    windows[key] = w;
  }
  return observation(d.state as "cached" | "stale", d.fetched_at, windows, d.expires_at);
}

function describe(label: string, usage: Usage): string {
  const windows = Object.entries(usage.windows).map(([key, w]) => {
    const duration = w.window_duration_mins ? `${w.window_duration_mins}分` : key;
    const reset = w.resets_at === null ? "不明" : new Date(w.resets_at * 1000).toISOString();
    return `  ${duration}: 使用 ${w.used_percent}% / 残り ${w.remaining_percent}% / reset ${reset}`;
  });
  const at = usage.observed_at === null ? "不明" : new Date(usage.observed_at * 1000).toISOString();
  return [`${label}: ${usage.state} (観測 ${at})`, ...windows].join("\n");
}

function codexUsage(result: Result | undefined): Usage {
  if (result?.code === 78 && !result.killed && !result.truncated) return unknown("blocked");
  const d = data(result);
  if (!d || d.state !== "ready" || d.model_started !== false || d.thread_started !== false || d.paid_api_calls !== 0) return unknown();
  if (d.ordinary_usage_allowed === false) return unknown("blocked");
  if (d.ordinary_usage_allowed !== true || !record(d.quota) || d.quota.state !== "known" || d.quota.bucket !== "codex") return unknown();
  const windows: Record<string, Window> = {};
  for (const key of ["primary", "secondary"]) {
    if (d.quota[key] == null) continue;
    const w = window(d.quota[key], true);
    if (!w) return unknown();
    windows[key] = w;
  }
  const at = typeof d.checked_at === "string" ? Date.parse(d.checked_at) / 1000 : NaN;
  return observation("known", at, windows);
}

export default function (pi: ExtensionAPI) {
  let cached: { cwd: string; at: number; value: Usage } | undefined;
  let pending: { cwd: string; task: Promise<Usage> } | undefined;

  async function read(name: string, args: string[], ctx: ExtensionContext, signal?: AbortSignal): Promise<Result | undefined> {
    try {
      // Fixed paths/arguments, no prompts or raw errors. model-route bounds auth/version reads
      // at 2 x 10s and app-server at 20s, so its normal cleanup runs before our 45s ceiling.
      return await pi.exec(join(homedir(), ".local/bin", name), args,
        { cwd: ctx.cwd, signal, timeout: name === "model-route" ? 45000 : 3000, maxBuffer: 16384 });
    } catch { return; }
  }

  async function codex(ctx: ExtensionContext, force: boolean, signal?: AbortSignal): Promise<Usage> {
    if (pending?.cwd === ctx.cwd) return pending.task;
    if (!force && cached?.cwd === ctx.cwd && now() >= cached.at && now() - cached.at < TTL) {
      return aged(cached.value);
    }
    const task = read("model-route", ["check", "--workflow", "review"], ctx, signal).then(codexUsage);
    pending = { cwd: ctx.cwd, task };
    try {
      const value = await task;
      cached = { cwd: ctx.cwd, at: now(), value };
      return value;
    } finally { if (pending?.task === task) pending = undefined; }
  }

  async function collect(ctx: ExtensionContext, force = false, signal?: AbortSignal) {
    const [cc, cx] = await Promise.all([
      read("claude-usage-cache", ["--json"], ctx, signal).then(claudeUsage), codex(ctx, force, signal),
    ]);
    const s = pi.getSettings().compaction;
    const override = ctx.model ? s?.modelOverrides?.[`${ctx.model.provider}/${ctx.model.id}`] : undefined;
    const compaction = { enabled: s?.enabled !== false,
      reserveTokens: override?.reserveTokens ?? s?.reserveTokens ?? 16384,
      keepRecentTokens: override?.keepRecentTokens ?? s?.keepRecentTokens ?? 20000 };
    // Either source can expire while waiting for the other helper.
    const snapshot = { checked_at: now(), claude: aged(cc), codex: aged(cx), compaction };
    if (ctx.hasUI) ctx.ui.setStatus("usage-aware", `枠 CC:${snapshot.claude.state} Codex:${snapshot.codex.state} (取得時点; /usage)`);
    return snapshot;
  }

  pi.registerTool({
    name: "usage_status",
    label: "Usage status",
    description: "Claude/Codex の利用枠の参考情報を読み取り専用で確認する。モデル呼出しなし。Claude は既存キャッシュのみ、Codex は既存の版・認証検査を維持する。",
    promptSnippet: "委譲・並列化の前に利用枠を確認（推論・有料の更新プローブなし）",
    promptGuidelines: RULES,
    parameters: Type.Object({}),
    async execute(_id, _params, signal, _onUpdate, ctx) {
      const snapshot = await collect(ctx, false, signal);
      return { content: [{ type: "text", text: `${CAVEAT}\n${JSON.stringify(snapshot, null, 2)}` }], details: snapshot };
    },
  });

  pi.registerCommand("usage", {
    description: "利用枠の参考情報と autocompact を確認（モデル呼出しなし、Codex 再確認）",
    handler: async (_args, ctx) => {
      const snapshot = await collect(ctx, true);
      const c = snapshot.compaction;
      if (ctx.hasUI) ctx.ui.notify([
        describe("Claude 参考キャッシュ", snapshot.claude), describe("Codex CLI 一般枠", snapshot.codex),
        `autocompact: ${c.enabled ? "ON" : "OFF"} / reserve ${c.reserveTokens} / recent ${c.keepRecentTokens}`,
        CAVEAT,
      ].join("\n"), "info");
    },
  });
}
