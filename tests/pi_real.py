"""Starts the installed Pi (am5-itx: ~/.pi/agent/bin/pi) in RPC mode for tests, without keys, network or model calls.

Each run gets a throwaway agent dir (PI_CODING_AGENT_DIR) and HOME, so the owner's settings, extensions,
sessions and auth.json are never read. Dummy provider keys only make models selectable: nothing is
prompted, so no request leaves the machine. Hosts without Pi (CI, macOS) skip these tests.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

PI = Path.home() / ".pi/agent/bin/pi"
DUMMY_KEYS = {"ANTHROPIC_API_KEY": "dummy-not-a-key", "OPENAI_API_KEY": "dummy-not-a-key"}


def available():
    return PI.is_file() and os.access(str(PI), os.X_OK)


def rpc(agent_files, commands, args=(), env=None, read_back=(), timeout=90):
    """agent_files: {path under the agent dir: text}. commands: RPC commands, each given an id.
    Returns ({id: response}, stderr, {path in read_back: text or None})."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        agent, home, work = tmp / "agent", tmp / "home", tmp / "work"
        for d in (agent, home, work):
            d.mkdir()
        for rel, text in agent_files.items():
            (agent / rel).parent.mkdir(parents=True, exist_ok=True)
            (agent / rel).write_text(text, encoding="utf-8")
        full_env = {"HOME": str(home), "PATH": os.environ["PATH"], "LANG": "C.UTF-8", "PI_CODING_AGENT_DIR": str(agent),
                    "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0", "PROBE_DIR": str(tmp)}
        full_env.update(DUMMY_KEYS, **(env or {}))
        with subprocess.Popen([str(PI), "--mode", "rpc", "--no-session", *args], cwd=str(work), env=full_env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            responses = {}
            guard = threading.Timer(timeout, proc.kill)  # a Pi that never answers fails the test instead of hanging it
            guard.start()
            try:
                for i, command in enumerate(commands):
                    command = dict(command, id="c%d" % i)
                    proc.stdin.write(json.dumps(command) + "\n")
                    proc.stdin.flush()
                    for line in proc.stdout:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        if record.get("type") == "response" and record.get("id") == command["id"]:
                            responses[command["id"]] = record
                            break
                proc.stdin.close()
                stderr = proc.stderr.read()
                proc.wait(timeout=timeout)
            finally:
                guard.cancel()
                if proc.poll() is None:
                    proc.kill()
        files = {}
        for rel in read_back:
            p = tmp / rel
            files[rel] = p.read_text(encoding="utf-8") if p.exists() else None
        return responses, stderr, files


def model_of(response):
    """provider/id and thinking level from a get_state or cycle_model response."""
    data = response.get("data") or {}
    model = data.get("model") or {}
    return "%s/%s" % (model.get("provider"), model.get("id")), data.get("thinkingLevel")
