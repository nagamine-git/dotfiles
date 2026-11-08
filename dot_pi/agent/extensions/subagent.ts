/**
 * subagent — Pi's official subagent tool, loaded from the running Pi's own copy of the example
 * (<package>/examples/extensions/subagent/index.ts), so a Pi update brings the matching version and
 * dotfiles keep no copy of it. Agents are ~/.pi/agent/agents/*.md, which agents-sync generates from
 * ~/.claude/agents/*.md. If the example is missing or fails to load, Pi starts without the tool and
 * says so at session start.
 */
import { type ExtensionAPI, getExamplesPath } from "@earendil-works/pi-coding-agent";
import * as path from "node:path";

export default async function (pi: ExtensionAPI) {
  let entry = "examples/extensions/subagent/index.ts";
  try {
    entry = path.join(getExamplesPath(), "extensions/subagent/index.ts");
    const { default: register } = await import(entry); // Pi's jiti loads it, .ts and Pi's own imports included
    await register(pi);
  } catch (e) {
    const why = `subagent: cannot load Pi's example ${entry}, so there is no subagent tool (${e instanceof Error ? e.message : e})`;
    pi.on("session_start", (_event, ctx) => { ctx.ui?.notify?.(why, "warning"); });
  }
}
