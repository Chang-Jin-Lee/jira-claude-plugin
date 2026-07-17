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
