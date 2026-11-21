// node tests/openclaw-plugins.mjs — OpenClaw の自作プラグイン (home-guard, jev-route) の判定の試験。am5-itx の OpenClaw の SDK を使う。
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const host = join(homedir(), ".local/share/openclaw-host");
if (!existsSync(join(host, "node_modules/openclaw"))) {
  console.log("skip: OpenClaw is not installed on this host");
  process.exit(0);
}
// プラグインは openclaw/plugin-sdk を import するので、OpenClaw の node_modules から解決できる場所に置いて読む
const src = new URL("../home/dot_local/share/openclaw-host/plugins/", import.meta.url);
const tmp = mkdtempSync(join(host, ".plugin-test-"));
try {
  for (const name of ["home-guard.mjs", "jev-route.mjs"]) {
    writeFileSync(join(tmp, name), await (await import("node:fs/promises")).readFile(new URL(name, src)));
  }
  const guard = await import(pathToFileURL(join(tmp, "home-guard.mjs")));
  const route = await import(pathToFileURL(join(tmp, "jev-route.mjs")));
  const ok = (p, write = false, shell = false) => assert.equal(guard.refuse(p, write, shell), undefined, p);
  const no = (p, write = false, shell = false) => assert.ok(guard.refuse(p, write, shell), p);

  ok("~/.pi/agent/sessions"); ok("~/.herdr", true); ok("notes.md", true); ok("~/ghq/github.com/x/y.ts", true);
  no("/etc/passwd"); no("~/.ssh/id_ed25519"); no("~/ghq/k/server.pem"); no("~/.gnupg/pubring.kbx");
  no("~/.local/state/openclaw-host/x"); no("~/.config/google-chrome/Default/Cookies");
  for (const s of guard.SECRET) no("~/" + s);                    // every listed secret place is refused
  ok("~/.pi/agent/extensions/jev-gate.ts"); no("~/.pi/agent/extensions/jev-gate.ts", true);
  no("~/.config/openclaw-host/config.json", true); no("~/.local/share/openclaw-host/plugins/home-guard.mjs", true);
  ok("~/.local/share/openclaw-host/workspace/a.md", true);
  ok("/usr/bin/rg", false, true); no("~/.ssh/config", true, true); no("~/.pi/agent/settings.json", true, true);
  // a symlink inside ~ that points at a secret place is refused by its target
  const link = join(tmp, "to-ssh");
  symlinkSync(join(homedir(), ".ssh"), link);
  no(link + "/known_hosts");
  assert.deepEqual(guard.commandPaths('rg foo ~/.pi "$HOME/.ssh/x" /usr/bin'), ["~/.pi", homedir() + "/.ssh/x", "/usr/bin"]);

  assert.equal(route.stripRouteNotices("↪️ Model Fallback: a/b (selected c/d; selected model unavailable)\n\n本文"), "本文");
  assert.equal(route.stripRouteNotices("↪️ Model Fallback cleared: c/d (was a/b)\n本文"), "本文");
  const real = "↪️ Model Fallback: a/b (selected c/d; rate limit)\n本文";
  assert.equal(route.stripRouteNotices(real), real);              // a real fallback stays visible
  console.log("openclaw plugins: OK");
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
