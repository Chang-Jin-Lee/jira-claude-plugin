# Standalone-Command Tree Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user browse Jira boards/issues in a real arrow-key terminal tree, launched as a standalone command outside Claude Code, and hand the picked key back into the `jira-to-backlog` skill by pasting it — replacing the hook-launched-TUI approach the TTY spike proved infeasible.

**Architecture:** A `SessionStart` hook syncs the plugin's Jira credentials to a fixed home-relative file and announces the exact launch command every session. A fully standalone `textual`-based script the user runs directly from their own shell reads that file, browses Jira via direct REST calls with lazy per-node fetching, and copies the selected key to the clipboard on Enter. The existing skill gains issue-key detection so a pasted issue key crawls that single issue instead of a whole board.

**Tech Stack:** Python (via `uv run`, no permanent install), `textual` (Tree widget + Pilot testing), `requests` (direct Jira REST calls), `pytest` + `pytest-asyncio` + `requests-mock` for tests, Claude Code plugin hooks (`hooks/hooks.json`).

## Global Constraints

- Windows only for this pass — clipboard copy uses `clip.exe` directly; no
  macOS/Linux clipboard support.
- No permanent install for either script — always run via `uv run --with
  <deps> <script>`.
- The Jira API token must never be visible to the model — not in skill
  text, not in a Bash command, not in any transcript.
- Read-only: never call a Jira tool/endpoint that writes, transitions, or
  creates issues.
- Credentials sync file path is fixed at `~/.jira-claude-plugin/credentials.json`
  (home-relative, NOT under the plugin's versioned install directory, so
  it survives plugin updates).
- `SessionStart` hook uses no `matcher` (fires on every session).
- `hooks/hooks.json` at the plugin root IS auto-discovered — do NOT add an
  explicit `"hooks": "./hooks/hooks.json"` field to `.claude-plugin/plugin.json`.
  (Correction to a belief carried over from the TTY spike: live testing
  during Task 2 proved the explicit field causes a "Duplicate hooks file
  detected" load error, since the standard path is already loaded
  automatically. `manifest.hooks` is only for *additional* hook files
  beyond the standard one.)
- Every task that changes `hooks/hooks.json`, `plugin.json`, or any file
  a hook depends on must bump the `"version"` field in both
  `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` —
  confirmed during the TTY spike that `/plugin update` is a silent no-op
  otherwise.
- Work directly on `master` (already-approved convention for this repo —
  no feature branch/worktree).
- Verification tool available: `claude plugin validate <path>`.
- All commands below are written relative to the repo root.

---

### Task 1: Credential sync script

**Files:**
- Create: `scripts/sync_credentials.py`
- Create: `scripts/tests/conftest.py`
- Create: `scripts/tests/test_sync_credentials.py`

**Interfaces:**
- Consumes: nothing (first task in this plan).
- Produces: `build_credentials(env: dict) -> dict | None`,
  `credentials_path() -> pathlib.Path`,
  `write_credentials(creds: dict, path: pathlib.Path) -> None`,
  `browse_command_hint(plugin_root: str) -> str`, `main() -> int` — all in
  `scripts/sync_credentials.py`. Task 4's `browse_tree.py` imports
  `credentials_path` from this module (do not duplicate the path
  constant).

- [ ] **Step 1: Write the test helper that makes `scripts/` importable**

Create `scripts/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: Write the failing tests**

Create `scripts/tests/test_sync_credentials.py`:

```python
import json

import sync_credentials as sc


def test_build_credentials_returns_dict_when_all_present():
    env = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "https://x.atlassian.net",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "a@b.com",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "tok",
    }
    result = sc.build_credentials(env)
    assert result == {
        "jira_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "tok",
    }


def test_build_credentials_returns_none_when_missing():
    env = {
        "CLAUDE_PLUGIN_OPTION_JIRA_URL": "https://x.atlassian.net",
        "CLAUDE_PLUGIN_OPTION_JIRA_EMAIL": "",
        "CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN": "tok",
    }
    assert sc.build_credentials(env) is None


