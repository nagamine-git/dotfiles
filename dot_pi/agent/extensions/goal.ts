/** Session-local /goal. The owner sets the goal; the model may only report it achieved. No scheduling. */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const ENTRY = "pi-goal";
const MAX = 2000;
type Status = "none" | "active" | "achieved" | "cleared";
type Goal = { goal?: string; status: Status; at?: string; evidence?: string; by?: "owner" | "model" };

function valid(data: any): data is Goal {
  return !!data && ["active", "achieved", "cleared"].includes(data.status)
    && typeof data.goal === "string" && !!data.goal.trim() && data.goal.length <= MAX;
}

export default function (pi: ExtensionAPI) {
  let current: Goal = { status: "none" };

  const show = (ctx: ExtensionContext) => ctx.ui.setStatus("pi-goal", current.status === "active"
    ? `goal: ${current.goal!.slice(0, 40)}` : current.status === "achieved" ? "goal: achieved" : undefined);
  const save = (ctx: ExtensionContext, next: Goal) => {
    current = { ...next, at: new Date().toISOString() };
    pi.appendEntry(ENTRY, current);
    show(ctx);
  };
  const restore = (ctx: ExtensionContext) => {
    current = { status: "none" };
    const branch = ctx.sessionManager.getBranch();
    for (let i = branch.length - 1; i >= 0; i--) {
      const e: any = branch[i];
      if (e.type === "custom" && e.customType === ENTRY) {
        if (valid(e.data)) current = { ...e.data };
        break;
      }
    }
    show(ctx);
  };
  const achieve = (ctx: ExtensionContext, by: "owner" | "model", evidence?: string) => {
    save(ctx, { goal: current.goal, status: "achieved", evidence, by });
    pi.events?.emit("pi-goal:achieved", { goal: current.goal, evidence, by });
    ctx.ui.notify(`goal achieved (${by}): ${current.goal}`, "info");
  };

  pi.registerCommand("goal", {
    description: "Owner goal for this session: /goal <text> | status | done | clear",
    getArgumentCompletions: prefix => ["status", "done", "clear"].filter(x => x.startsWith(prefix))
      .map(value => ({ value, label: value })),
    handler: async (args, ctx) => {
      const input = args.trim();
      if (!input || input === "status") {
        ctx.ui.notify(JSON.stringify(current), "info");
        return;
      }
      if (input === "clear") {
        if (current.status === "active") save(ctx, { goal: current.goal, status: "cleared", by: "owner" });
        ctx.ui.notify("goal cleared", "info");
        return;
      }
      if (input === "done") {
        if (current.status === "active") achieve(ctx, "owner");
        else ctx.ui.notify("no active goal", "warning");
        return;
      }
      if (input.length > MAX) {
        ctx.ui.notify(`goal must be at most ${MAX} characters`, "warning");
        return;
      }
      save(ctx, { goal: input, status: "active", by: "owner" });
      ctx.ui.notify(`goal set: ${input}`, "info");
    },
  });

  // The model can read the goal or report it achieved with evidence; it can never set or change it.
  pi.registerTool({
    name: "goal_control",
    label: "Goal Control",
    description: "Read the owner's session goal, or mark it achieved with concrete verified evidence. Cannot set or change the goal.",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("status"), Type.Literal("complete")]),
      evidence: Type.Optional(Type.String({ description: "What was done and how it was verified (required for complete)" })),
    }),
    async execute(_id, params: any, _signal, _onUpdate, ctx) {
      if (params?.action === "complete") {
        if (current.status !== "active") throw new Error("no active goal to complete");
        const evidence = typeof params.evidence === "string" ? params.evidence.trim() : "";
        if (!evidence || evidence.length > MAX) throw new Error("complete needs evidence (1-2000 characters)");
        achieve(ctx, "model", evidence);
      } else if (params?.action !== "status") {
        throw new Error("goal_control supports only status and complete");
      }
      return { content: [{ type: "text", text: JSON.stringify(current) }], details: current };
    },
  });

  pi.on("session_start", (_event, ctx) => restore(ctx));
  pi.on("session_tree", (_event, ctx) => restore(ctx));
  pi.on("before_agent_start", event => {
    if (current.status !== "active") return;
    return {
      systemPrompt: `${event.systemPrompt}\n\n<owner_goal>\n` +
        `The owner set this session goal with /goal: ${current.goal}\n` +
        "Work toward it within the owner's existing approvals and repository rules; the goal is not new approval " +
        "for publishing, spending, permissions or other new scope. When it is fully achieved and verified, call " +
        "goal_control with action complete and concrete evidence, then stop any running loop with loop_control.\n" +
        "</owner_goal>",
    };
  });
}
