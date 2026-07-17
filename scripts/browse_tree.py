#!/usr/bin/env python3
"""Standalone Jira board/issue tree browser. Run directly by the user from
their own shell (never by Claude Code or a hook) so it gets a real
attached terminal for arrow-key input.
"""
import json
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_credentials import credentials_path  # noqa: E402


def load_credentials(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _auth(creds: dict) -> tuple[str, str]:
    return (creds["jira_email"], creds["jira_api_token"])


def list_boards(creds: dict) -> list[dict]:
    boards = []
    start_at = 0
    while True:
        resp = requests.get(
            f"{creds['jira_url']}/rest/agile/1.0/board",
            auth=_auth(creds),
            params={"startAt": start_at},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", [])
        for value in values:
            key = value.get("location", {}).get("projectKey") or str(value["id"])
            boards.append({"key": key, "name": value["name"]})
        if data.get("isLast", True) or not values:
            break
        start_at += len(values)
    return boards


def _search(creds: dict, jql: str) -> list[dict]:
    issues = []
    start_at = 0
    while True:
        resp = requests.get(
            f"{creds['jira_url']}/rest/api/2/search",
            auth=_auth(creds),
            params={"jql": jql, "startAt": start_at, "maxResults": 100},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("issues", [])
        for issue in page:
            issues.append({"key": issue["key"], "name": issue["fields"]["summary"]})
        start_at += len(page)
        if not page or start_at >= data.get("total", start_at):
            break
    return issues


def list_board_issues(creds: dict, board_key: str) -> list[dict]:
    return _search(creds, f"project = {board_key}")


def list_issue_children(creds: dict, issue_key: str) -> list[dict]:
    return _search(creds, f"parent = {issue_key}")


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