def test_write_credentials_writes_json_to_path(tmp_path):
    creds = {"jira_url": "u", "jira_email": "e", "jira_api_token": "t"}
    target = tmp_path / "nested" / "credentials.json"
    sc.write_credentials(creds, target)
    assert json.loads(target.read_text(encoding="utf-8")) == creds


def test_browse_command_hint_includes_resolved_path():
    hint = sc.browse_command_hint("/plugin/root")
    assert "/plugin/root/scripts/browse_tree.py" in hint
    assert "uv run --with textual,requests" in hint


def test_main_writes_file_and_prints_hint(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", "https://x.atlassian.net")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", "a@b.com")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", "tok")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/plugin/root")
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    exit_code = sc.main()
    assert exit_code == 0
    written = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    assert written["jira_url"] == "https://x.atlassian.net"
    captured = capsys.readouterr()
    assert "/plugin/root/scripts/browse_tree.py" in captured.out


def test_main_skips_write_when_incomplete(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_URL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_EMAIL", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(sc, "credentials_path", lambda: tmp_path / "credentials.json")
    exit_code = sc.main()
    assert exit_code == 0
    assert not (tmp_path / "credentials.json").exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --with pytest pytest scripts/tests/test_sync_credentials.py -v`
Expected: `ModuleNotFoundError: No module named 'sync_credentials'` (the file
doesn't exist yet).

- [ ] **Step 4: Write the implementation**

Create `scripts/sync_credentials.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --with pytest pytest scripts/tests/test_sync_credentials.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add scripts/sync_credentials.py scripts/tests/conftest.py scripts/tests/test_sync_credentials.py
git commit -m "Add credential-sync script for standalone tree browser"
```

---

### Task 2: Wire the SessionStart hook and verify it fires live

**Files:**
- Modify: `hooks/hooks.json` (replace the spike's diagnostic
  `UserPromptExpansion` entries entirely)
- Modify: `.claude-plugin/plugin.json` (version bump)
- Modify: `.claude-plugin/marketplace.json` (version bump)

**Interfaces:**
- Consumes: `scripts/sync_credentials.py` from Task 1 (run as-is via `uv
  run`, no code-level interface — it's invoked as a subprocess by the
  hook).
- Produces: a live `~/.jira-claude-plugin/credentials.json` file and a
  browse-command hint visible at the start of every session, for Task 4's
  manual end-to-end check and Task 6's final verification to rely on.

- [ ] **Step 1: Replace the hooks file**

Replace the full contents of `hooks/hooks.json` with:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv",
            "args": ["run", "${CLAUDE_PLUGIN_ROOT}/scripts/sync_credentials.py"]
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Bump the plugin version**

In `.claude-plugin/plugin.json`, change the `"version"` field from
`"0.1.1"` to `"0.1.2"`.

In `.claude-plugin/marketplace.json`, change the `"version"` field inside
the `plugins[0]` entry from `"0.1.1"` to `"0.1.2"` (must match
`plugin.json` exactly).

- [ ] **Step 3: Validate the plugin**

Run: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 4: Commit**

```bash
git add hooks/hooks.json .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "Replace TTY-spike hooks with SessionStart credential sync"
git push origin master
```

- [ ] **Step 5: Update the installed plugin and start a brand-new session (requires a human, not a subagent)**

`SessionStart` only fires when a session *starts* — `/reload-plugins`
does not trigger it, since that reloads an already-running session
in place. In a live Claude Code session:

```
/plugin update jira-claude-plugin
```

Expected: `✔ Updated jira-claude-plugin. Run /reload-plugins to apply.`
(if this instead reports no update available, the version bump in Step 2
didn't take — check `.claude-plugin/plugin.json`'s `"version"` field was
actually changed and pushed).

Then exit this session entirely and start a completely new one (close
the terminal / run `claude` again fresh) in this same repo directory.

- [ ] **Step 6: Confirm the sync fired (requires a human)**

In that brand-new session, check for either:
- A line reading `보드/이슈를 화살표키로 탐색하려면...` appearing near
  the start of the conversation (SessionStart's stdout is added as
  context), or
- If Jira wasn't configured yet, a line reminding to run `/plugin` first.

Then, outside Claude Code, in any terminal:

```
cat ~/.jira-claude-plugin/credentials.json
```

(PowerShell: `Get-Content ~/.jira-claude-plugin/credentials.json`)

Expected: a JSON object with `jira_url`, `jira_email`, `jira_api_token`
matching the values configured via `/plugin` for this plugin. If the file
is missing, check the hint from Step 6 of the TTY spike's ledger
(`.superpowers/sdd/progress.md`) for known hook-wiring pitfalls (matcher
form, `plugin.json`'s `"hooks"` field, plain-text vs JSON stdout) before
assuming this is a new bug — record whatever is found either way.

---

### Task 3: Jira REST data functions for the browser

**Files:**
- Create: `scripts/browse_tree.py`
- Create: `scripts/tests/test_browse_tree_data.py`

**Interfaces:**
- Consumes: `credentials_path` from `scripts/sync_credentials.py` (Task 1).
- Produces: `load_credentials(path: pathlib.Path) -> dict | None`,
  `list_boards(creds: dict) -> list[dict]`,
  `list_board_issues(creds: dict, board_key: str) -> list[dict]`,
  `list_issue_children(creds: dict, issue_key: str) -> list[dict]`,
  `copy_to_clipboard(text: str) -> None` — all in `scripts/browse_tree.py`.
  Each list function returns a list of `{"key": str, "name": str}` dicts.
  Task 4 imports and wires all five into the `textual` app.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_browse_tree_data.py`:

```python
import json

import browse_tree as bt


CREDS = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}


def test_load_credentials_returns_none_when_missing(tmp_path):
    assert bt.load_credentials(tmp_path / "nope.json") is None


def test_load_credentials_reads_json(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    assert bt.load_credentials(path) == CREDS


def test_list_boards_returns_key_and_name(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/agile/1.0/board",
        json={
            "values": [{"id": 1, "name": "KAN board", "location": {"projectKey": "KAN"}}],
            "isLast": True,
        },
    )
    assert bt.list_boards(CREDS) == [{"key": "KAN", "name": "KAN board"}]


def test_list_boards_falls_back_to_id_when_no_project_key(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/agile/1.0/board",
        json={"values": [{"id": 7, "name": "Filter board", "location": {}}], "isLast": True},
    )
    assert bt.list_boards(CREDS) == [{"key": "7", "name": "Filter board"}]


def test_list_boards_paginates_across_multiple_pages(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/agile/1.0/board",
        [
            {
                "json": {
                    "values": [{"id": 1, "name": "First", "location": {"projectKey": "AAA"}}],
                    "isLast": False,
                }
            },
            {
                "json": {
                    "values": [{"id": 2, "name": "Second", "location": {"projectKey": "BBB"}}],
                    "isLast": True,
                }
            },
        ],
    )
    boards = bt.list_boards(CREDS)
    assert boards == [{"key": "AAA", "name": "First"}, {"key": "BBB", "name": "Second"}]


def test_list_board_issues_returns_key_and_summary(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/api/2/search",
        json={"issues": [{"key": "KAN-1", "fields": {"summary": "First"}}], "total": 1},
    )
    assert bt.list_board_issues(CREDS, "KAN") == [{"key": "KAN-1", "name": "First"}]


def test_list_issue_children_returns_key_and_summary(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/api/2/search",
        json={"issues": [{"key": "KAN-2", "fields": {"summary": "Child"}}], "total": 1},
    )
    assert bt.list_issue_children(CREDS, "KAN-1") == [{"key": "KAN-2", "name": "Child"}]


def test_list_board_issues_paginates_across_multiple_pages(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/api/2/search",
        [
            {"json": {"issues": [{"key": "KAN-1", "fields": {"summary": "First"}}], "total": 2}},
            {"json": {"issues": [{"key": "KAN-2", "fields": {"summary": "Second"}}], "total": 2}},
        ],
    )
    issues = bt.list_board_issues(CREDS, "KAN")
    assert issues == [{"key": "KAN-1", "name": "First"}, {"key": "KAN-2", "name": "Second"}]


def test_copy_to_clipboard_invokes_clip(monkeypatch):
    calls = []

    def fake_run(cmd, input, check):
        calls.append((cmd, input, check))

    monkeypatch.setattr(bt.subprocess, "run", fake_run)
    bt.copy_to_clipboard("KAN-248")
    assert calls == [(["clip"], b"KAN-248", True)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest,requests,requests-mock pytest scripts/tests/test_browse_tree_data.py -v`
Expected: `ModuleNotFoundError: No module named 'browse_tree'`

- [ ] **Step 3: Write the implementation**

Create `scripts/browse_tree.py`:

```python
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
```

(The `textual` app and `main()` entry point are added in Task 4 — this
task only produces the data functions above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest,requests,requests-mock pytest scripts/tests/test_browse_tree_data.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/browse_tree.py scripts/tests/test_browse_tree_data.py
git commit -m "Add Jira REST data functions for the standalone tree browser"
```

---

### Task 4: Textual tree UI and entry point

**Files:**
- Modify: `scripts/browse_tree.py` (append the app + entry point)
- Create: `scripts/tests/test_browse_tree_app.py`

**Interfaces:**
- Consumes: `load_credentials`, `list_boards`, `list_board_issues`,
  `list_issue_children`, `copy_to_clipboard`, `credentials_path` (all from
  Task 1/3, already in `scripts/browse_tree.py`).
- Produces: `BrowseApp` (a `textual.app.App` subclass) and `main() -> int`
  in `scripts/browse_tree.py`. Nothing later in this plan consumes these
  programmatically — they're the script's own CLI entry point.

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_browse_tree_app.py`:

```python
import pytest
from textual.widgets import Tree

import browse_tree as bt

CREDS = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}


@pytest.mark.asyncio
async def test_boards_load_on_mount():
    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        assert len(tree.root.children) == 1
        board_node = tree.root.children[0]
        assert board_node.data == {"key": "KAN", "kind": "board", "loaded": False}


@pytest.mark.asyncio
async def test_expanding_board_node_loads_issues_lazily():
    calls = []

    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    def fake_board_issues(creds, key):
        calls.append(key)
        return [{"key": "KAN-1", "name": "First"}]

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards, board_issues_fn=fake_board_issues)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        board_node = tree.root.children[0]
        assert calls == []
        board_node.expand()
        await pilot.pause()
        assert calls == ["KAN"]
        assert len(board_node.children) == 1
        assert board_node.children[0].data == {"key": "KAN-1", "kind": "issue", "loaded": False}


@pytest.mark.asyncio
async def test_expanding_issue_node_loads_children_not_boards():
    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    def fake_board_issues(creds, key):
        return [{"key": "KAN-1", "name": "First"}]

    def fake_issue_children(creds, key):
        return [{"key": "KAN-2", "name": "Sub"}]

    app = bt.BrowseApp(
        CREDS,
        boards_fn=fake_boards,
        board_issues_fn=fake_board_issues,
        issue_children_fn=fake_issue_children,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        board_node = tree.root.children[0]
        board_node.expand()
        await pilot.pause()
        issue_node = board_node.children[0]
        issue_node.expand()
        await pilot.pause()
        assert len(issue_node.children) == 1
        assert issue_node.children[0].data["key"] == "KAN-2"


@pytest.mark.asyncio
async def test_expanding_node_with_no_children_disallows_further_expand():
    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    def fake_board_issues(creds, key):
        return []

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards, board_issues_fn=fake_board_issues)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        board_node = tree.root.children[0]
        board_node.expand()
        await pilot.pause()
        assert board_node.allow_expand is False


@pytest.mark.asyncio
async def test_selecting_node_copies_key_and_exits():
    copied = []

    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards, copy_fn=lambda k: copied.append(k))
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        board_node = tree.root.children[0]
        tree.select_node(board_node)
        await pilot.pause()
    assert copied == ["KAN"]
    assert app.return_value == "KAN"


@pytest.mark.asyncio
async def test_expand_failure_shows_status_and_allows_retry():
    from textual.widgets import Static

    attempts = []

    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    def flaky_board_issues(creds, key):
        attempts.append(key)
        if len(attempts) == 1:
            raise bt.requests.RequestException("network down")
        return [{"key": "KAN-1", "name": "First"}]

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards, board_issues_fn=flaky_board_issues)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        board_node = tree.root.children[0]
        board_node.expand()
        await pilot.pause()
        status = app.query_one("#status", Static)
        assert "network down" in status.content
        assert board_node.data["loaded"] is False
        assert len(board_node.children) == 0

        board_node.expand()
        await pilot.pause()
        assert attempts == ["KAN", "KAN"]
        assert len(board_node.children) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --with pytest,pytest-asyncio,textual,requests pytest scripts/tests/test_browse_tree_app.py -v`
Expected: `AttributeError: module 'browse_tree' has no attribute 'BrowseApp'`

- [ ] **Step 3: Append the implementation**

Append to `scripts/browse_tree.py` (after the functions from Task 3):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --with pytest,pytest-asyncio,textual,requests pytest scripts/tests/test_browse_tree_app.py -v`
Expected: `6 passed`

- [ ] **Step 5: Run the full test suite**

Run: `uv run --with pytest,pytest-asyncio,textual,requests,requests-mock pytest scripts/tests/ -v`
Expected: `21 passed` (6 from Task 1 + 9 from Task 3 + 6 from Task 4)

- [ ] **Step 6: Commit**

```bash
git add scripts/browse_tree.py scripts/tests/test_browse_tree_app.py
git commit -m "Add textual tree UI and entry point for standalone browser"
```

---

### Task 5: Issue-key detection in the skill

**Files:**
- Modify: `skills/jira-to-backlog/SKILL.md:22-37` (step 1)

**Interfaces:**
- Consumes: nothing new (this is a prompt-text change, not code).
- Produces: nothing consumed elsewhere in this plan — this is the
  skill-side change that lets a pasted issue key from the browser resolve
  correctly.

- [ ] **Step 1: Add issue-key detection to step 1**

In `skills/jira-to-backlog/SKILL.md`, replace step 1's current text:

```markdown
## 1. Resolve the board

If `$ARGUMENTS` (or the user's message) names a board/project, try to
resolve it directly — exact key or name match first. If nothing was given,
or nothing matches:

- Use the available Jira tools to list the boards/projects the
  authenticated user can see (for example, a JQL project search, or a
  dedicated "list boards" tool if the connected MCP server exposes one —
  check what's actually available rather than assuming a specific tool
  name).
- Print them as a numbered list in the terminal (key — name).
- Ask the user to pick one by number, or type the key/name directly.

If a name was given but matches more than one board, show the candidates
and ask which one instead of guessing.
```

with:

```markdown
## 1. Resolve the board or issue

If `$ARGUMENTS` (or the user's message) matches an issue-key pattern —
a project prefix followed by a dash and a number, e.g. `KAN-248` — treat
it as a single issue, not a board: fetch it directly with `jira_get_issue`
and use it as the crawl root for step 3 onward, **skipping step 2's
board-wide fetch entirely**. The written document/backlog filenames use
this issue key instead of a board key (e.g. `jira-docs/KAN-248.md`,
`jira-docs/KAN-248-backlog.md`).

Otherwise, if `$ARGUMENTS` (or the user's message) names a board/project,
try to resolve it directly — exact key or name match first. If nothing
was given, or nothing matches:

- Use the available Jira tools to list the boards/projects the
  authenticated user can see (for example, a JQL project search, or a
  dedicated "list boards" tool if the connected MCP server exposes one —
  check what's actually available rather than assuming a specific tool
  name).
- Print them as a numbered list in the terminal (key — name).
- Ask the user to pick one by number, or type the key/name directly.

If a name was given but matches more than one board, show the candidates
and ask which one instead of guessing.
```

- [ ] **Step 2: Update the filename references in later steps to stay generic**

In the same file, step 4's heading currently reads:

```markdown
Save one Markdown file to `jira-docs/<BOARD-KEY>.md` in the user's current
```

Replace `<BOARD-KEY>` there and in step 5's `jira-docs/<BOARD-KEY>-backlog.md`
reference with `<ROOT-KEY>` in both places (two edits total: one in step 4,
one in step 5's heading), so the wording correctly covers both the
existing board-key case and the new single-issue case introduced in Step 1
above — the actual value substituted is still whichever key (board or
issue) step 1 resolved.

- [ ] **Step 3: Validate the plugin**

Run: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 4: Commit**

```bash
git add skills/jira-to-backlog/SKILL.md
git commit -m "Add issue-key detection so the skill can crawl a single issue"
```

---

### Task 6: End-to-end manual verification and version bump

**Files:**
- Modify: `.claude-plugin/plugin.json` (version bump)
- Modify: `.claude-plugin/marketplace.json` (version bump)

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: nothing further downstream — this is the plan's final task.

- [ ] **Step 1: Bump the plugin version again**

In `.claude-plugin/plugin.json`, change `"version"` from `"0.1.2"` to
`"0.1.3"`. In `.claude-plugin/marketplace.json`, make the matching change
in `plugins[0].version`.

- [ ] **Step 2: Validate, commit, and push**

```bash
claude plugin validate .
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "Bump plugin version to 0.1.3 for standalone tree browser release"
git push origin master
```

Expected: `claude plugin validate .` prints `✔ Validation passed` before
committing.

- [ ] **Step 3: Update the installed plugin and start a fresh session (requires a human)**

```
/plugin update jira-claude-plugin
```

then exit and start a brand-new Claude Code session in this repo.

- [ ] **Step 4: Run the standalone browser for real (requires a human)**

In a plain terminal (the exact command was printed at the new session's
start per Task 2), run it. Confirm:
- The tree renders with real Jira boards as top-level nodes.
- Pressing the right arrow on a board loads its issues (a brief pause,
  then children appear) — confirms lazy loading, not an upfront full
  fetch.
- Pressing Enter on an issue exits the program and a message confirms the
  key was copied to the clipboard.
- Pasting into any text field confirms the clipboard actually contains
  that issue key.

- [ ] **Step 5: Confirm the skill handles a pasted issue key (requires a human)**

Back in the Claude Code session, send:

```
/jira-claude-plugin:jira-to-backlog <the issue key copied in Step 4>
```

Confirm the skill skips straight to crawling that single issue (no board
listing/prompt), and that `jira-docs/<ISSUE-KEY>.md` and
`jira-docs/<ISSUE-KEY>-backlog.md` are written correctly — reusing this
plugin's existing manual `KAN-248` test as the reference for what
"correct" looks like.

- [ ] **Step 6: Record the result**

Append one line to
`docs/superpowers/specs/2026-07-17-standalone-tree-browser-design.md`
under a new "Implementation verification" heading (after "Testing"),
stating what was observed in Steps 4-5 above. Commit:

```bash
git add docs/superpowers/specs/2026-07-17-standalone-tree-browser-design.md
git commit -m "Record standalone tree browser end-to-end verification"
git push origin master
```
