"""agent-claude and agent-chrome-mcp: the vault token when it resolves, the plain command otherwise.
Fake op-agent, claude and npx; no keys, network or vault."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "home/dot_local/bin"
FAKE_OP = r'''#!/usr/bin/env bash
# op-agent run --env-file F -- cmd...: resolves when $HOME/vault-ok exists, and passes a synthetic value.
[[ "$1" == run ]] || exit 9
[[ -e "$HOME/vault-ok" ]] || { echo "item not found" >&2; exit 1; }
shift; shift; shift; shift
export CLAUDE_CODE_OAUTH_TOKEN=SYNTHETIC PLAYWRIGHT_MCP_EXTENSION_TOKEN=SYNTHETIC OP_SERVICE_ACCOUNT_TOKEN=SA-SYNTHETIC
exec "$@"
'''
FAKE_CMD = r'''#!/usr/bin/env python3
import json, os, sys
print(json.dumps({"cmd": os.path.basename(sys.argv[0]), "argv": sys.argv[1:],
                  "token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN"),
                  "sa": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")}))
'''


class Wrappers(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        for name, text in (("op-agent", FAKE_OP), ("claude", FAKE_CMD), ("npx", FAKE_CMD)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        (self.home / ".config/agents").mkdir(parents=True)

    def run_wrapper(self, name, *args):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "LANG": "C.UTF-8"}
        out = subprocess.run(["bash", str(BIN / f"executable_{name}"), *args], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_agent_claude_uses_the_token_only_when_it_resolves_and_never_passes_the_service_account_on(self):
        self.assertEqual(self.run_wrapper("agent-claude", "-p", "x"), {"cmd": "claude", "argv": ["-p", "x"], "token": None, "sa": None})
        (self.home / ".config/agents/claude-code.env").write_text("CLAUDE_CODE_OAUTH_TOKEN=op://Agents/x/credential\n")
        self.assertEqual(self.run_wrapper("agent-claude", "-p", "x")["token"], None)  # not in the vault yet
        (self.home / "vault-ok").touch()
        self.assertEqual(self.run_wrapper("agent-claude", "-p", "x"), {"cmd": "claude", "argv": ["-p", "x"], "token": "SYNTHETIC", "sa": None})

    def test_agent_chrome_mcp_prefers_the_extension_token_then_chrome_s_own_debugging_then_the_extension(self):
        out = self.run_wrapper("agent-chrome-mcp")
        self.assertEqual((out["argv"][1:], out["token"]), (["@playwright/mcp@latest", "--extension", "--background"], None))
        (self.home / ".config/google-chrome").mkdir(parents=True)
        (self.home / ".config/google-chrome/DevToolsActivePort").write_text("9222\n/devtools/browser/x\n")
        self.assertIn("--autoConnect", self.run_wrapper("agent-chrome-mcp")["argv"])
        (self.home / ".config/agents/chrome.env").write_text("PLAYWRIGHT_MCP_EXTENSION_TOKEN=op://Agents/x/password\n")
        (self.home / "vault-ok").touch()
        out = self.run_wrapper("agent-chrome-mcp")
        self.assertEqual((out["argv"][1:], out["token"], out["sa"]), (["@playwright/mcp@latest", "--extension", "--background"], "SYNTHETIC", None))


if __name__ == "__main__":
    unittest.main()
