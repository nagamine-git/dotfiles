# Codex MCP の認証保存先を切り替える

2026-10-21 21:50 / 21:56 JST に、このホストで GNOME Keyring のクラッシュを確認した。
関連する上流の [work item 190](https://gitlab.gnome.org/GNOME/gnome-keyring/-/work_items/190) と
[MR 112](https://gitlab.gnome.org/GNOME/gnome-keyring/-/merge_requests/112) は、同日の確認時点で未解決・未マージだった。
Codex 側にも [同種の報告](https://github.com/openai/codex/issues/51694) がある。
既存の暗号化レコードは残し、Codex MCP から Keyring へアクセスする経路を減らす。
Keyring 自体や、別アプリの認証が直ったとは扱わない。

## 設定する範囲

[公式 OpenAI documentation](https://learn.chatgpt.com/docs/config-file/config-reference) は、
`mcp_oauth_credentials_store` に `auto` / `file` / `keyring` を指定できる。
このリポジトリは Linux でこのトップレベルキーが未設定の場合だけ、次を補う。

```toml
mcp_oauth_credentials_store = "file"
```

明示された `auto` / `keyring` / `file` は変更しない。macOS の既定も変更しない。
モデル、effort、権限、CLI 本体へのログイン保存先 `cli_auth_credentials_store` はそのままにする。

[Codex の File store 実装](https://github.com/openai/codex/blob/main/codex-rs/rmcp-client/src/oauth/resolved_store.rs#L396) は、Keyring の既存レコードを読まず、ファイルを読む。
そのため、設定を変えるだけで既存の MCP OAuth 認証が引き継がれるとは限らない。
Keyring からのトークンの抽出・変換や、既存レコードの削除は行わず、必要なサーバーを再認証する。

ファイルにはログインパスワードではなく OAuth トークンが保存される。
ただしトークンも認証に使える秘密であり、暗号化された Keyring と同じ保護ではない。
`$CODEX_HOME/.credentials.json` (既定 `~/.codex/.credentials.json`) は本人だけが読める `0600` とし、内容を表示・共有・Git 管理しない。
認証ファイルを手で読んだり書き換えたりせず、Codex の OAuth ログインで保存する。

## 反映と再認証を段階的に行う

1. `chezmoi diff` と dry-run で設定キーだけの変更を確認し、設定を反映する。
2. 同じ `CODEX_HOME` を使う Codex CLI・アプリ・IDE は、作業が安全に切り替えられる時点で新しい設定を読み直す。稼働中の作業を強制終了しない。
3. 以下の既存 4 サーバーを一つずつ OAuth で再認証する。一つが終わる前に次のログインを始めない。
4. ファイルの権限だけを確認し、各サーバーの小さな読取操作で接続を検証する。
5. アプリを安全に再起動した後も接続を確認する。CLI だけの成功で全クライアントを完了扱いにしない。

```sh
codex mcp login cloudflare
codex mcp login figma
codex mcp login notion
codex mcp login zeed-atlas
stat -c '%a %n' ~/.codex/.credentials.json
```

ログインが成功しても、API の権限やツール実行が成功したとは限らない。
必要な権限だけを許可し、実際の読取操作まで確認する。
参照: [Codex MCP login の実装](https://github.com/openai/codex/blob/main/codex-rs/cli/src/mcp_cmd.rs#L74)。

## 今回の実行結果

- Linux の設定を scoped apply 済み。既存の model・effort・権限が変わっていないことを検証した。
- Notion はブラウザーで既存の会社 workspace を選び、CLI の再ログイン成功と `mcp list` の `o_auth` を確認した。
- `.credentials.json` の権限は `0600`。内容は出力していない。
- Figma は Google のアカウント選択画面まで進んだが、ブラウザー操作が停止して再認証未完了。再試行時は登録 API への HTTP 接続も失敗した。
- Cloudflare は既定の認証要求に広範な管理・書込権限が含まれたため、同意していない。必要な範囲を確認してから再接続する。
- zeed-atlas は認証 URL の発行まで成功したが、ブラウザー接続が利用不能になったため未完了。待機中の CLI は停止した。

Notion の実ツールによる読取、アプリ再起動後の保持、残り 3 サーバーの再接続は未検証。
ファイル保存への切替後、未再認証のサーバーは以前の Keyring 認証を自動では使えない。

## この切り替えで解決しないもの

ネイティブ ChatGPT 接続やブラウザーの Cookie 保存は、Codex MCP の OAuth 保存先とは別の経路になり得る。
この設定で Cookie の保持や再ログインの問題が直るとは保証しない。
ブラウザーの Cookie 保存先を `basic` に変えたり、login keyring のパスワードを空にしたりしない。
問題が残る場合は、どのクライアント・認証経路で失敗したかを分けて調べる。
既存の暗号化レコードは、各クライアントの動作が確認できるまで保持する。
