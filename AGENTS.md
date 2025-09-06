# Repository Guidelines

## Project Structure & Module Organization
- Root: dotfiles managed with `chezmoi` for Arch/EndeavourOS.
- Home dotfiles: files prefixed with `dot_` (e.g., `dot_zshrc`, `dot_gitconfig`).
- Private files: files/directories prefixed with `private_` (e.g., `private_dot_ssh`, `private_dot_config/hypr`). These are intended for sensitive or user-specific settings.
- System configs: `etc/` holds machine-wide files applied by scripts (e.g., `etc/keyd/default.conf`).
- Data/templates: `.chezmoidata/` for data values used by templates; avoid secrets here.
- Scripts: `run_onchange_*.sh` are chezmoi hooks executed on apply when they change (e.g., `run_onchange_setup.sh`).
- Extras: `dot_local/` mirrors `~/.local` (e.g., `dot_local/bin`).

## Build, Test, and Development Commands
- `chezmoi diff`: preview changes against `$HOME` before applying.
- `chezmoi apply -v`: apply dotfiles to your system with verbose output.
- `chezmoi add -v <path>`: import a file from `$HOME` into the repo (e.g., `chezmoi add -v ~/.zshrc`).
- `chezmoi doctor`: diagnose environment issues.
- Script checks: `bash -n run_onchange_setup.sh`; if available, run `shellcheck run_onchange_setup.sh`.

## Coding Style & Naming Conventions
- Shell scripts: Bash, `set -eu`, prefer small, idempotent functions; keep comments concise.
- File naming: `dot_*` → `~/*` and `~/.config/*` (via `dot_config/...`); `private_*` for sensitive paths; `etc/*` for system-level files applied by scripts.
- Keep OS assumptions explicit (Arch/EndeavourOS); gate machine-specific logic in scripts.

## Testing Guidelines
- No unit test suite. Validate changes via `chezmoi diff` and `chezmoi apply --dry-run` where appropriate.
- For risky changes, test in a disposable user/container. Capture before/after with `chezmoi diff` in the PR.

## Commit & Pull Request Guidelines
- Commits: follow Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`). Keep messages imperative and scoped.
- PRs: include purpose, affected areas (e.g., `private_dot_config/waybar`), screenshots for UI changes, OS/desktop context, and test plan (`chezmoi diff` output and key commands run).

## Security & Configuration Tips
- Do not commit secrets. Use `private_*` with restrictive permissions and consider `.chezmoiignore`/templates to exclude host-specific data.
- Avoid hardcoding tokens, keys, or personal identifiers. Prefer environment variables or local-only files ignored by git.

