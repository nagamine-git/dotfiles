# gnome-keyring の OpenSession クラッシュと修正版パッケージ

am5-itx と fp7-e14 の gnome-keyring は、公式版ではなく、パッチを当てて再ビルドした `1:51.1-1.2` を使っている (2026-11-01 から)。この文書は、その理由と、入れ直し・戻し方の手順をまとめたもの。

## 症状と原因

2026-10-20〜26 に、ChatGPT アプリでキーリングの解錠を何度も求められた。原因はパスワードの設定ではなく、`gnome-keyring-daemon` 自体のクラッシュだった。デーモンが落ちると解錠した状態がメモリごと消え、systemd が再起動したデーモンはロックされた状態で始まる。そのため、アプリが鍵にアクセスするたびに解錠を求め直していた。

ログには毎回、次の順でメッセージが出る。

```
gkd_secret_service_get_pkcs11_session: assertion 'client' failed
aes_negotiate: assertion 'session' failed
gkd_secret_service_publish_dispatch: assertion 'client' failed
g_variant_new: expected GVariant of type 'v' but received value has type '(null)'
```

アプリが接続して最初に送る `OpenSession` が、クライアントを登録する G_PRIORITY_HIGH の idle より先に処理されることがある。GLib の `g_main_context_check()` が処理中に context のロックを手放すため、この順番は保証されていない。登録が無い状態で `OpenSession` を処理すると、エラーを設定しないまま失敗し、出力が NULL のまま返事を作ろうとして abort する。

上流では issue #190・#196・#199 として報告されており、修正 MR !112 はまだマージされていない (2026-11-01 時点)。

## 修正版パッケージ

リポジトリ: <https://github.com/nagamine-git/gnome-keyring-openssession-fix> (private)

中身は、Arch 公式の PKGBUILD に `daemon/dbus/gkd-secret-service.c` へのパッチを 1 本足したもの。パッチは `OpenSession` の入口で未登録のクライアントをその場で登録し、エラーが設定されないまま失敗した場合も D-Bus のエラーとして返す。隔離した D-Bus で再現させたところ、公式版は 40 回中 40 回クラッシュし、修正版は 0 回だった。再現手順と結果は、リポジトリの `repro/` に置いてある。

新しいホストや、公式の更新後に入れ直すときのコマンド:

```sh
ghq get nagamine-git/gnome-keyring-openssession-fix
cd ~/ghq/github.com/nagamine-git/gnome-keyring-openssession-fix && export GNUPGHOME=$(mktemp -d) && gpg --quiet --import keys/pgp/*.asc && makepkg -si
systemctl --user restart gnome-keyring-daemon.service   # 再起動するとキーリングがロックされるので、ログインパスワードを 1 回入力する
```

公式版に戻すときのコマンド:

```sh
sudo pacman -S gnome-keyring
```

`IgnorePkg` は使っていない。公式の更新 (51.2 や pkgrel の更新) が来ると、`pacman -Syu` で修正版は公式版に置き換わる。

## 公式の更新が来たとき

1. `pacman -Q gnome-keyring` で版を確認する。
2. その版に MR !112 (またはそれに相当する修正) が入っていれば、公式版のままでよい。修正版のリポジトリはアーカイブしてよい。
3. 入っていなければ、PKGBUILD の pkgver・pkgrel・チェックサムを新しい公式版に合わせてビルドし直す。

## Codex の file 保存は残す

`home/private_dot_codex/modify_private_config.toml` は、Linux で `mcp_oauth_credentials_store = "file"` を設定している。これは、ChatGPT 同梱の Codex が MCP の OAuth トークンを keyring に置かないようにするための設定で、このクラッシュを引き起こすきっかけを減らしていた。デーモンを修正した後も、次の理由で外さない。

- 公式版に戻った場合の保険になる。
- 修正したのは `OpenSession` だけで、プロパティの取得など、ほかの呼び出しが最初に来たときの同種の競合 (上流 #195・#203) は残っている。

## 再発の確認

```sh
journalctl --user --since "2026-11-01 11:48" | grep 'gnome-keyring-daemon.service: Main process exited'
```

am5-itx の 2026-11-01 10:56〜11:44 のユーザージャーナルと `coredumpctl` には、再現試験で意図的に落とした記録が約 200 件残っている。本番のクラッシュを数えるときは、この時間帯を除外する。
