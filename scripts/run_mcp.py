#!/usr/bin/env python3
"""Launch the bundled mcp-atlassian server with Jira credentials injected
from the plugin's synced credentials file.

Workaround for anthropics/claude-code#51573: ``${user_config.*}``
references in a plugin .mcp.json ``env`` block reach the server process
unexpanded, so the documented mechanism cannot deliver the user's Jira
settings. The SessionStart hook already syncs them to
``~/.jira-claude-plugin/credentials.json`` for the standalone tree browser;
this wrapper reuses that file. The hook and the MCP server both start with
the session in no guaranteed order, so the wrapper waits briefly for the
file on a genuinely first-ever session.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_credentials import credentials_path  # noqa: E402

ENV_MAP = {
    "JIRA_URL": "jira_url",
    "JIRA_USERNAME": "jira_email",
    "JIRA_API_TOKEN": "jira_api_token",
}


def build_env(creds: dict, base_env: dict) -> dict:
    env = dict(base_env)
    for var, key in ENV_MAP.items():
        env[var] = creds[key]
    env["READ_ONLY_MODE"] = "true"
    return env


def wait_for_credentials(path: Path, attempts: int = 5, delay: float = 2.0) -> dict | None:
    for attempt in range(attempts):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if attempt < attempts - 1:
            time.sleep(delay)
    return None


def main() -> int:
    creds = wait_for_credentials(credentials_path())
    if creds is None:
        print(
            "jira-claude-plugin: credentials file not found - configure the "
            "plugin via /plugin (jira_url/jira_email/jira_api_token) and "
            "start a new session.",
            file=sys.stderr,
        )
        return 1
    proc = subprocess.run(["uvx", "mcp-atlassian"], env=build_env(creds, dict(os.environ)))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
