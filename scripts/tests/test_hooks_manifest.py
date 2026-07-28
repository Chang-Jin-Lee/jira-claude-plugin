"""The SessionStart hook wiring.

A hook naming an executable that isn't installed fails loudly every single
session ("Executable not found in $PATH: ..."), and Claude Code offers no way
to scope a hook to one platform. Shipping an `sh` hook therefore broke every
Windows machine without Git Bash, and a `powershell` hook would break macOS
and Linux the same way. Only `uv` may be named here — it is what the plugin
requires anyway, and the skill bootstraps it when it is absent.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))

PLATFORM_SPECIFIC = {"sh", "bash", "powershell", "pwsh", "cmd", "python", "python3"}


def hook_commands():
    for group in HOOKS["hooks"].values():
        for entry in group:
            for hook in entry["hooks"]:
                yield hook["command"]


def test_no_hook_names_a_platform_specific_interpreter():
    named = set(hook_commands())
    offenders = named & PLATFORM_SPECIFIC
    assert not offenders, (
        f"{offenders} is not present on every platform; a hook naming it "
        "errors on every session of the machines that lack it"
    )


def test_session_start_only_runs_the_credential_sync():
    assert list(hook_commands()) == ["uv"]


def test_hook_runs_with_no_project_so_it_ignores_the_user_project():
    for group in HOOKS["hooks"]["SessionStart"]:
        for hook in group["hooks"]:
            assert "--no-project" in hook["args"]
