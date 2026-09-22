from __future__ import annotations

import base64

import httpx
import pytest

from github_workflow_mcp.config import Settings
from github_workflow_mcp.errors import GitHubClientError
from github_workflow_mcp.github_client import GitHubClient


def test_read_file_decodes_utf8_and_reports_truncation():
    observed: dict[str, object] = {}
    payload = base64.b64encode("abcdef".encode("utf-8")).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        observed["request"] = request
        return httpx.Response(
            200,
            json={"type": "file", "content": payload},
            request=request,
        )

    client = GitHubClient(
        Settings("github_pat_test", "https://api.github.com"),
        transport=httpx.MockTransport(handler),
    )

    result = client.read_file("owner", "repo", "README.md", "main", max_chars=4)

    assert result == {
        "content": "abcd",
        "truncated": True,
        "source_url": "https://github.com/owner/repo/blob/main/README.md",
    }
    request = observed["request"]
    assert isinstance(request, httpx.Request)
    assert request.url.path == "/repos/owner/repo/contents/README.md"
    assert request.url.params["ref"] == "main"
    assert request.headers["Authorization"] == "Bearer github_pat_test"
    assert request.headers["Accept"] == "application/vnd.github+json"


def test_read_file_accepts_github_base64_with_line_breaks():
    text = "GitHub inserts line breaks into Base64 content. " * 4
    payload = base64.encodebytes(text.encode("utf-8")).decode("ascii")

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "type": "file",
                "encoding": "base64",
                "content": payload,
                "name": "README.md",
                "path": "README.md",
                "sha": "abc123",
                "size": len(text.encode("utf-8")),
                "url": "https://api.github.com/repos/owner/repo/contents/README.md",
                "html_url": "https://github.com/owner/repo/blob/main/README.md",
                "git_url": "https://api.github.com/repos/owner/repo/git/blobs/abc123",
                "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
                "_links": {
                    "self": "https://api.github.com/repos/owner/repo/contents/README.md",
                    "git": "https://api.github.com/repos/owner/repo/git/blobs/abc123",
                    "html": "https://github.com/owner/repo/blob/main/README.md",
                },
            },
            request=request,
        )
    )
    client = GitHubClient(Settings("github_pat_test"), transport=transport)

    result = client.read_file(
        "owner", "repo", "README.md", "main", max_chars=1000
    )

    assert result["content"] == text
    assert result["truncated"] is False


def test_read_file_url_encodes_ref_and_path_for_browser_source_url():
    payload = base64.b64encode(b"content").decode("ascii")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"type": "file", "content": payload},
            request=request,
        )
    )
    client = GitHubClient(Settings("github_pat_test"), transport=transport)

    result = client.read_file(
        "owner",
        "repo",
        "docs/quick start.md",
        "feature/mcp",
        max_chars=100,
    )

    assert result["source_url"] == (
        "https://github.com/owner/repo/blob/feature%2Fmcp/docs/quick%20start.md"
    )


def test_list_issues_removes_pull_requests_and_normalizes_labels():
    observed: dict[str, object] = {}
    response = [
        {
            "number": 1,
            "title": "Issue",
            "state": "open",
            "user": {"login": "alice"},
            "labels": [{"name": "bug"}, "help wanted"],
            "created_at": "2026-09-01T00:00:00Z",
            "html_url": "https://github.com/o/r/issues/1",
        },
        {
            "number": 2,
            "title": "PR",
            "state": "open",
            "user": {"login": "bob"},
            "labels": [],
            "created_at": "2026-09-02T00:00:00Z",
            "html_url": "https://github.com/o/r/pull/2",
            "pull_request": {},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        observed["request"] = request
        return httpx.Response(200, json=response, request=request)

    client = GitHubClient(
        Settings("github_pat_test"),
        transport=httpx.MockTransport(handler),
    )

    issues = client.list_issues("owner", "repo", "open", limit=10)

    assert issues == [
        {
            "number": 1,
            "title": "Issue",
            "state": "open",
            "author": "alice",
            "labels": ["bug", "help wanted"],
            "created_at": "2026-09-01T00:00:00Z",
            "url": "https://github.com/o/r/issues/1",
        }
    ]
    request = observed["request"]
    assert isinstance(request, httpx.Request)
    assert request.url.path == "/repos/owner/repo/issues"
    assert dict(request.url.params) == {
        "state": "open",
        "per_page": "10",
        "sort": "created",
        "direction": "desc",
    }


@pytest.mark.parametrize(
    ("status", "headers", "expected_code"),
    [
        (401, {}, "AUTHENTICATION_FAILED"),
        (403, {}, "AUTHENTICATION_FAILED"),
        (403, {"X-RateLimit-Remaining": "0"}, "RATE_LIMITED"),
        (404, {}, "NOT_FOUND"),
        (429, {}, "RATE_LIMITED"),
        (500, {}, "UPSTREAM_ERROR"),
    ],
)
def test_http_failures_are_mapped_without_disclosing_upstream_details(
    status: int,
    headers: dict[str, str],
    expected_code: str,
):
    secret = "github_pat_never_leak"
    unsafe_body = f"{secret} /Users/private Traceback: internal failure"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers=headers,
            text=unsafe_body,
            request=request,
        )

    client = GitHubClient(
        Settings(secret),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GitHubClientError) as exc_info:
        client.list_issues("owner", "repo", "open", limit=10)

    assert exc_info.value.code == expected_code
    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert secret not in rendered
    assert "/Users/private" not in rendered
    assert "Traceback" not in rendered


def test_timeout_is_mapped_to_safe_upstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret timeout detail", request=request)

    client = GitHubClient(
        Settings("github_pat_test"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GitHubClientError) as exc_info:
        client.list_issues("owner", "repo", "open", limit=10)

    assert exc_info.value.code == "UPSTREAM_ERROR"
    assert "secret timeout detail" not in str(exc_info.value)


def test_malformed_json_is_mapped_to_safe_upstream_error():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not-json", request=request)
    )
    client = GitHubClient(Settings("github_pat_test"), transport=transport)

    with pytest.raises(GitHubClientError) as exc_info:
        client.list_issues("owner", "repo", "open", limit=10)

    assert exc_info.value.code == "UPSTREAM_ERROR"
    assert "not-json" not in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "dir", "content": ""},
        {"type": "file", "content": "not valid base64!"},
        {
            "type": "file",
            "content": base64.b64encode(b"\xff\xfe").decode("ascii"),
        },
    ],
)
def test_unsupported_repository_content_is_reported_safely(payload: dict[str, str]):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload, request=request)
    )
    client = GitHubClient(Settings("github_pat_test"), transport=transport)

    with pytest.raises(GitHubClientError) as exc_info:
        client.read_file("owner", "repo", "README.md", "main", max_chars=100)

    assert exc_info.value.code == "UNSUPPORTED_CONTENT"


def test_malformed_issues_payload_is_mapped_to_safe_upstream_error():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"message": "not a list"},
            request=request,
        )
    )
    client = GitHubClient(Settings("github_pat_test"), transport=transport)

    with pytest.raises(GitHubClientError) as exc_info:
        client.list_issues("owner", "repo", "open", limit=10)

    assert exc_info.value.code == "UPSTREAM_ERROR"
