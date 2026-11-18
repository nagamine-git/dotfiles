"""エージェントのハーネスの層 (Pi の拡張と、その上の自作スクリプト) のコード量に上限を置く。

本人の方針 (2026-11-18): 無駄なコードを残さない。足すときは同じだけ削る。
上限は、方針を決めた日の量 (4,266 行) を 100 行単位に切り上げたもの。小さな修正の余地だけを残す。
2026-11-15 から 3 日で 3,235 → 4,266 行に増えていたのが、上限を置いた理由。

上限を上げるのは、削れるものが本当に無いときだけ。上げるなら、日付と理由をここに書く。
"""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BUDGET = 4300
SCRIPTS = ("model-radar", "agent-retro", "agents-sync", "pi-jev")


def sources():
    files = sorted((ROOT / "home/dot_pi/agent/extensions").glob("*.ts"))
    return files + [ROOT / f"home/dot_local/bin/executable_{name}" for name in SCRIPTS]


def lines(path):
    return len(path.read_text(encoding="utf-8").splitlines())


class HarnessBudget(unittest.TestCase):
    def test_harness_code_stays_within_the_budget(self):
        sizes = sorted(((lines(p), p.name) for p in sources()), reverse=True)
        total = sum(n for n, _ in sizes)
        biggest = ", ".join(f"{name} {n}" for n, name in sizes[:5])
        self.assertLessEqual(total, BUDGET, f"ハーネスの層が {total} 行で、上限 {BUDGET} 行を超えた。足した分だけ削る。大きい順: {biggest}")

    def test_every_listed_script_exists(self):
        # 名前を変えたり消したりしたら、この一覧も直す (数え漏れで上限をすり抜けないため)
        for p in sources():
            self.assertTrue(p.is_file(), p)


if __name__ == "__main__":
    unittest.main()
