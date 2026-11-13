#!/usr/bin/env python3
"""Import 1Password references once into a private, unmanaged Espanso match file."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def restart_espanso(enabled):
    if not enabled:
        return True
    path = os.environ.get("PATH", os.defpath) + ":/opt/homebrew/bin:/usr/local/bin"
    espanso = shutil.which("espanso", path=path)
    if not espanso:
        print("Espanso is not installed; restart it after installation.", file=sys.stderr)
        return False
    result = subprocess.run([espanso, "restart"], capture_output=True, text=True)
    if result.returncode:
        print("Local matches are available, but Espanso restart failed. Run: espanso restart", file=sys.stderr)
    return result.returncode == 0


def load_manifest(path):
    references = json.loads(path.read_text())
    if not isinstance(references, dict) or not references:
        raise ValueError
    for trigger, reference in references.items():
        if not isinstance(trigger, str) or not trigger.startswith("z"):
            raise ValueError
        if not isinstance(reference, str) or not reference.startswith("op://"):
            raise ValueError
    return references


def load_existing(path):
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    matches = document["matches"]
    if not isinstance(matches, list):
        raise ValueError
    existing = {}
    for match in matches:
        if not isinstance(match, dict) or not isinstance(match.get("trigger"), str):
            raise ValueError
        if not isinstance(match.get("replace"), str) or "vars" in match:
            raise ValueError
        if match["trigger"] in existing:
            raise ValueError
        existing[match["trigger"]] = match
    return existing


def write_matches(path, matches):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".espanso-local-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"matches": matches}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true", help="Explicitly re-read references; successful reads replace local edits")
    parser.add_argument("--no-restart", action="store_true", help="Let the setup script restart Espanso instead")
    args = parser.parse_args()
    output = args.config_dir / "match/private.local.yml"

    if output.is_symlink() or (output.exists() and not output.is_file()):
        print("Local match path must be a regular file; nothing was changed.", file=sys.stderr)
        return 1

    # Re-applying dotfiles must never prompt for authentication or replace local edits.
    if output.exists() and not args.refresh:
        try:
            output.chmod(0o600)
        except OSError:
            print("Cannot restrict local match file permissions; nothing was imported.", file=sys.stderr)
            return 1
        print(f"Using existing local matches (no 1Password access): {output}")
        return 0 if restart_espanso(not args.no_restart) else 1

    try:
        references = load_manifest(args.config_dir / "onepassword-references.json")
        existing = load_existing(output)
    except (OSError, ValueError, KeyError, TypeError):
        print("Invalid references or local JSON match file; existing values were not changed.", file=sys.stderr)
        return 1

    environment = dict(os.environ)
    for name in ("OP_SERVICE_ACCOUNT_TOKEN", "OP_CONNECT_TOKEN", "OP_CONNECT_HOST"):
        environment.pop(name, None)
    environment["PATH"] = environment.get("PATH", os.defpath) + ":/opt/homebrew/bin:/usr/local/bin"
    op = shutil.which("op", path=environment["PATH"])
    if not op:
        print("1Password CLI is unavailable; existing local matches were not changed.", file=sys.stderr)
        return 1
    failures = []
    imported = 0
    matches = dict(existing)
    for trigger, reference in references.items():
        try:
            result = subprocess.run(
                [op, "read", "--no-newline", reference],
                env=environment, capture_output=True, text=True, timeout=60,
            )
            value = result.stdout if result.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            value = ""
        if value:
            matches[trigger] = {"trigger": trigger, "word": True, "replace": value}
            imported += 1
        else:
            failures.append(trigger)
            # Keep previous values; on first import leave the trigger untouched for manual editing.
            matches.setdefault(trigger, {"trigger": trigger, "word": True, "replace": trigger})

    if imported == 0:
        print("No fields could be imported; existing local matches were not changed.", file=sys.stderr)
        return 1

    try:
        write_matches(output, list(matches.values()))
    except OSError:
        print("Cannot write the local match file; existing values were not changed.", file=sys.stderr)
        return 1
    print(f"Imported {imported} fields into {output} (permissions: 0600). Values were not printed.")
    if failures:
        print("Not imported (previous values kept, otherwise edit replace locally): " + ", ".join(failures), file=sys.stderr)
    restarted = restart_espanso(not args.no_restart)
    return 1 if failures or not restarted else 0


if __name__ == "__main__":
    raise SystemExit(main())
