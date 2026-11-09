# Espanso は端末内の平文を使い、1Password は初回だけ読む

通常の展開では 1Password を呼ばない。初回セットアップで必要な値を取り込み、その後はローカルの平文を正として編集する。1Password からの再取得は明示的に実行したときだけ行う。

## 値は Git と chezmoi の管理外に置く

| パス | 内容 |
|---|---|
| `~/.config/espanso/match/private.local.yml` | 端末内だけの平文マッチ。権限は 0600 |
| `private_dot_config/espanso/onepassword-references.json` | 公開可能なトリガーと参照の対応表 |
| `private_dot_config/espanso/scripts/onepassword-sync.py` | 初回取り込み・明示的な更新 |
| `private_dot_config/espanso/match/base.yml` | 公開許可済みの氏名 |
| `private_dot_config/espanso/match/secrets.yml` | 空のマッチ。旧版の動的展開を無効にする |
| `private_dot_config/espanso/config/default.yml.tmpl` | OS 別の配列・貼り付け設定 |

個人値はリポジトリの外に置く。`.chezmoiignore` で取り込み対象から外し、誤ってソース側にコピーしても `.gitignore` が `private_` 接頭辞付きの名前やバックアップを除外する。

これは暗号化ではなく、Git への混入防止である。本人権限で動くアプリはローカルの平文を読める。

## 初回取り込み後はローカルで編集する

本人のログイン済みターミナルで、1Password デスクトップアプリの CLI 連携を有効にして実行する。

```sh
python3 ~/.config/espanso/scripts/onepassword-sync.py
```

- 初回だけ指定のフィールドを取得し、権限 0600 のローカルファイルに保存する。
- 既存ファイルがあれば、1Password にアクセスせず、手編集も上書きしない。
- 保存後は Espanso を明示的に再起動する。
- 値と CLI の生のエラーは表示・ログ出力しない。サービスアカウントは使わない。

通常のセットアップスクリプトも同じ処理を呼ぶ。既存ファイルがあれば、再適用時に認証を求めない。

生成ファイルは JSON 形式だが、YAML として Espanso がそのまま読める。テキストエディタで該当する `replace` を編集し、`espanso restart` を実行する。値はチャットに貼る必要がない。

```json
{
  "trigger": "zph",
  "word": true,
  "replace": "ここに会社電話番号を入力する"
}
```

一部の取得に失敗した場合は、成功分を保存し、失敗したトリガー名だけ表示する。失敗項目は前の値を保ち、初回なら `replace` に元のトリガーを入れる。必要な値はローカルで直接入力できる。すべて失敗した場合は既存ファイルを変更しない。

1Password を正として再取得したい場合だけ、次を実行する。成功した項目は手編集の値も置き換わるので注意する。

```sh
python3 ~/.config/espanso/scripts/onepassword-sync.py --refresh
```

再取得時は生成時の JSON 形式を維持しておく。通常の YAML に書き換えたファイルも通常利用・再適用では保持するが、`--refresh` では上書きせずエラーにする。

## 会社は z、個人は zp に揃える

| トリガー | 展開内容 |
|---|---|
| `zefg` | 会社名 |
| `zph` | 会社電話 |
| `zadden` | 会社の英語住所 |
| `zema` | 会社メール |
| `zsal` | 営業メール |
| `zpma` | 個人メール |
| `zpph` | 個人電話 |
| `znam` | 永峰 剛志 (公開許可済みの平文) |

`zadd` と `zpadd` は取得不具合のため初回取り込み対象から除外する。ローカルで追加済みの値は削除・変更しない。`zcma` は参照未指定のため未登録。

すべて `word: true` とし、英数入力で末尾にスペースなどの区切りを入力すると展開する。Alt+Space の一覧を開く必要はない。

## Hyprland / Colemak は明示的な配列と貼り付けを使う

Linux では Wayland 版 Espanso を導入し、`keyboard_layout: {layout: us, variant: colemak}` を明示する。出力は `backend: Clipboard` に固定し、文字列のキーコード注入を避ける。

貼り付けキーは Linux が `CTRL+SHIFT+V`、macOS が `CMD+V`。Linux 側は foot / Ghostty に合わせている。ブラウザでは通常プレーンテキスト貼り付けになる。このキー操作を受け付けないアプリでは別の調整が必要になる。

設定の実体は `~/.config/espanso`。macOS は `~/Library/Application Support/espanso` からリンクする。既存ディレクトリがある場合は、リンクに置き換える前に内容を確認する。

クリップボード経由なので、cliphist に値が保存される可能性がある。`preserve_clipboard: true` は直前のクリップボードを戻す設定で、履歴を消す機能ではない。パスワード・本人確認番号・口座情報は登録しない。

## 作業ブランチからは適用先パスを指定する

導入済みの Linux では、このリポジトリのルートで次を実行する。通常のソースには切り替えず、Espanso の設定だけを反映する。

```sh
chezmoi --source "$PWD" diff --recursive "$HOME/.config/espanso"
chezmoi --source "$PWD" apply -v --recursive "$HOME/.config/espanso"
python3 "$HOME/.config/espanso/scripts/onepassword-sync.py"
```

この環境の chezmoi v2.73.3 では、`--source-path private_dot_config/espanso` のディレクトリ指定で配下が配置されなかった。一時 HOME でも再現したため、上記の適用先パスを使う。終了コード 0 や無出力だけで配置成功と判断しない。

## エラーは描画と設定監視を分けて確認する

旧版ではスクリプトが標準エラーを出すと、終了コード 0 でも Espanso が描画エラーとした。現在は動的スクリプトを使わないので、1Password のロックや参照エラーが通常の展開を止めることはない。

`watcher` スレッドの `No space left on device` は inotify の監視枠不足でも発生する。Espanso が起動中でも、設定の自動再読み込みだけが壊れている場合がある。ディスクの空き容量とは別に調べ、監視を大量消費するアプリを確認する。むやみに上限を増やさず、対象アプリの再起動後に `espanso restart` を実行する。

## 検証は偽の CLI と一時 HOME で行う

`python3 tests/espanso.py` で、初回取り込み、認証なしの再利用、手編集の保護、明示的な更新、失敗時の値保持、原子的な書き込み、権限、Git 除外、配置を検証する。実在する保管庫・クリップボードにはアクセスしない。

chezmoi / PyYAML がない場合は、対応する検証だけをスキップする。実際の取り込み、入力展開、macOS のアクセシビリティ権限は本人の端末で別途確認する。

## iPhone は別途テキスト置換を使う

Espanso の iOS 版はない。iPhone のテキスト置換に同じトリガーを登録できるが、値の自動同期はしない。Mac にも同期する場合は、Espanso と二重に展開されないか確認する。
