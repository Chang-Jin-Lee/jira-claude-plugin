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
        "https://x.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "KAN-1", "fields": {"summary": "First"}}], "isLast": True},
    )
    assert bt.list_board_issues(CREDS, "KAN") == [{"key": "KAN-1", "name": "First"}]


def test_list_issue_children_returns_key_and_summary(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/api/3/search/jql",
        json={"issues": [{"key": "KAN-2", "fields": {"summary": "Child"}}], "isLast": True},
    )
    assert bt.list_issue_children(CREDS, "KAN-1") == [{"key": "KAN-2", "name": "Child"}]


def test_list_board_issues_paginates_across_multiple_pages(requests_mock):
    requests_mock.get(
        "https://x.atlassian.net/rest/api/3/search/jql",
        [
            {
                "json": {
                    "issues": [{"key": "KAN-1", "fields": {"summary": "First"}}],
                    "nextPageToken": "tok1",
                    "isLast": False,
                }
            },
            {
                "json": {
                    "issues": [{"key": "KAN-2", "fields": {"summary": "Second"}}],
                    "isLast": True,
                }
            },
        ],
    )
    issues = bt.list_board_issues(CREDS, "KAN")
    assert issues == [{"key": "KAN-1", "name": "First"}, {"key": "KAN-2", "name": "Second"}]
    assert requests_mock.request_history[1].qs["nextpagetoken"] == ["tok1"]


def test_copy_to_clipboard_invokes_clip(monkeypatch):
    calls = []

    def fake_run(cmd, input, check):
        calls.append((cmd, input, check))

    monkeypatch.setattr(bt.subprocess, "run", fake_run)
    bt.copy_to_clipboard("KAN-248")
    assert calls == [(["clip"], b"KAN-248", True)]
