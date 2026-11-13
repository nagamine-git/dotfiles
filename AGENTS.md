# このリポジトリ

chezmoi で Linux (`am5-itx` / `fp7-e14`) と macOS の設定を管理する。`.chezmoiroot` により chezmoi のソースは `home/` (`dot_*` はホームのドットファイル、`home/.chezmoidata/` は共有値、`home/.chezmoiscripts/` は実行スクリプト)。`system/` は /etc などホームの外へ入れるものとパッケージの一覧、`tests/`・`docs/` はリポジトリの道具でホームには配らない。

## 変更と検証

- `~` の設定を直接直さずソースを変更する。対象パスを指定した `chezmoi diff` → `chezmoi apply --dry-run` で影響を確認してから反映する。新規取り込みは `chezmoi add -v <path>`。
- ホスト差はテンプレートの条件分岐で表す。通常のスクリプト・unit・`system/pkglist.txt` にホスト名を固定しない。セットアップ自動化は `home/.chezmoiscripts/` の既存の `run_onchange_*` に合わせ、OS 専用のものは中身を OS の条件で囲む。
- Bash は `#!/usr/bin/env bash`、`set -eu`、2スペース、冪等を基本とする。変更したスクリプトを `bash -n` と利用可能な `shellcheck` で確認し、関連する `tests/` を実行する。
- CI とローカルの検査は `.github/workflows/chezmoi.yml` / `.pre-commit-config.yaml` が正本。`prek install` は checkout ごとに1回。`chezmoi doctor` は環境診断時に使う。
- デスクトップの動作を変えたら変更前後を確認し、必要なスクリーンショットを添える。差分のレビューは [REVIEW.md](REVIEW.md) に従う。
- `private_*` は命名・権限管理であり、秘密の保管庫ではない。秘密値をコミットせず、`op://` 参照かローカルの認証を使う。

コミットは Conventional Commits。PR には目的・対象パス・OS/ホスト・実行した検証を記す。
