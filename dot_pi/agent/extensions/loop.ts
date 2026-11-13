/** Session-local /loop. No subprocesses, gate changes, model routing, or automatic restart. */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";

const DEFAULT_INTERVAL = 10 * 60_000;
const DEFAULT_TASK = "Continue the user's already approved task, following current repository instructions. Make concrete progress and report what changed, verification, and blockers. Do not treat this extension-authored tick as fresh owner approval.";
const MAX_INTERVAL = 2_147_483_647; // Node's setTimeout upper bound; larger values become 1 ms.
type Request = {
  version: 1;
  sessionId: string;
  cwd: string;
  intervalMs: number;
  task: string;
  provider: string;
  model: string;
  thinkingLevel: string;
};

function validRequest(value: unknown): value is Request {
  const r = value as Request | undefined;
  return !!r && r.version === 1 && typeof r.sessionId === "string" && typeof r.cwd === "string"
    && Number.isInteger(r.intervalMs) && r.intervalMs >= 1000 && r.intervalMs <= MAX_INTERVAL
    && typeof r.task === "string" && !!r.task.trim() && r.task.length <= 4000
    && typeof r.provider === "string" && typeof r.model === "string" && typeof r.thinkingLevel === "string";
}

export default function (pi: ExtensionAPI) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  let active = false;
  let intervalMs = DEFAULT_INTERVAL;
  let task = DEFAULT_TASK;
  let ticks = 0;
  let nextAt: string | undefined;
  let reason = "not started";

  const state = () => ({ active, intervalMs, ticks, nextAt, reason });
  const show = (ctx: ExtensionContext) => {
    ctx.ui.setStatus("pi-loop", active
      ? `loop: ${ticks} · ${nextAt ? `next ${new Date(nextAt).toLocaleTimeString()}` : "working"}`
      : `loop: stopped (${reason})`);
  };
  const clear = () => {
    generation++;
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    nextAt = undefined;
  };
  const stop = (ctx: ExtensionContext, why: string) => {
    const wasActive = active;
    active = false;
    reason = why;
    clear();
    if (wasActive) pi.appendEntry("pi-loop-state", state());
    show(ctx);
    if (wasActive) ctx.ui.notify(`loop stopped: ${why}`, "warning");
  };
  const schedule = (ctx: ExtensionContext, delay: number) => {
    clear();
    if (!active) return;
    const token = generation;
    nextAt = new Date(Date.now() + delay).toISOString();
    timer = setTimeout(() => {
      if (!active || generation !== token) return;
      timer = undefined;
      nextAt = undefined;
      // Never steer or pile up follow-ups while the user, a tool, or compaction is busy.
      if (!ctx.isIdle() || ctx.hasPendingMessages()) {
        schedule(ctx, 1000);
        return;
      }
      try {
        ticks++;
        show(ctx);
        pi.appendEntry("pi-loop-state", state());
        pi.sendMessage({
          customType: "pi-loop-tick",
          content: `[Automatic loop tick ${ticks}; extension-authored, not new owner approval]\n${task}`,
          display: true,
        }, { triggerTurn: true });
      } catch {
        stop(ctx, "could not dispatch tick; no retry");
      }
      // Only agent_settled schedules the next cycle, measured from completion.
    }, delay);
    timer.unref();
    show(ctx);
  };
  const start = (ctx: ExtensionContext, interval: number, text: string) => {
    if (!["tui", "rpc"].includes(ctx.mode) || !ctx.isProjectTrusted()) {
      ctx.ui.notify("loop needs a trusted project and a persistent TUI or RPC session", "warning");
      return;
    }
    intervalMs = interval;
    task = text;
    ticks = 0;
    active = true;
    reason = "started by explicit request";
    pi.appendEntry("pi-loop-state", state());
    schedule(ctx, 0);
  };

  pi.registerCommand("loop", {
    description: "Repeat approved work: /loop start [10m] [task] | stop | status",
    getArgumentCompletions: prefix => ["start", "stop", "status"].filter(x => x.startsWith(prefix))
      .map(value => ({ value, label: value })),
    handler: async (args, ctx) => {
      const input = args.trim();
      if (!input || input === "status") {
        ctx.ui.notify(JSON.stringify(state()), "info");
        return;
      }
      if (input === "stop") {
        stop(ctx, "owner stopped");
        return;
      }
      const match = /^start(?:\s+(\d+)([smh]))?(?:\s+([\s\S]+))?$/.exec(input);
      const amount = match?.[1] ? Number(match[1]) : undefined;
      const interval = amount === undefined ? DEFAULT_INTERVAL
        : amount * ({ s: 1000, m: 60_000, h: 3_600_000 }[match![2]] ?? 0);
      const text = match?.[3]?.trim() || DEFAULT_TASK;
      // Numeric-looking malformed durations must not silently become tasks.
      const malformedDuration = !match?.[1] && /^start\s+[-+\d.]/.test(input);
      if (!match || malformedDuration || !Number.isInteger(interval) || interval < 1000
        || interval > MAX_INTERVAL || text.length > 4000) {
        ctx.ui.notify("Usage: /loop start [positive integer + s/m/h] [task] | stop | status", "warning");
        return;
      }
      start(ctx, interval, text);
    },
  });

  // The model can inspect or stop the loop, never enable/re-enable it itself.
  pi.registerTool({
    name: "loop_control",
    label: "Loop Control",
    description: "Inspect or stop this session's loop. Cannot start one. Stop when work is complete or blocked.",
    parameters: Type.Object({ action: Type.Union([Type.Literal("status"), Type.Literal("stop")]) }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      if (params.action === "stop") stop(ctx, "task complete or blocked");
      return { content: [{ type: "text", text: JSON.stringify(state()) }], details: state() };
    },
  });

  pi.on("session_start", (event, ctx) => {
    show(ctx);
    // One-shot setup handoff for an owner-requested installation. Not auto-resume:
    // ordinary startup, switching, resuming, and forking never consume this request.
    if (event.reason !== "reload" || !ctx.isProjectTrusted() || !["tui", "rpc"].includes(ctx.mode)) return;
    const sessionId = ctx.sessionManager.getSessionId();
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(sessionId)) return;
    const requestPath = path.join(os.homedir(), ".local/state/pi-loop", `${sessionId}.json`);
    try {
      const value: unknown = JSON.parse(fs.readFileSync(requestPath, "utf8"));
      if (!validRequest(value) || value.sessionId !== sessionId || value.cwd !== ctx.cwd
        || value.provider !== ctx.model?.provider || value.model !== ctx.model?.id
        || value.thinkingLevel !== ctx.thinkingLevel) {
        ctx.ui.notify("loop start request does not match this session/project/model; not started", "warning");
        return;
      }
      fs.unlinkSync(requestPath); // Consume before dispatch; never replay after a reload or failure.
      start(ctx, value.intervalMs, value.task);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        ctx.ui.notify("loop start request could not be read; not started", "warning");
      }
    }
  });
  pi.on("agent_start", (_event, ctx) => { clear(); if (active) show(ctx); });
  pi.on("agent_settled", (event, ctx) => {
    if (event.aborted) stop(ctx, "run aborted");
    else if (active) schedule(ctx, intervalMs);
  });
  pi.on("message_end", (event, ctx) => {
    if (!active || event.message.role !== "assistant") return;
    if (["error", "aborted", "length"].includes(event.message.stopReason)) {
      stop(ctx, `assistant ${event.message.stopReason}; no automatic resend`);
      void ctx.abort(); // Cancel core retry/backoff too; no model or harness fallback.
    }
  });
  pi.on("tool_execution_end", (event, ctx) => {
    if (active && event.isError) stop(ctx, "tool failed or was denied; review before restarting");
  });
  pi.on("ui_prompt_start", (_event, ctx) => stop(ctx, "owner interaction required"));
  pi.on("session_tree", (_event, ctx) => stop(ctx, "branch changed"));
  pi.on("model_select", (_event, ctx) => stop(ctx, "model changed"));
  pi.on("thinking_level_select", (_event, ctx) => stop(ctx, "thinking level changed"));
  pi.on("session_shutdown", (_event, ctx) => stop(ctx, "session closed or reloaded"));
}
