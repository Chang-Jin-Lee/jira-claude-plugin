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
async def test_right_arrow_expands_cursor_node():
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
        await pilot.press("down")
        await pilot.press("right")
        await pilot.pause()
        board_node = tree.root.children[0]
        assert board_node.is_expanded
        assert calls == ["KAN"]


@pytest.mark.asyncio
async def test_left_arrow_collapses_cursor_node():
    def fake_boards(creds):
        return [{"key": "KAN", "name": "KAN board"}]

    def fake_board_issues(creds, key):
        return [{"key": "KAN-1", "name": "First"}]

    app = bt.BrowseApp(CREDS, boards_fn=fake_boards, board_issues_fn=fake_board_issues)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(Tree)
        await pilot.press("down")
        await pilot.press("right")
        await pilot.pause()
        board_node = tree.root.children[0]
        assert board_node.is_expanded
        await pilot.press("left")
        await pilot.pause()
        assert board_node.is_expanded is False


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
