# ホームディレクトリ (~) で起動したとき

ここはプロジェクトではなく $HOME (git 管理外)。全体ルールは ~/.claude/CLAUDE.md・~/.codex/AGENTS.md にある。

- dotfiles は chezmoi 管理。~ 配下の設定ファイルを直接編集せず、`~/.local/share/chezmoi` のソースを直して `chezmoi diff` → `chezmoi apply` で反映する。管理対象かは `chezmoi source-path <path>` で確認する。
- 新規プロジェクトは `~/ghq/github.com/<owner>/<repo>` に作る。~ 直下にファイルやディレクトリを作らない。一時ファイルは /tmp を使う。
- ~ 全体を再帰検索しない (巨大)。対象ディレクトリを絞ってから find / grep する。
- `~/.ssh` `~/.gnupg` や認証情報ファイル (`*credentials*`, `*.env` など) は読まない・表示しない。
- 削除・移動・上書きは対象を確認してから行う。
