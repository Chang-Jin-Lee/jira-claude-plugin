import json
from types import SimpleNamespace

import run_mcp as rm

CREDS = {"jira_url": "https://x.atlassian.net", "jira_email": "a@b.com", "jira_api_token": "t"}


def test_build_env_injects_credentials_and_read_only():
    env = rm.build_env(CREDS, {"PATH": "/usr/bin"})
    assert env["JIRA_URL"] == "https://x.atlassian.net"
    assert env["JIRA_USERNAME"] == "a@b.com"
    assert env["JIRA_API_TOKEN"] == "t"
    assert env["READ_ONLY_MODE"] == "true"
    assert env["PATH"] == "/usr/bin"


def test_wait_for_credentials_returns_creds_when_present(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    assert rm.wait_for_credentials(path, attempts=1, delay=0) == CREDS


def test_wait_for_credentials_retries_then_gives_up(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(rm.time, "sleep", lambda s: sleeps.append(s))
    assert rm.wait_for_credentials(tmp_path / "nope.json", attempts=3, delay=2) is None
    assert sleeps == [2, 2]


def test_wait_for_credentials_picks_up_file_appearing_between_attempts(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"

    def write_then_noop(_):
        path.write_text(json.dumps(CREDS), encoding="utf-8")

    monkeypatch.setattr(rm.time, "sleep", write_then_noop)
    assert rm.wait_for_credentials(path, attempts=2, delay=1) == CREDS


def test_main_runs_server_with_injected_env(monkeypatch, tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(CREDS), encoding="utf-8")
    monkeypatch.setattr(rm, "credentials_path", lambda: path)
    calls = []

    def fake_run(cmd, env):
        calls.append((cmd, env))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(rm.subprocess, "run", fake_run)
    assert rm.main() == 7
    cmd, env = calls[0]
    assert cmd == ["uvx", "mcp-atlassian"]
    assert env["JIRA_URL"] == "https://x.atlassian.net"
    assert env["JIRA_API_TOKEN"] == "t"


def test_main_returns_1_when_credentials_never_appear(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rm, "credentials_path", lambda: tmp_path / "nope.json")
    monkeypatch.setattr(rm.time, "sleep", lambda s: None)
    calls = []
    monkeypatch.setattr(rm.subprocess, "run", lambda *a, **k: calls.append(a))
    assert rm.main() == 1
    assert calls == []
    assert "credentials" in capsys.readouterr().err
