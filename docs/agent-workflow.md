# Claude Code / Codex: 品質を確認しながらコストを抑える

2026-09-21確認。Linux / macOS共通。モデルやeffortを上げてもミスゼロは保証できない。
今回の設定は品質・費用のベンチマーク結果ではなく、比較しながら使うための初期設定。

## 導入と使い方

Claude Code >= 2.1.257、Codex CLI >= 0.155.1が必要。確認環境は2.1.273 / 0.155.1。
各サービスの既存ログインを利用する。プロキシや別サービスへのAPIキーは追加しない。
PRを取り込んだchezmoiソースで対象だけを確認・適用する（マシン整理のsetupは実行しない）。

```bash
chezmoi diff --recursive --parent-dirs -- ~/.local/bin/ai-code ~/.claude/CLAUDE.md ~/.claude/agents ~/.codex/AGENTS.md \
  ~/.codex/quality-standard.config.toml ~/.codex/quality-routine.config.toml \
  ~/.codex/quality-deep.config.toml ~/.codex/quality-review.config.toml ~/.codex/agents
chezmoi apply --parent-dirs --include=files,dirs -- ~/.local/bin/ai-code ~/.claude/CLAUDE.md ~/.claude/agents \
  ~/.codex/AGENTS.md ~/.codex/quality-standard.config.toml ~/.codex/quality-routine.config.toml \
  ~/.codex/quality-deep.config.toml ~/.codex/quality-review.config.toml ~/.codex/agents
```

`~/.codex/config.toml`、認証、Claudeのsettings・通知フックは上書きしない。
Codexの通常起動のmodel/effortは従来どおり。新設定は下記ランチャーか`--profile`で選ぶ。
グローバル作業規約とカスタムエージェントは通常起動でも読み込まれる。
反映後は新しいセッションで起動する（進行中の会話への再読込は保証しない）。
`AGENTS.override.md`があればCodexはそちらを優先する。独自のCODEX_HOME /
CLAUDE_CONFIG_DIRを使う場合、chezmoiの標準配備先から必要ファイルを別途配備する。

| 用途 | コマンド | モデル / effort |
|---|---|---|
| 自動判断で作業 | `ai-code claude` | 親 Opus / high → 必要時 Fable 5.1専門担当 |
| 親モデルの任意指定 | `ai-code claude deep` | Fable 5.1 / high |
| 親モデルの任意指定 | `ai-code claude routine` | Sonnet / medium |
| ファイルと検証記録のレビュー | `ai-code claude review` | Opus / xhigh |
| 自動判断で作業 | `ai-code codex` | 親 Sol / high → 必要時 Astra専門担当 |
| 親モデルの任意指定 | `ai-code codex deep` | GPT-6 Astra / high |
| 親モデルの任意指定 | `ai-code codex routine` | GPT-5.6 Terra / medium |
| Git差分のレビュー | `ai-code codex review --base main` | GPT-6 Astra / high |

Claudeのopus/sonnet aliasはproviderやローカルのalias上書きに依存する。
Codexのprofileは0.134以降の独立した`quality-*.config.toml`形式を使う。
プロジェクト設定や明示CLIオプションはprofileより優先する。起動時の実モデルも確認する。

```bash
ai-code claude 'この不具合を再現して修正して'       # 難易度の指定は不要
ai-code --dry-run codex '設計を確認して'             # 親の起動コマンド表示のみ・課金なし
ai-code codex exec 'この変更を実装して'
ai-code codex review --uncommitted                  # 未コミット差分
ai-code codex review --base main                    # ブランチ全体
ai-code claude review '指定したファイルとテスト記録をレビューして'
```

追加引数はネイティブCLIへそのまま渡す。presetは権限強制の仕組みではない。
Fable/Astraへのアクセス・課金条件は契約次第であり、インストールは利用権を保証しない。
利用不可や枠不足で別モデルへ自動再試行する機能は付けていない。Claude製品側の
安全判定などによるfallbackは別の機能なので、実モデルと通知を確認する。
Fableの非対話`-p`は契約によってusage creditsを確認なしで使うため、先に契約を確認する。

## 難易度はAIが判断する

ユーザーは`deep`などを選ばなくてよい。親が開始時と新しい証拠・失敗の後に
曖昧さ・影響範囲・危険・検証可能性を評価し、必要な専門担当へ自律的に委任する。
これはネイティブsubagentと作業規約を使った判断であり、親モデルの途中切替や
独立した難易度分類APIではない。CLI自体はpromptを採点しない。

| 状況 | 指示している動作 |
|---|---|
| 小さく明確な修正 | 親が実装・検証。分類用の追加呼出しなし |
| 切り出せる資料収集 | Sonnet / Terraのresearcherへ必要部分だけ委任 |
| 曖昧な設計、認証・課金・データ移行の変更、複数領域の原因不明障害 | 最初からFable / Astraのspecialistへ相談 |
| 同じ問題への修正が2回失敗 | 再現・試行をまとめてspecialistへ相談 |
| 親がすでにFable / Astra | 自分で再評価。同じモデルへの重複相談はしない |
| 委任禁止、モデル固定、予算制限、モデル利用不可 | 制約を尊重して未検証点を報告。勝手な降格・追加契約なし |

専門担当は設計・診断に絞り、親が回答を待って実装・テストを行う。
相談の理由は通知するが、ユーザーに難易度選択は求めない。仕様・権限について本当に
不足する情報は別途確認する。同時子担当は最大2件、難問相談は1件、子から再委任しない。
同じ根拠で相談を繰り返さず、専門担当でも未解決なら不足情報を報告する。

