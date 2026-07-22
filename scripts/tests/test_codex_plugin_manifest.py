import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"


def _load():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_has_required_top_level_fields():
    manifest = _load()
    assert manifest["name"] == "jira-claude-plugin"
    assert manifest["version"] == "0.1.8"
    assert manifest["description"]
    assert manifest["author"]["name"]
    assert manifest["skills"] == "./skills/"


def test_manifest_has_no_hooks_field():
    manifest = _load()
    assert "hooks" not in manifest


def test_manifest_declares_atlassian_mcp_server_with_env_substitution():
    manifest = _load()
    server = manifest["mcpServers"]["atlassian"]
    assert server["command"] == "uvx"
    assert server["args"] == ["mcp-atlassian"]
    assert server["env"] == {
        "JIRA_URL": "${JIRA_URL}",
        "JIRA_USERNAME": "${JIRA_USERNAME}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}",
        "READ_ONLY_MODE": "true",
    }


def test_manifest_has_required_interface_fields():
    manifest = _load()
    interface = manifest["interface"]
    for field in (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "defaultPrompt",
    ):
        assert field in interface
