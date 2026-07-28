import json

import mcp_recovery as mr

OTHERS = {
    "claude.ai Figma": {"timestamp": 1, "id": "a"},
    "claude.ai Notion": {"timestamp": 2, "id": "b"},
}


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_removes_only_our_entry(tmp_path):
    path = write(tmp_path / "c.json", {**OTHERS, mr.SERVER_KEY: {"timestamp": 3}})
    assert mr.clear_needs_auth(path) is True
    assert json.loads(path.read_text(encoding="utf-8")) == OTHERS


def test_reports_nothing_removed_when_we_are_not_flagged(tmp_path):
    path = write(tmp_path / "c.json", OTHERS)
    assert mr.clear_needs_auth(path) is False
    assert json.loads(path.read_text(encoding="utf-8")) == OTHERS


def test_missing_file_is_not_an_error(tmp_path):
    assert mr.clear_needs_auth(tmp_path / "nope.json") is False


def test_unparseable_file_is_left_alone(tmp_path):
    # Claude Code owns this file; if it isn't what we expect, don't touch it.
    path = tmp_path / "c.json"
    path.write_text("not json at all", encoding="utf-8")
    assert mr.clear_needs_auth(path) is False
    assert path.read_text(encoding="utf-8") == "not json at all"


def test_unexpected_shape_is_left_alone(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('["a list, not an object"]', encoding="utf-8")
    assert mr.clear_needs_auth(path) is False
    assert path.read_text(encoding="utf-8") == '["a list, not an object"]'


def test_leaves_the_original_intact_when_the_rewrite_fails(tmp_path, monkeypatch):
    original = {**OTHERS, mr.SERVER_KEY: {"timestamp": 3}}
    path = write(tmp_path / "c.json", original)
    monkeypatch.setattr(
        mr.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("locked"))
    )
    assert mr.clear_needs_auth(path) is False
    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert list(tmp_path.iterdir()) == [path], "left a temp file behind"


def test_cache_path_is_the_one_claude_code_uses(tmp_path, monkeypatch):
    monkeypatch.setattr(mr.Path, "home", classmethod(lambda cls: tmp_path))
    assert mr.needs_auth_cache_path() == tmp_path / ".claude" / "mcp-needs-auth-cache.json"


def test_server_key_matches_the_plugin_and_server_name():
    # Claude Code keys these as plugin:<plugin name>:<server name in .mcp.json>.
    import json as _json
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    plugin = _json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    servers = _json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    expected = f"plugin:{plugin['name']}:{next(iter(servers))}"
    assert mr.SERVER_KEY == expected
