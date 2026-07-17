#!/usr/bin/env python3
"""Sync Jira credentials from this hook process's environment to a fixed
local file, and announce the standalone tree-browser command. Run once per
session by a SessionStart hook.
"""
import json
import os
import sys
from pathlib import Path

ENV_KEYS = {
    "jira_url": "CLAUDE_PLUGIN_OPTION_JIRA_URL",
    "jira_email": "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL",
    "jira_api_token": "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN",
}


def build_credentials(env: dict) -> dict | None:
    creds = {key: env.get(var, "") for key, var in ENV_KEYS.items()}
    if not all(creds.values()):
        return None
    return creds


def credentials_path() -> Path:
    return Path.home() / ".jira-claude-plugin" / "credentials.json"


def write_credentials(creds: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(creds), encoding="utf-8")


def browse_command_hint(plugin_root: str) -> str:
    script = f"{plugin_root}/scripts/browse_tree.py"
    return (
        "보드/이슈를 화살표키로 탐색하려면 새 터미널에서 다음을 실행하세요: "
        f'uv run --with textual,requests "{script}"'
    )


def main() -> int:
    creds = build_credentials(dict(os.environ))
    if creds is None:
        print(
            "Jira 설정이 아직 없습니다 - /plugin 에서 jira_url/jira_email/"
            "jira_api_token을 채운 뒤 새 세션을 시작하세요."
        )
        return 0
    write_credentials(creds, credentials_path())
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", ".")
    print(browse_command_hint(plugin_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
