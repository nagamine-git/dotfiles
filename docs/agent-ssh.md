# エージェントから Mac への無人 SSH

2026-10-21 JST、am5 から Mac への Tailscale SSH 移行と新規接続の検証が完了した。
Homebrew daemon を GUI と別の `m1pro-mbp14-agent` として再登録し、userspace モードで稼働させた。
Linux の `ssh mac` は個人鍵・1Password Agent・パスワードを使わず、この専用ノードへ接続する。
ホスト鍵は Tailscale の制御プレーンで確認し、厳密な照合を維持している。
GUI ノードもオンラインのまま。Mac の再起動後と他の接続元は未検証。

## 調査開始時の状態

| 項目 | 実測・確認結果 |
|---|---|
| 接続元 am5-itx | `tag:ci`、`tag:personal` |
| 接続先 Mac の GUI ノード | `m1pro-mbp14`、IP `100.73.145.6`、ID `ncbVcuQj1911CNTRL`、承認後に `tag:personal`、online |
| GUI ノードの状態 | 1.96.5、backend `Running`、`RunSSH=false`、Health なし |
| Mac の Homebrew daemon | 同じホスト名、IP `100.104.45.92`、ID `nuKwpS9WTT11CNTRL`、`tag:personal`、offline |
| Homebrew daemon の状態 | 1.98.5、backend `Running`、`RunSSH=true`。管理画面・peer 一覧に存在せず、ログに node removed / deleted |
| CLI の接続先 | `/opt/homebrew/bin/tailscale` 1.98.5。既定では GUI 側へ接続し得る。daemon を指定するには `--socket=/var/run/tailscaled.socket` |
| am5 の状態 | 1.104.1。peer に見える Mac は GUI ノードだけ。daemon の peer / ホスト鍵は未確認 |
| 当初の Mac 接続 | `mac_login.pub` と 1Password SSH Agent。既存 master は調査時 PID 4029349 |

## 移行後に確認できた状態

| 項目 | 実測・確認結果 |
|---|---|
| 専用ノード | `m1pro-mbp14-agent.tailcda87f.ts.net.`、ID `n7FAuQsrwE11CNTRL` |
| 専用ノードの IP | `100.73.103.16`、`fd7a:115c:a1e0::f2a:6711` |
| 専用 daemon | `Running`、online、`tag:personal`、Health なし、起動引数 `--tun=userspace-networking` |
| GUI ノード | 元の ID と IP のまま `Running`、online、Health なし |
| am5 の `ssh mac` | 接続共有を止めた新規接続で、認証方式 `none`、ユーザー名 `tsuyoshi.nagamine`、終了コード 0 |

管理画面で確認した既存の SSH 規則は次のとおり。
ACL 本文は変更していない。

```json
{
  "action": "accept",
  "src": ["autogroup:member", "tag:personal"],
  "dst": ["tag:personal", "tag:ci", "tag:healthcare", "tag:zeed-telemetry"],
  "users": ["autogroup:nonroot", "root"]
}
```

