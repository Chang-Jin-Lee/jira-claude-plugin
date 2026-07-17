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
    next_page_token = None
    while True:
        params = {"jql": jql, "maxResults": 100, "fields": "summary"}
        if next_page_token:
            params["nextPageToken"] = next_page_token
        resp = requests.get(
            f"{creds['jira_url']}/rest/api/3/search/jql",
            auth=_auth(creds),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("issues", [])
        for issue in page:
            issues.append({"key": issue["key"], "name": issue["fields"]["summary"]})
        next_page_token = data.get("nextPageToken")
        if not next_page_token or data.get("isLast"):
            break
    return issues


def list_board_issues(creds: dict, board_key: str) -> list[dict]:
    return _search(creds, f"project = {board_key}")


def list_issue_children(creds: dict, issue_key: str) -> list[dict]:
    return _search(creds, f"parent = {issue_key}")


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["clip"], input=text.encode("utf-8"), check=True)


from textual.app import App
from textual.widgets import Static, Tree


class BrowseApp(App):
    def __init__(
        self,
        credentials: dict,
        boards_fn=list_boards,
        board_issues_fn=list_board_issues,
        issue_children_fn=list_issue_children,
        copy_fn=copy_to_clipboard,
    ):
        super().__init__()
        self.credentials = credentials
        self.boards_fn = boards_fn
        self.board_issues_fn = board_issues_fn
        self.issue_children_fn = issue_children_fn
        self.copy_fn = copy_fn

    def compose(self):
        yield Tree("Jira boards")
        yield Static(id="status")

    def on_mount(self) -> None:
        tree = self.query_one(Tree)
        tree.root.expand()
        for board in self.boards_fn(self.credentials):
            tree.root.add(
                f"{board['key']} — {board['name']}",
                data={"key": board["key"], "kind": "board", "loaded": False},
            )

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        data = node.data
        if data is None or data.get("loaded"):
            return
        status = self.query_one("#status", Static)
        try:
            if data["kind"] == "board":
                children = self.board_issues_fn(self.credentials, data["key"])
            else:
                children = self.issue_children_fn(self.credentials, data["key"])
        except requests.RequestException as exc:
            status.update(f"[red]{data['key']} 조회 실패: {exc} - 다시 펼쳐서 재시도하세요[/red]")
            return
        data["loaded"] = True
        status.update("")
        if not children:
            node.allow_expand = False
            return
        for child in children:
            node.add(
                f"{child['key']} — {child['name']}",
                data={"key": child["key"], "kind": "issue", "loaded": False},
            )

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if data is None:
            return
        self.copy_fn(data["key"])
        self.exit(result=data["key"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    creds = load_credentials(credentials_path())
    if creds is None:
        print(
            "자격증명 파일이 없습니다 - 이 플러그인이 활성화된 Claude Code "
            "세션을 한 번 시작한 뒤 다시 실행하세요."
        )
        return 1
    app = BrowseApp(creds)
    result = app.run()
    if result:
        print(f"{result} 을(를) 클립보드에 복사했습니다 - Claude Code로 돌아가 붙여넣으세요.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
