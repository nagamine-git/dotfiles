# このリポジトリの開発用コマンド。一覧は `just`。CI も同じレシピを使う
default:
    @just --list

# tests/*.py を全部実行する。鍵・ネットワーク・モデル呼び出しは使わない。
# unittest.main を持たないファイル (pi_real.py などの補助) は飛ばす
test:
    #!/usr/bin/env bash
    set -u
    fail=0
    for t in tests/*.py; do
      grep -q 'unittest.main' "$t" || continue
      echo "::group::$t"
      python3 -B "$t" || { echo "::error file=$t::$t failed"; fail=1; }
      echo "::endgroup::"
    done
    # OpenClaw の自作プラグイン (OpenClaw が無いホストでは試験自身が skip する)
    for t in tests/*.mjs; do
      node "$t" || { echo "::error file=$t::$t failed"; fail=1; }
    done
    exit "$fail"

# コミット前の検査 (秘密・ShellCheck・ruff・zizmor など) を全ファイルにかける
lint:
    prek run --all-files
