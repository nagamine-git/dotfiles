"""No model calls: feed disposable config.toml text to the modify_ script and check stdout."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "private_dot_codex/modify_private_config.toml"
FALLBACK = "project_doc_fallback_filenames"


def modify(text):
    result = subprocess.run([sys.executable, str(SCRIPT)], input=text, capture_output=True,
                            text=True, check=True)
    return result.stdout, result.stderr


class CodexConfigModify(unittest.TestCase):
    def test_empty_input_gets_effort_profile_and_claude_fallback(self):
        out, _ = modify("")
        self.assertEqual(out, 'model_reasoning_effort = "medium"\n'
                              '%s = ["CLAUDE.md"]\n\n'
                              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK)

    def test_adds_fallback_after_last_top_level_line_not_inside_a_table(self):
        src = 'model = "x"\nmodel_reasoning_effort = "medium"\n\n[tui]\nfullscreen = true\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n'
        out, _ = modify(src)
        self.assertEqual(out, 'model = "x"\nmodel_reasoning_effort = "medium"\n'
                              '%s = ["CLAUDE.md"]\n\n[tui]\nfullscreen = true\n\n'
                              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK)

    def test_keeps_other_fallback_names_and_appends_claude_md(self):
        src = 'model_reasoning_effort = "medium"\n%s = ["TEAM.md"]  # mine\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK
        out, _ = modify(src)
        self.assertIn('%s = ["TEAM.md", "CLAUDE.md"]  # mine\n' % FALLBACK, out)

    def test_already_present_is_a_no_op(self):
        src = 'model_reasoning_effort = "medium"\n%s = [".agents.md", \'CLAUDE.md\']\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, src)

    def test_second_run_changes_nothing(self):
        first, _ = modify('model = "x"\n\n[tui]\nfullscreen = true\n')
        second, _ = modify(first)
        self.assertEqual(second, first)

    def test_same_key_inside_another_table_is_not_mistaken_for_top_level(self):
        src = 'model_reasoning_effort = "medium"\n\n[x]\n%s = ["OTHER.md"]\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK
        out, _ = modify(src)
        self.assertIn('[x]\n%s = ["OTHER.md"]\n' % FALLBACK, out)
        self.assertEqual(out.count('["CLAUDE.md"]'), 1)
        self.assertLess(out.index('["CLAUDE.md"]'), out.index("[x]"))

    def test_multiline_array_is_left_alone_with_a_warning(self):
        src = 'model_reasoning_effort = "medium"\n%s = [\n  "TEAM.md",\n]\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK
        out, err = modify(src)
        self.assertEqual(out, src)
        self.assertIn(FALLBACK, err)

    def test_existing_effort_behaviour_is_unchanged(self):
        src = 'model_reasoning_effort = "high"\n%s = ["CLAUDE.md"]\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "low"\n' % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, 'model_reasoning_effort = "medium"\n%s = ["CLAUDE.md"]\n\n'
                              '[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n' % FALLBACK)


if __name__ == "__main__":
    unittest.main()
