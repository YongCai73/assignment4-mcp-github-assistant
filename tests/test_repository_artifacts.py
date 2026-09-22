from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_claude_config_uses_venv_python_and_contains_no_secret():
    config = json.loads((ROOT / "claude_desktop_config.json").read_text())
    server = config["mcpServers"]["github-workflow-assistant"]

    assert server["command"] == str(ROOT / ".venv" / "bin" / "python")
    assert server["args"] == [str(ROOT / "server.py")]
    assert "GITHUB_TOKEN" not in json.dumps(config)
    assert "github_pat_" not in json.dumps(config)
    assert "env" not in server


def test_readme_contains_every_demo_and_setup_command():
    text = (ROOT / "README.md").read_text()

    for required in [
        "python3 -m venv",
        "pip install -r requirements.txt",
        "pytest -q",
        "demo_security_checks.py",
        "Claude Desktop",
        "Code citations",
        "read_repository_file",
        "list_repository_issues",
        "review_repository_activity",
        "Input sanitization",
        "Error disclosure",
    ]:
        assert required in text


def test_env_is_ignored_and_example_contains_only_placeholder():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    example = (ROOT / ".env.example").read_text()

    assert ".env" in ignored
    assert "github_pat_replace_with_your_token" in example
    assert not re.search(r"github_pat_[A-Za-z0-9_]{60,}", example)
    assert not re.search(r"ghp_[A-Za-z0-9]{30,}", example)
