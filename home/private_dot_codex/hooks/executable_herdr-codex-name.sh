#!/usr/bin/env bash
# Codex Stop hook: name the herdr codex agent after its current work, mirroring
# Claude Code. Reads the Stop payload (transcript_path, session id) on stdin,
# builds a short excerpt from the codex rollout, and hands it to
# ~/.local/bin/herdr-agent-name (which summarizes with Claude Haiku on the flat
# plan and reports to herdr). Always exits 0; never blocks Codex.
set -eu

[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v herdr-agent-name >/dev/null 2>&1 || command -v "$HOME/.local/bin/herdr-agent-name" >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0

excerpt_and_session="$(HERDR_HOOK_JSON="$input" python3 <<'PY' 2>/dev/null || true
import json, os
try:
    hook = json.loads(os.environ.get("HERDR_HOOK_JSON", ""))
except Exception:
    raise SystemExit(0)
tp = hook.get("transcript_path") or hook.get("rollout_path") or ""
sid = hook.get("session_id") or hook.get("conversation_id") or hook.get("thread_id") or ""
if not tp or not os.path.isfile(tp):
    raise SystemExit(0)
msgs = []
try:
    with open(tp) as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "response_item":
                continue
            p = d.get("payload") or {}
            if p.get("type") != "message":
                continue
            role = p.get("role")
            if role not in ("user", "assistant"):
                continue
            c = p.get("content")
            text = " ".join(b.get("text", "") for b in c if isinstance(b, dict)) if isinstance(c, list) else str(c or "")
            text = " ".join(text.split()).strip()
            if not text or text[0] in "#<":
                continue
            msgs.append(("ユーザー" if role == "user" else "エージェント") + ": " + text[:400])
except Exception:
    raise SystemExit(0)
excerpt = "\n".join(msgs[-6:])[-2000:]
if not excerpt:
    raise SystemExit(0)
# First line = session id, rest = excerpt.
print(sid)
print(excerpt)
PY
)"

[ -n "$excerpt_and_session" ] || exit 0
session="$(printf '%s' "$excerpt_and_session" | head -n1)"
excerpt="$(printf '%s' "$excerpt_and_session" | tail -n +2)"
[ -n "$excerpt" ] || exit 0

printf '%s' "$excerpt" | "$HOME/.local/bin/herdr-agent-name" --kind codex --session "${session:-$HERDR_PANE_ID}" >/dev/null 2>&1 || true
exit 0
