# グローバル運用ルール (Claude Code / Codex 共通)

<!-- 正本: dotfiles (chezmoi) の dot_agents/AGENTS.md → ~/.agents/AGENTS.md。
     Claude Code は ~/.claude/CLAUDE.md の @~/.agents/AGENTS.md で、Codex は同じ内容の ~/.codex/AGENTS.md で読む。
     ~ 側を直接編集せず、ソースを直して chezmoi apply する。説明は docs/agents-unified.md。 -->

見出しに「Claude Code のみ」「Codex のみ」とある節は、その道具だけに適用する。もう一方は読み飛ばす。

## 共通

- 上位モデル・追加課金・外部のモデル振り分けサービスはユーザーが明示したときだけ使う。
- 費用・精度・削減率・「ミスゼロ」などの数値は自分で測ったものだけ主張する。API の従量料金とサブスクリプション枠は別物。
- 変更に応じたテスト・lint・dry-run を実行する。
- 完了報告は「変更 / 実行した検証とその結果 / 未検証」を短く書く。未実行や失敗を成功と書かない。
- 秘密が要るコマンドは承認なしで `op-agent run --env-file ~/.config/agents/secrets.env -- <cmd>` で実行する (vault 'Agents' 限定)。無い秘密は本人に Agents vault への追加と secrets.env への参照追加を頼む。値は表示・保存・チャット出力しない。

## Claude Code のみ

<!-- 要確認: ~/.claude/settings.json の modelSettings は claude-opus-5-5 を effortLevel "high" にしている。下の「medium」と食い違う。 -->

- モデルと effort は既定 (Opus 5.5 / medium) のまま使う。
- subagent は `~/.claude/agents` で effort low。コードを書く作業 (実装・修正・テスト・リファクタ) は `coder` subagent (Sonnet 5.5 xhigh) に任せる。
- high 以上はユーザーが `/effort` で上げたときだけ。Fable 5.1 と /fast もユーザーが明示したときだけ使い、subagent の model にも指定しない。
- 利用枠は推測せず `/usage` で確認する。

## Codex のみ

<!-- 要確認: Claude Code には「コードを書く作業は `coder` subagent に任せる」があるが、旧 Codex 側には無かった。Codex にも同名の `coder` (~/.codex/agents/coder.toml, xhigh) はあるので、ここではユーザーが委任を頼んだときに使う扱いにした。自律で委任させるか決めてほしい。 -->

- モデルと reasoning effort は `~/.codex/config.toml` の既定のまま。

### 回答形式

<!-- 要確認: 旧 Claude 側には無く、旧 Codex 側だけにあった。Claude Code に広げると回答が短くなるので、決まるまで Codex のみにしている。 -->

- 結論→根拠→次の行動の順。不要な項目は省く。
- 一文40字以内、全体1000字以内。URLは字数から除外。
- セクションは最大5。箇条書きは各階層最大5項目。
- 階層は必要最小限。比較は表、関係や流れはMermaid。
- 詳細は依頼時に展開。判断に必要な不確実性は先に示す。

## セッションとメモリ

- セッションは Claude Code と Codex の間で共有されない。別の道具・別の会話へ渡すことは Linear のチケットか PR (本文・コメント) に書く。会話に残しただけで引き継げたとは扱わない。
- 長期メモリの正本は Claude の自動メモリ `~/.claude/projects/<リポジトリ>/memory/` (1 事実 1 ファイル + 索引 `MEMORY.md`)。Claude Code は自動で読む。
- Codex は作業の最初に `agent-memory-dir` を実行し、出たディレクトリの `MEMORY.md` を読む (無ければ飛ばす)。索引の各行のうち今の作業に関係するファイルを開き、書かれた方針 (feedback / project) に従う。メモリより現在のコードと本人の指示を優先し、古そうなら確かめる。
- Codex が覚えておくべきことを足すときは同じディレクトリに `<type>_<短い題>.md` を作る。frontmatter は `name` / `description` / `metadata` (`node_type: memory` と `type: user|feedback|project|reference`)、本文は事実と理由。そのうえで `MEMORY.md` に `- [題](ファイル名) — 一行の要約` を 1 行足す。索引は 200 行・25KB 以内。秘密・トークン・個人データは書かない。
- Codex 自身の memories (`~/.codex/memories`) は自動生成物で別物。手で書かない。

## 共有設定

- スキルは `~/.agents/skills`、MCP サーバーは `~/.agents/mcp.json` が正本。どちらも Claude Code と Codex に同じものが入る (追加方法は dotfiles の `docs/agents-unified.md`)。
- リポジトリに `AGENTS.md` と `CLAUDE.md` の両方があるときは、`CLAUDE.md` の先頭を `@AGENTS.md` にして中身を一つに保つ。
