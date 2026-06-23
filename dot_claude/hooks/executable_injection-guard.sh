#!/usr/bin/env bash
# PreToolUse guard against prompt-injection-driven RCE / credential exfiltration.
# Denies, regardless of permission mode:
#   1) remote fetch piped to an interpreter   (curl ... | bash)
#   2) interpreter running a remote fetch      (bash <(curl ...), sh -c "$(curl ...)")
#   3) outbound mail                            (mail/sendmail/... — exfil channel)
#   4) 1Password secret reads                   (op item/read/signin/document)
#   5) curl/wget referencing a secret file      (.env, id_rsa, aws/ssh creds)
# Single curl/wget (e.g. docker healthcheck) is intentionally allowed.
# Wired in ~/.claude/settings.json -> hooks.PreToolUse (matcher: Bash).
set -uo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[ -z "$cmd" ] && exit 0

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$1"
  exit 0
}

if printf '%s' "$cmd" | grep -Eq '(curl|wget|fetch)\b.*\|[[:space:]]*\b(bash|sh|zsh|python|perl|node)\b'; then
  deny "injection-guard: remote fetch piped to a shell/interpreter is blocked (curl|bash class)."
fi
if printf '%s' "$cmd" | grep -Eq '\b(bash|sh|zsh|python|perl|node)\b[[:space:]]+(-c[[:space:]])?[^&;]*[<$]\([[:space:]]*(curl|wget)'; then
  deny "injection-guard: executing a remotely fetched script is blocked."
fi
if printf '%s' "$cmd" | grep -Eq '(^|[;|&[:space:]])(sendmail|mailx|ssmtp|swaks|mutt|mail)[[:space:]]'; then
  deny "injection-guard: outbound mail command blocked (possible credential exfiltration)."
fi
if printf '%s' "$cmd" | grep -Eq '\bop[[:space:]]+(item|read|signin|document)\b'; then
  deny "injection-guard: 1Password secret read blocked."
fi
if printf '%s' "$cmd" | grep -Eq '(curl|wget)\b[^|;&]*(\.env|env\.runtime|id_rsa|\.aws/credentials|\.ssh/id_)'; then
  deny "injection-guard: network transfer referencing a secret file blocked."
fi
exit 0
