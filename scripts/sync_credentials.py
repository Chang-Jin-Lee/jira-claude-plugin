#!/usr/bin/env python3
"""The plugin's SessionStart hook. Syncs Jira credentials from this hook
process's environment to a fixed local file, keeps the Jira MCP server's
package downloaded, and announces the standalone tree-browser command.

The file is the standalone tree browser's only source of credentials, and a
fallback for the MCP wrapper, which starts concurrently with this hook. So
writes are atomic (temp file + ``os.replace``) and skipped entirely when the
stored values already match — a reader must never observe a half-written
file.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server_package  # noqa: E402

ENV_KEYS = {
    "jira_url": "CLAUDE_PLUGIN_OPTION_JIRA_URL",
    "jira_email": "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL",
    "jira_api_token": "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN",
}
# What mcp-atlassian itself reads, and what a Codex CLI or plain-shell user
# exports by hand. Shared with run_mcp.py so there is one definition.
DIRECT_ENV_KEYS = {
    "jira_url": "JIRA_URL",
    "jira_email": "JIRA_USERNAME",
    "jira_api_token": "JIRA_API_TOKEN",
}


def build_credentials(env: dict) -> dict | None:
    creds = {key: env.get(var, "") for key, var in ENV_KEYS.items()}
    if not all(creds.values()):
        return None
    return creds


def credentials_path() -> Path:
    return Path.home() / ".jira-claude-plugin" / "credentials.json"


def read_credentials(path: Path) -> dict | None:
    """Return the stored credentials, or None if the file is absent,
    unreadable, not yet complete, or mid-write."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not all(data.get(key) for key in ENV_KEYS):
        return None
    return {key: data[key] for key in ENV_KEYS}


def write_credentials(creds: dict, path: Path) -> bool:
    """Publish creds atomically. Returns False without touching the file when
    it already holds exactly these values."""
    if read_credentials(path) == creds:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(creds), encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return True


def creds_from_env_vars(env: dict, keys: dict) -> dict | None:
    """Credentials read straight out of an environment mapping, or None if any
    is unset or is still an unexpanded ``${...}`` reference rather than a
    value."""
    creds = {key: env.get(var, "").strip() for key, var in keys.items()}
    if not all(creds.values()) or any("${" in value for value in creds.values()):
        return None
    return creds


def load_credentials(path: Path) -> dict | None:
    """Credentials for a caller outside Claude Code: the synced file if it
    holds a complete set, else the environment. Codex CLI and plain shells
    have no session hook to write the file."""
    return read_credentials(path) or creds_from_env_vars(dict(os.environ), DIRECT_ENV_KEYS)


def browse_command_hint(plugin_root: str) -> str:
    script = f"{plugin_root}/scripts/browse_tree.py"
    return (
        "보드/이슈를 화살표키로 탐색하려면 새 터미널에서 다음을 실행하세요: "
        f'uv run --no-project --with textual,requests "{script}"'
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    path = credentials_path()
    creds = build_credentials(dict(os.environ))
    if creds is not None:
        write_credentials(creds, path)
        configured = True
    else:
        # No options in this hook's environment. Already-stored credentials
        # stay valid, so only ask the user to configure when there are none.
        configured = read_credentials(path) is not None

    # The MCP server starts before this hook and only ever launches from the
    # cache, so downloading the server package is this hook's job. Do it even
    # before Jira is configured: on a new machine that download is the long
    # pole, and the minutes the user spends pasting in their API token are
    # exactly when it is free.
    notice = server_package.prepare(path.parent, time.time())
    if notice:
        print(notice)

    if not configured:
        print(
            "Jira 설정이 아직 없습니다 - /plugin 에서 jira_url/jira_email/"
            "jira_api_token을 채운 뒤 새 세션을 시작하세요."
        )
        return 0
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", ".")
    print(browse_command_hint(plugin_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
