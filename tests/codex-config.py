"""No model calls: feed disposable config.toml text to the modify_ script and check stdout."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "private_dot_codex/modify_private_config.toml"
FALLBACK = "project_doc_fallback_filenames"
MCP_STORE = "mcp_oauth_credentials_store"


def modify(text, platform="darwin"):
    # Keep the original formatting/effort checks independent of Linux's credential-store default.
    wrapper = "import runpy, sys; sys.platform = sys.argv[1]; runpy.run_path(sys.argv[2], run_name='__main__')"
    result = subprocess.run([sys.executable, "-c", wrapper, platform, str(SCRIPT)], input=text, capture_output=True,
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

    def test_preserves_existing_effort_in_both_scopes(self):
        for top, deep in (("high", "low"), ("ultra", "ultra"), ("low", "high")):
            with self.subTest(top=top, deep=deep):
                src = 'model_reasoning_effort = "%s"  # chosen\n' \
                      '%s = ["CLAUDE.md"]\n\n' \
                      '[profiles.deep]\n"model_reasoning_effort" = \'%s\'\n' % (top, FALLBACK, deep)
                out, _ = modify(src)
                self.assertEqual(out, src)

    def test_adds_only_missing_top_level_effort(self):
        src = '%s = ["CLAUDE.md"]\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "ultra"\n' % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, '%s = ["CLAUDE.md"]\nmodel_reasoning_effort = "medium"\n\n'
                              '[profiles.deep]\nmodel_reasoning_effort = "ultra"\n' % FALLBACK)

    def test_preserves_single_quoted_effort_keys_as_valid_toml(self):
        src = "'model_reasoning_effort' = 'high'\n%s = [\"CLAUDE.md\"]\n\n" \
              "[profiles.deep]\n'model_reasoning_effort' = 'low'\n" % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, src)
        try:
            import tomllib
        except ImportError:
            self.skipTest("TOML parsing requires Python 3.11+")
        config = tomllib.loads(out)
        self.assertEqual(config["model_reasoning_effort"], "high")
        self.assertEqual(config["profiles"]["deep"]["model_reasoning_effort"], "low")

    def test_adds_only_missing_profile_effort(self):
        src = 'model_reasoning_effort = "ultra"\n%s = ["CLAUDE.md"]\n\n' \
              '[profiles.deep]\nmodel = "x"\n' % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, src + 'model_reasoning_effort = "xhigh"\n')

    def test_preserves_other_scopes_and_multiline_text_when_adding_defaults(self):
        src = '%s = ["CLAUDE.md"]\n\n[other]\nmodel_reasoning_effort = "low"\n' \
              'text = \'\'\'\n[profiles.deep]\nmodel_reasoning_effort = "high"\n\'\'\'\n' % FALLBACK
        out, _ = modify(src)
        self.assertEqual(out, src.replace('\n\n[other]', '\nmodel_reasoning_effort = "medium"\n\n[other]') +
                              '\n[profiles.deep]\nmodel_reasoning_effort = "xhigh"\n')

    def test_linux_adds_only_missing_mcp_store_at_top_level(self):
        src = 'model = "chosen-model"\nmodel_reasoning_effort = "high"  # chosen\n' \
              '%s = ["CLAUDE.md"]\n\n[permissions]\nmode = "chosen-mode"\n\n' \
              '[profiles.deep]\nmodel_reasoning_effort = "low"\n' % FALLBACK
        out, _ = modify(src, "linux")
        expected = src.replace('\n\n[permissions]', '\n%s = "file"\n\n[permissions]' % MCP_STORE)
        self.assertEqual(out, expected)
        self.assertEqual(modify(out, "linux")[0], out)

    def test_linux_empty_input_gets_file_store(self):
        out, _ = modify("", "linux")
        self.assertEqual(out.count('%s = "file"' % MCP_STORE), 1)
        self.assertLess(out.index(MCP_STORE), out.index("[profiles.deep]"))

    def test_linux_preserves_explicit_mcp_store_including_quoted_keys(self):
        for store in ("auto", "keyring", "file"):
            for key in (MCP_STORE, '"%s"' % MCP_STORE, "'%s'" % MCP_STORE):
                with self.subTest(store=store, key=key):
                    src = '%s = \'%s\' # chosen\nmodel_reasoning_effort = "high"\n' \
                          '%s = ["CLAUDE.md"]\n\n[profiles.deep]\n' \
                          '"model_reasoning_effort" = "low"\n' % (key, store, FALLBACK)
                    out, _ = modify(src, "linux")
                    self.assertEqual(out, src)

    def test_darwin_does_not_default_the_mcp_store(self):
        out, _ = modify("", "darwin")
        self.assertNotIn(MCP_STORE, out)

    def test_linux_does_not_take_nested_or_multiline_mcp_keys_as_top_level(self):
        src = 'text = \'\'\'\n%s = "keyring"\n\'\'\'\n\n' \
              '[other]\n"%s" = "auto"\n' % (MCP_STORE, MCP_STORE)
        out, _ = modify(src, "linux")
        self.assertIn(src.split('\n\n[other]')[0], out)
        self.assertIn('[other]\n"%s" = "auto"\n' % MCP_STORE, out)
        self.assertEqual(out.count('%s = "file"' % MCP_STORE), 1)
        self.assertLess(out.index('%s = "file"' % MCP_STORE), out.index("[other]"))


if __name__ == "__main__":
    unittest.main()
