# Repository Guidelines

## Project Structure & Module Organization
The repo is a chezmoi source tree for Arch/EndeavourOS. Files prefixed with `dot_` mirror home dotfiles (`dot_zshrc`, `dot_tmux.conf`), while `dot_local/` shadows `~/.local` assets such as scripts in `dot_local/bin/`. Sensitive data and host overrides live under `private_*` (for example, `private_dot_config/hypr/`). Machine-wide configs belong in `etc/`, and reusable values go in `.chezmoidata/`. Keep helper scripts in `run_onchange_*.sh`, updating `run_onchange_setup.sh` when automation is required.

## Build, Test, and Development Commands
Run `chezmoi diff` before every change to preview what will touch `$HOME`. Apply changes with `chezmoi apply -v` or `chezmoi apply --dry-run` for a safer rehearsal. Import new files from your environment with `chezmoi add -v <path>`. Validate the workstation with `chezmoi doctor`. For scripts, run `bash -n run_onchange_setup.sh` and, when installed, `shellcheck run_onchange_setup.sh`.

## Coding Style & Naming Conventions
Shell scripts target Bash; start them with `#!/usr/bin/env bash` and `set -eu`. Prefer small idempotent functions, explicit `case` statements for OS-specific branches, and consistent two-space indentation. Keep comments brief and functional. Follow existing naming: `dot_config/<app>/` for config directories, `private_*` for secrets, and avoid hardcoded hostnames.

## Testing Guidelines
There is no automated test suite. Rely on `chezmoi diff` and `chezmoi apply --dry-run` to confirm template output. After editing shell helpers, run the lint commands above and execute scripts in a disposable shell when risky. Capture before/after snapshots or screenshots when desktop tooling is affected.

## Commit & Pull Request Guidelines
Commits use Conventional Commit prefixes (`feat:`, `fix:`, `chore:`, `refactor:`) and should scope changes tightly. Pull requests need a clear purpose, impacted paths (e.g., `private_dot_config/waybar/`), OS or desktop context, and the key commands run (`chezmoi diff`, validators). Attach screenshots for UI tweaks and link related issues when available.

## Security & Configuration Tips
Never commit secrets. Store credentials only under `private_*` paths with restrictive permissions, and template host-specific values so they can be ignored via `.chezmoiignore` when necessary. Avoid embedding API tokens; prefer environment variables or local-only overrides.
