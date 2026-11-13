/**
 * user-zsh — 本人が入力欄で打つ `!` / `!!` コマンドを zsh で実行し、Tab で zsh の補完候補を出す。
 *
 * - 実行: Pi の既定の bash の代わりに `zsh -ic` を使う。.zshrc のエイリアス・関数・PATH が使える。
 *   Pi のローカル実行 (createLocalBashOperations) を通すので、端末から切り離され (setsid) 標準入力も渡らない。
 *   対話の zsh が端末を掴んで Pi が止まる事故 (#33) は起きない。
 * - 対象は本人の `!` だけ。モデルが呼ぶ bash ツールは素の bash のままにする。jev-gate は
 *   「モデルの bash ではエイリアスが読まれない」ことを前提に拒否のルールを当てているため、それを崩さない。
 *   shellPath / shellCommandPrefix は bash ツールにも効くので使わない。
 * - 補完: 行が `!` で始まるときの Tab で ~/.local/bin/zsh-capture-completion を呼び、zsh の補完候補を一覧にする。
 *   それ以外の行は Pi の既定の補完 (ファイル・スラッシュコマンド) に任せる。
 */
import { type ExtensionAPI, createLocalBashOperations } from "@earendil-works/pi-coding-agent";
import type { AutocompleteItem } from "@earendil-works/pi-tui";
import { execFile } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

const CAPTURE = path.join(os.homedir(), ".local/bin/zsh-capture-completion");
const CAPTURE_TIMEOUT_MS = 3000;
const MAX_ITEMS = 200;

const quote = (s: string) => `'${s.replace(/'/g, `'\\''`)}'`;

// 対話の zsh の $FPATH (sheldon などで足した補完関数の場所)。初回の補完のときに 1 度だけ取る
let fpathPromise: Promise<string | undefined> | undefined;
function interactiveFpath(): Promise<string | undefined> {
  fpathPromise ??= new Promise((resolve) => {
    execFile("zsh", ["-ic", "print -r -- $FPATH"], { timeout: CAPTURE_TIMEOUT_MS, detached: true }, (err, stdout) => {
      resolve(err ? undefined : stdout.trim() || undefined);
    });
  });
  return fpathPromise;
}

async function zshCompletions(buffer: string, cwd: string, signal: AbortSignal): Promise<AutocompleteItem[]> {
  const fpath = await interactiveFpath();
  const env = { ...process.env, ...(fpath ? { FPATH: fpath } : {}) };
  return new Promise((resolve) => {
    execFile(
      "zsh",
      [CAPTURE, buffer],
      { cwd, env, timeout: CAPTURE_TIMEOUT_MS, signal, detached: true, maxBuffer: 1024 * 1024 },
      (_err, stdout) => {
        const seen = new Set<string>();
        const items: AutocompleteItem[] = [];
        for (const raw of (stdout ?? "").split("\n")) {
          const line = raw.replace(/\r$/, "");
          if (!line) continue;
          const sep = line.indexOf(" -- ");
          const value = sep >= 0 ? line.slice(0, sep) : line;
          const description = sep >= 0 ? line.slice(sep + 4) : undefined;
          if (!value || seen.has(value)) continue;
          seen.add(value);
          items.push({ value, label: value, description });
          if (items.length >= MAX_ITEMS) break;
        }
        resolve(items);
      },
    );
  });
}

export default function (pi: ExtensionAPI) {
  const local = createLocalBashOperations();

  pi.on("user_bash", () => ({
    operations: {
      exec: (command, cwd, options) => local.exec(`exec zsh -ic ${quote(command)}`, cwd, options),
    },
  }));

  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    let lastWasShell = false;
    ctx.ui.addAutocompleteProvider((current) => ({
      triggerCharacters: current.triggerCharacters,
      async getSuggestions(lines, line, col, options) {
        lastWasShell = false;
        const before = (lines[line] ?? "").slice(0, col);
        const m = line === 0 ? before.match(/^!!?(.*)$/s) : null;
        if (!m || !options.force) return current.getSuggestions(lines, line, col, options);
        const buffer = m[1] ?? "";
        const prefix = buffer.match(/(\S*)$/)?.[1] ?? "";
        const items = await zshCompletions(buffer, ctx.cwd, options.signal);
        if (items.length === 0) return null;
        lastWasShell = true;
        return { prefix, items };
      },
      applyCompletion(lines, line, col, item, prefix) {
        if (!lastWasShell) return current.applyCompletion(lines, line, col, item, prefix);
        const text = lines[line] ?? "";
        const start = col - prefix.length;
        // ディレクトリは続けて Tab できるよう空白を足さない
        const insert = item.value.endsWith("/") ? item.value : `${item.value} `;
        const next = [...lines];
        next[line] = text.slice(0, start) + insert + text.slice(col);
        return { lines: next, cursorLine: line, cursorCol: start + insert.length };
      },
      shouldTriggerFileCompletion(lines, line, col) {
        if (line === 0 && /^!/.test(lines[0] ?? "")) return true;
        return current.shouldTriggerFileCompletion?.(lines, line, col) ?? true;
      },
    }));
  });
}
