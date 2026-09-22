from __future__ import annotations

import json
import logging

from github_workflow_mcp.config import Settings
from github_workflow_mcp.errors import ConfigurationError, GitHubClientError
from github_workflow_mcp.service import GitHubWorkflowService


class FakeClient:
    def read_file(
        self,
        owner: str,
        repository: str,
        path: str,
        ref: str,
        max_chars: int,
    ) -> dict[str, object]:
        return {
            "content": "hello",
            "truncated": False,
            "source_url": f"https://github.com/{owner}/{repository}/blob/{ref}/{path}",
        }

    def list_issues(
        self,
        owner: str,
        repository: str,
        state: str,
        limit: int,
    ) -> list[dict[str, object]]:
        return [
            {
                "number": 7,
                "title": "Document setup",
                "state": state,
                "author": "alice",
                "labels": ["docs"],
                "created_at": "2026-09-01T00:00:00Z",
                "url": f"https://github.com/{owner}/{repository}/issues/7",
            }
        ][:limit]


def test_invalid_input_returns_error_before_loading_settings_or_network():
    calls = {"settings": 0, "client": 0}

    def count_settings() -> Settings:
        calls["settings"] += 1
        return Settings("github_pat_test")

    def count_client(settings: Settings) -> FakeClient:
        calls["client"] += 1
        return FakeClient()

    service = GitHubWorkflowService(
        settings_loader=count_settings,
        client_factory=count_client,
    )

    result = service.read_repository_file(
        "owner",
        "repo",
        "../../etc/passwd",
        "main",
        6000,
    )

    assert result == {
        "ok": False,
        "error": {
            "code": "INVALID_INPUT",
            "message": "Repository path is not allowed.",
        },
    }
    assert calls == {"settings": 0, "client": 0}


def test_read_repository_file_returns_stable_success_envelope():
    service = GitHubWorkflowService(
        settings_loader=lambda: Settings("github_pat_test"),
        client_factory=lambda settings: FakeClient(),
    )

    result = service.read_repository_file(
        "owner",
        "repo",
        "README.md",
        "main",
        6000,
    )

    assert result == {
        "ok": True,
        "repository": "owner/repo",
        "path": "README.md",
        "ref": "main",
        "content": "hello",
        "truncated": False,
        "source_url": "https://github.com/owner/repo/blob/main/README.md",
    }


def test_list_repository_issues_returns_stable_success_envelope():
    service = GitHubWorkflowService(
        settings_loader=lambda: Settings("github_pat_test"),
        client_factory=lambda settings: FakeClient(),
    )

    result = service.list_repository_issues("owner", "repo", "open", 10)

    assert result == {
        "ok": True,
        "repository": "owner/repo",
        "state": "open",
        "count": 1,
        "issues": [
            {
                "number": 7,
                "title": "Document setup",
                "state": "open",
                "author": "alice",
                "labels": ["docs"],
                "created_at": "2026-09-01T00:00:00Z",
                "url": "https://github.com/owner/repo/issues/7",
            }
        ],
    }


def test_missing_token_becomes_configuration_error_without_server_crash():
    def raise_configuration_error() -> Settings:
        raise ConfigurationError(
            "GitHub authentication is not configured. Add GITHUB_TOKEN to /private/.env."
        )

    service = GitHubWorkflowService(settings_loader=raise_configuration_error)

    result = service.list_repository_issues("owner", "repo", "open", 10)

    assert result == {
        "ok": False,
        "error": {
            "code": "CONFIGURATION_ERROR",
            "message": "GitHub authentication is not configured on this computer.",
        },
    }
    assert "/private" not in json.dumps(result)


def test_upstream_secret_is_absent_from_result_and_logs(caplog):
    secret = "github_pat_never_leak"

    class FailingClient(FakeClient):
        def list_issues(
            self,
            owner: str,
            repository: str,
            state: str,
            limit: int,
        ) -> list[dict[str, object]]:
            _malicious_body = f"{secret} /Users/private Traceback"
            raise GitHubClientError("UPSTREAM_ERROR", status=500)

    service = GitHubWorkflowService(
        settings_loader=lambda: Settings(secret),
        client_factory=lambda settings: FailingClient(),
    )

    with caplog.at_level(logging.WARNING):
        result = service.list_repository_issues("owner", "repo", "open", 10)

    assert result["ok"] is False
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert len(result["error"]["correlation_id"]) == 12
    rendered = json.dumps(result) + caplog.text
    assert secret not in rendered
    assert "/Users/private" not in rendered
    assert "Traceback" not in rendered
    assert "operation=list_repository_issues" in caplog.text
    assert "status=500" in caplog.text


def test_unexpected_exception_is_mapped_without_details(caplog):
    class BrokenClient(FakeClient):
        def list_issues(
            self,
            owner: str,
            repository: str,
            state: str,
            limit: int,
        ) -> list[dict[str, object]]:
            raise RuntimeError("github_pat_never_leak /Users/private Traceback")

    service = GitHubWorkflowService(
        settings_loader=lambda: Settings("github_pat_test"),
        client_factory=lambda settings: BrokenClient(),
    )

    with caplog.at_level(logging.WARNING):
        result = service.list_repository_issues("owner", "repo", "open", 10)

    assert result["error"]["code"] == "UPSTREAM_ERROR"
    rendered = json.dumps(result) + caplog.text
    assert "github_pat_never_leak" not in rendered
    assert "/Users/private" not in rendered
    assert "Traceback" not in rendered