調査開始時は Mac がタグなしだったため、タグ付きの am5 から Tailscale SSH に移行できなかった。
[公式の接続条件](https://tailscale.com/docs/features/tailscale-ssh#order-of-evaluation)に合わせ、承認後に宛先をタグ付きにした。

## 承認済みの変更と影響

本人が承認した範囲は、Mac への既存の `tag:personal` の付与と `RunSSH` の有効化。
このタグは表示用の分類ではなく、アクセス権の主体になる。

- 既存規則により、tailnet のメンバーと `tag:personal` の端末から、Mac の非 root ユーザーと **root** への SSH が許可対象になる。
- `accept` なので、接続ごとの追加ログイン確認は要求しない。
- Mac の所有主体がユーザーからタグに変わる。元のユーザー所有に戻すには Mac 側での Tailscale 再認証が必要で、管理画面で最後のタグだけを削除することはできない。
- Tailscale はタグをサービス用端末に推奨している。この Mac を無人作業用ホストとして扱う判断を含む。

既存規則で root も許可対象になることを示したうえで、タグ付与と SSH 有効化の承認を得た。
[タグの仕様と戻し方](https://tailscale.com/docs/features/tags#limitations)

タグは [Machines](https://login.tailscale.com/admin/machines) の `m1pro-mbp14` で保存済み。
保存後に、am5 の peer 情報と Mac の既定 CLI の両方で `tag:personal` と同じ IP を確認した。
さらに socket を明示した確認で、Homebrew daemon は別 IP の既存ノードで、こちらも既に `tag:personal` と分かった。

## 適用済みの設定と復旧手順

既存 master 経由で調査し、新しい鍵利用やパスワード入力を要求しないようにした。
Mac の `sudo -n true` は `sudo: a password is required` で失敗する。
root の launchd サービスの変更・再起動は本人が Mac ローカル端末から実行する。
既定 CLI に対する `sudo tailscale set --ssh` は GUI を対象にし得るため使わない。
macOS の SSH サーバー機能は open-source daemon 版に限られる。[公式の対応環境](https://tailscale.com/docs/features/tailscale-ssh#prerequisites)

復旧用に `agent-mac-ssh-bootstrap` を用意した。
既存の Homebrew plist だけを対象にし、root 所有・権限・実行ファイル・引数を検証する。
引数やサービスの形が想定と異なる場合は書き換えずに止まる。
ホスト名は引数で渡し、GUI ノードと重複させない。

1. 元の plist を root 専用の `.plist.before-agent-userspace` に一度だけ保存する。
2. 明示した daemon socket へ、DNS・経路の取り込み無効化、別ホスト名、SSH 有効を設定する。
3. daemon の停止・launchd からの削除完了を確認してから、`--tun=userspace-networking` で再起動する。GUI の VPN・macOS sshd・sudo 設定は変更しない。
4. daemon の再認証コマンドを表示する。起動成功だけで無人 SSH の完了とは表示しない。

userspace モードは OS の VPN インターフェースを作らない。
GUI と別の SSH 用ノードとして動かす構成であり、今回の Mac 実機で SSH 接続を検証済み。
[userspace networking の公式説明](https://tailscale.com/docs/concepts/userspace-networking)

修正版は Mac の `~/Downloads/agent-mac-ssh-bootstrap.py` に配置済み。
am5 側と SHA-256 の一致と、Mac 上の変更しないチェックを確認した。
Mac のローカル端末で準備したスクリプトを実行する。
最初の管理者パスワードは本人が OS に入力する。エージェントへ渡さない。

```sh
sudo /usr/bin/python3 ~/Downloads/agent-mac-ssh-bootstrap.py --apply --hostname m1pro-mbp14-agent
```

次に、表示された explicit socket 付きの `tailscale login` を使って登録し直す。
SSH 経由で開始する場合、このバージョンの `login` は切断警告で止まり、警告に示される `--accept-risk` も受け付けない。
今回のように専用 daemon と GUI の接続経路が別と確認済みの場合は、同じ設定の `tailscale up --accept-risk=lose-ssh` を使える。
GUI と同じ daemon に対してこの指定を使わない。
`tag:personal` と SSH 有効化は承認済み。認証キーを新設・保存する必要はない。
GUI の元の名前と IP を宛先にして試験せず、新しく登録された `m1pro-mbp14-agent` の FQDN と公開ホスト鍵を確認する。

新しい plist の起動が失敗した場合は保存済み plist への復帰を試み、エラーを返す。
手動で起動方式を戻すときは次を使う。

```sh
sudo /usr/bin/python3 ~/Downloads/agent-mac-ssh-bootstrap.py --restore
```

停止済みの場合も、元のサービスを起動して LocalAPI の応答を確認してから次へ進む。
復帰が戻すのは起動引数で、DNS・経路・ホスト名の設定や端末登録は戻さない。
タグの取り消しと元のユーザー所有への復帰には別途再認証が必要。
Mac ローカルの復旧経路を確保して行う。修正版のテストは 20 件成功。実機の無人 SSH も検証済み。

## 23:14 の起動失敗と復旧

初版を本人が実行した際、新設定の `launchctl bootstrap` と旧設定の再起動が共に終了コード 5 で失敗した。
旧設定のファイルへの復帰はできていたが、サービスが停止した状態になった。
二度目の実行は socket が存在せず `tailscale set` が失敗した。

ログ上では 23:14:28.970 に設定ファイルの変更が検出され、23:14:29.929 に元のサービスが終了・削除されている。
停止完了前に起動を試みた競合が疑われる。
本人が 23:21 に次を実行し、その後の SSH 経由の確認で launchd `running`、PID 89025、explicit socket の応答を確認した。
この時点のバックエンドは `NeedsLogin` で、端末の再認証は未完了だった。

```sh
sudo /bin/launchctl bootstrap system /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist
```

修正版では削除完了まで待機し、停止済みのサービスも扱い、起動登録だけでなく LocalAPI の応答を確認する。
新設定の起動失敗と復帰失敗は両方のエラーを報告する。
`bootout` が先に戻る挙動を再現した回帰テストも追加した。

本人が 23:25 に修正版を適用し、エラーなしで終了した。
SSH 経由で plist の引数が `--tun=userspace-networking` となったことと、LocalAPI の `NeedsLogin` を確認した。
専用 daemon の `up` を開始し、ブラウザー操作の接続が利用不能のため、本人へ認証 URL を案内した。
その後、am5 の peer 一覧と Mac の explicit socket の双方で、新しい端末 ID と online を確認した。
ブラウザー画面に 403 が出ていても登録は完了していたため、再ログインを求めず接続検証へ進んだ。

## 鍵・agent・接続共有を使わない完了確認

Tailscale SSH は tailnet の端末認証を使う。
`tailscale ssh` は制御プレーン経由の公開ホスト鍵を確認し、Linux では通常 `~/.config/tailscale/ssh_known_hosts` に保存する。
ホスト鍵検証は `StrictHostKeyChecking=yes` のまま使う。
`ssh-keyscan` の未確認鍵、`StrictHostKeyChecking=no`、個人秘密鍵の持ち出しは使わない。
[公式 CLI 実装](https://github.com/tailscale/tailscale/blob/v1.104.1/cmd/tailscale/cli/ssh.go#L92-L179)

承認・有効化の後、am5 の Bash から以下を実行する。
`-F /dev/null` で既存の 1Password 設定を読み込まず、agent、鍵認証、パスワード、キーボード対話、接続共有を明示的に止める。
失敗時には対話へ切り替えない。各接続は新規に認証される。

```bash
ts_mac_ssh() {
  env -u SSH_AUTH_SOCK tailscale ssh \
    tsuyoshi.nagamine@m1pro-mbp14-agent.tailcda87f.ts.net. \
    -F /dev/null \
    -o IdentityAgent=none -o IdentityFile=none \
    -o PubkeyAuthentication=no -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no -o GSSAPIAuthentication=no \
    -o HostbasedAuthentication=no -o BatchMode=yes \
    -o ControlMaster=no -o ControlPath=none \
    -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes \
    -o ConnectTimeout=10 -o ConnectionAttempts=1 "$@"
}

ts_mac_ssh -v /usr/bin/id -un
ts_mac_ssh /usr/bin/true
```

完了条件は、初回のユーザー名が `tsuyoshi.nagamine`、両方の終了コードが 0 で、詳細ログの認証方式が `none` であること。
公開鍵認証を無効にした新規接続で、上記の完了条件を満たした。

その後、通常の OpenSSH でも同じ公開ホスト鍵で接続できるか確かめる。

```bash
env -u SSH_AUTH_SOCK ssh -F /dev/null \
  -o IdentityAgent=none -o IdentityFile=none \
  -o PubkeyAuthentication=no -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o GSSAPIAuthentication=no \
  -o HostbasedAuthentication=no -o BatchMode=yes \
  -o ControlMaster=no -o ControlPath=none \
  -o UserKnownHostsFile="${XDG_CONFIG_HOME:-$HOME/.config}/tailscale/ssh_known_hosts" \
  -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes \
  -o ConnectTimeout=10 -o ConnectionAttempts=1 \
  tsuyoshi.nagamine@m1pro-mbp14-agent.tailcda87f.ts.net. /usr/bin/id -un
```

通常の OpenSSH でも成功を確認後、`private_dot_ssh/config.tmpl` の Linux 側 Mac Host ブロックを同じ方式へ変更し、am5 に scoped apply した。
`ssh -G mac` で認証・ホスト鍵の設定を確認し、さらに `env -u SSH_AUTH_SOCK ssh -o ControlMaster=no -o ControlPath=none -v mac /usr/bin/id -un` で新規接続に成功した。
ログの認証方式は `none`、ユーザー名は `tsuyoshi.nagamine`、終了コードは 0。
別の Linux ホストに反映するときは、先に `tailscale ssh` で制御プレーンからホスト鍵を取得し、同じ試験を行う。
将来のホスト鍵変更で接続が止まったら、`tailscale ssh` で制御プレーンから再取得する。

## 21:50 / 21:56 のダイアログと tmux

GNOME Keyring では、次のクラッシュと再起動が確認されている。
時間は 2026-10-21 JST。

| 時刻 | 証拠 |
|---|---|
| 21:50:09.326 / 21:50:11.017 | アプリに keyring 失敗ログ。後者は MCP/OAuth 処理時 |
| 21:50:15.802 | `gnome-keyring-daemon.service` が ABRT。再起動回数 4 |
| 21:56:01.985 | 同サービスが ABRT。再起動回数 5 |
| 21:56:15.550 | 同サービスが ABRT。再起動回数 6。以後の確認時 PID 72570 |

ログには `gkd_secret_service_get_pkcs11_session` の `client` assertion、`aes_negotiate`、GLib variant の異常がある。
クラッシュとアプリの keyring 失敗の前後関係は確認できたが、原因クライアントの特定はできていない。
これは SSH の鍵利用承認とは別の調査対象。keyring の内容やパスワードは変更していない。

1Password の SSH Agent は、鍵を使うアプリやプロセスに承認を結び付ける。
tmux に起動場所をそろえるだけでは、1Password の初回承認や再ロック、GNOME Keyring のクラッシュは解消しない。
Codex を tmux 内で起動することは、この無人認証案の前提ではない。
[1Password の承認モデル](https://developer.1password.com/docs/ssh/agent/security/#authorization-model)
