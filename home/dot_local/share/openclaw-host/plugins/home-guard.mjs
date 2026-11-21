// OpenClaw のファイル操作とシェルを ~ の中に限り、鍵の置き場は読ませず、安全装置 (ゲート・自分の設定) は書かせない。
// 本人の指示 (2026-11-21「~/配下には権限与えたい」)。OpenClaw の workspaceOnly の代わりにこの判定を使う。
import { realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const HOME = realpathSync(homedir());
const WORK = join(HOME, ".local/share/openclaw-host/workspace");
// 読むことも書くことも断る (~ からの相対)。鍵・ログイン・ブラウザのクッキー・OpenClaw 自身の認証。
export const SECRET = [".ssh", ".gnupg", ".pki", ".password-store", ".netrc", ".aws", ".kube", ".docker/config.json",
  ".config/op", ".config/gh/hosts.yml", ".codex/auth.json", ".claude/.credentials.json", ".pi/agent/auth.json",
  ".pi/agent/mcp-auth.json", ".local/state/openclaw-host", ".local/share/keyrings", ".config/google-chrome",
  ".config/chromium", ".config/BraveSoftware", ".mozilla", ".config/Slack", ".config/discord"];
// 書くことだけ断る。ゲート・フック・権限の設定と、OpenClaw 自身の設定 (自分で権限を広げられないように)。
export const CONTROL = [".pi/agent/extensions", ".pi/agent/settings.json", ".claude/settings.json",
  ".claude/settings.local.json", ".claude/hooks", ".codex/config.toml", ".codex/hooks", ".config/openclaw-host",
  ".local/share/openclaw-host/plugins", ".local/share/openclaw-host/node_modules", ".local/share/openclaw-host/package.json",
  ".config/systemd", ".config/agents", ".local/share/chezmoi/home/dot_pi/agent/extensions",
  ".local/share/chezmoi/home/dot_claude", ".local/share/chezmoi/home/private_dot_config/openclaw-host",
  ".local/share/chezmoi/home/dot_local/share/openclaw-host"];
const KEY_FILE = /(^|\/)(id_[a-z0-9]+|[^/]*\.(pem|key|p12|pfx|kdbx))$/i;
const WRITE_TOOLS = /^(write|edit|apply_patch|multiedit|move|rm|delete)/i;
const PATH_KEYS = ["path", "file_path", "filePath", "file", "paths", "target", "source", "destination", "cwd", "workdir"];

/** Resolve symlinks of the longest existing prefix so a link inside ~ cannot point at a secret. */
function real(p) {
  const abs = resolve(WORK, p.replace(/^~(?=\/|$)/, HOME));
  for (let head = abs, tail = ""; ; tail = join(head.slice(dirname(head).length + 1), tail), head = dirname(head)) {
    try { return join(realpathSync(head), tail); } catch { if (head === dirname(head)) return abs; }
  }
}

const under = (rel, list) => list.some((x) => rel === x || rel.startsWith(x + "/"));

/** Why a path must not be used, or undefined. `shell`: a path named in a command (outside ~ is allowed there). */
export function refuse(p, write, shell = false) {
  const rel = relative(HOME, real(p));
  if (rel.startsWith("..") || isAbsolute(rel)) return shell ? undefined : `${p}: ホーム (~) の外`;
  if (under(rel, SECRET) || KEY_FILE.test(rel)) return `${p}: 鍵や認証の置き場`;
  if (write && under(rel, CONTROL)) return `${p}: 安全装置や OpenClaw 自身の設定 (本人が変える)`;
}

/** Paths mentioned in a shell command: ~/x, $HOME/x and absolute paths. */
export function commandPaths(cmd) {
  return [...cmd.replaceAll("$HOME", HOME).replaceAll("${HOME}", HOME).matchAll(/(?:^|[\s'"=:<>|;&(])((?:~|\/)[^\s'"|;&<>()]*)/g)].map((m) => m[1]);
}

export default definePluginEntry({
  id: "home-guard",
  name: "Home guard",
  description: "Keep file and shell tools inside ~, away from secrets and control files",
  register(api) {
    api.on("before_tool_call", (event) => {
      const params = event?.params ?? {};
      const write = WRITE_TOOLS.test(event?.toolName ?? "");
      const paths = PATH_KEYS.flatMap((k) => [params[k]].flat()).filter((v) => typeof v === "string" && v);
      paths.push(...(event?.derivedPaths ?? []));
      const shell = typeof params.command === "string" ? commandPaths(params.command) : [];
      // シェルは何を書くか読めないので、鍵と安全装置の場所に触れるコマンドはまとめて断る
      const why = paths.map((p) => refuse(p, write)).find(Boolean) ?? shell.map((p) => refuse(p, true, true)).find(Boolean);
      return why ? { block: true, blockReason: `home-guard: ${why}` } : undefined;
    });
  },
});