Codexのstandard profileでは`agents.enabled=true`、子担当ではfalseを指定する。
上位の管理設定・プロジェクト設定・明示CLI指定で無効なら自動委任はできない。
手動presetは親の選択であり、全担当のモデル固定ではない。モデル固定や委任禁止は
明示指示を優先する。review起動は検査専用なので、この自動相談の対象外。

判断はモデルへの指示であり、必ず正しく分類する保証や費用上限の強制ではない。
追加課金を有効化する設定は変更しないが、すでに有効な従量課金・usage creditsは
子担当でも消費し得る。アカウント側の利用上限は別途必要。
オフラインテストは配備・モデル設定・子の再委任無効化を検証する。
実際の判断精度、モデル利用権、費用は未測定で、`--dry-run`でも検証されない。

## 改善した点

- Claudeの既存agentファイルに必須の`name`・`description`を追加。欠けると現行版はファイルをスキップする。
- 実装はOpus/high、資料収集はSonnet/medium、レビューはOpus/xhigh。
  researcher/reviewerは許可toolを列挙し、Bash経由の書き込みも防ぐ。テスト実行は親担当。
- 難問相談のdeep-specialist (Fable 5.1/high) / dotfiles-specialist (Astra/high) を追加。
  親への「上位設定への切替を提案」ではなく、必要時に自律委任する規約へ変更。
- Codexにも専用agentを追加。profileでは同時子agentを2つまでに制限し、reviewは委任無効。
- 両方に合格条件、変更に応じたテスト、未検証の明記、失敗2回で再評価する規約を追加。
  これはモデルへの指示であり、CIの合格を強制するプログラムではない。
- Codex reviewのローカルfilesystemはCLIでread-onlyを指定。ただしMCPの外部書き込みや
  ユーザーによる明示overrideまで防ぐものではない。custom agentのsandboxも親のlive overrideが優先する。
- グローバルに大量のMCP、ローカル推論daemon、全タスクの多重レビューを追加しない。

## 引用された構成の検証

| 主張 | 確認結果と判断 |
|---|---|
| Fable 5.1 / Opus 5は実在する | 公式モデル仕様で確認。API単価とClaude Codeサブスクリプション枠は別物 |
| `effort="adaptive"` | 誤り。adaptiveはthinking方式。effortはlow/medium/high/xhigh/max等。Fable 5.1はadaptiveが常時有効 |
| JevをRX 9070で動かす | 公式quickstartはクラウドAPI。今回調べた一次資料で配布weights・ROCmローカル手順を確認できず、導入しない |
| Jevは絶対に誤らない | 型・schemaの保証と正しい判断は別。公式でもconfidenceで扱う設計。難易度scoreだけで降格しない |
| 高額モデルの呼出しを10%未満へ | この作業環境での根拠なし。ルーター精度・再試行・レビュー費用を含めた評価が必要 |
| AstraはGUI専用 | OpenAIは複雑なコード・調査・複数ツールの仕事向けとして案内。CLIテストで足りる確認にGUIを必須にしない |
| Sonnet 5は値上げで割高 / OSWorld 2.0 72.6% | 引用のINDEXだけでは出典不明。本PRの判断材料にしない |

Jevを後で比較するなら、まず実タスクに対して実行先を変えないshadow評価を行う。
低confidenceや認証・削除・課金・データ移行は強いモデル側へ固定し、失敗時も降格しない。
コード・認証情報・会話全体を自動送信せず、送信範囲、API契約、測定結果を先に決める。

## 品質と費用の比較手順

同じcommitから独立したworktreeを作り、実務の代表タスク（設定修正、バグ修正、
UI、複数ファイル変更、認証境界）を各presetで比較する。期待するテストを先に固定する。
`routine`は軽作業群だけに使い、高リスク群はstandard/deepで比較する。

各試行でtask ID、commit、実モデル、effort、合否、テストコマンド・終了コード、
見逃した不具合、人手修正、経過時間、usage/costを記録する。APIと定額枠は分ける。
再試行とレビューも合計費用へ含める。代表タスクを複数回試し、基準を満たすpresetを選ぶ。
失敗・未実行は成功件数へ入れない。少数の成功から「ミスゼロ」を推定しない。

ローカル検証（モデルへの有料リクエストなし）：

```bash
python3 -m unittest discover -s tests -v
bash -n dot_local/bin/executable_ai-code
claude plugin validate dot_claude/agents
```

## 一次資料

- [Claude Code model configuration](https://code.claude.com/docs/en/model-config): alias、effort、必要バージョン、Fable課金とfallback。
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents): 必須frontmatter、tools、maxTurns、検証コマンド。
- [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview) と [effort](https://platform.claude.com/docs/en/build-with-claude/effort): thinkingとeffortの違い。
- [Codex advanced config](https://learn.chatgpt.com/docs/config-file/config-advanced): 独立profileと設定優先順。
- [Codex models](https://learn.chatgpt.com/docs/models): Astra/Sol/Terraの役割と利用条件。
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): TOMLのagent定義と親設定の優先。
- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md): グローバル規約の読み込み。
- [TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart)、[confidence routing](https://docs.typesafe.ai/patterns/confidence-routing)、[発表](https://typesafe.ai/blog/introducing-system-one-models-and-jev): APIと判断の限界。
