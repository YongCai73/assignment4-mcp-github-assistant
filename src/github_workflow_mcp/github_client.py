from __future__ import annotations

import base64
import binascii
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .errors import GitHubClientError


class GitHubClient:
    """Small read-only adapter for the GitHub REST API."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._settings.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "assignment4-github-workflow-mcp/1.0",
        }

    def _get_json(self, url: str, params: dict[str, str]) -> Any:
        try:
            with httpx.Client(
                headers=self._headers(),
                timeout=10.0,
                transport=self._transport,
            ) as client:
                response = client.get(url, params=params)
        except httpx.RequestError:
            raise GitHubClientError("UPSTREAM_ERROR") from None

        if not response.is_success:
            status = response.status_code
            if status == 401:
                code = "AUTHENTICATION_FAILED"
            elif status == 403:
                code = (
                    "RATE_LIMITED"
                    if response.headers.get("X-RateLimit-Remaining") == "0"
                    else "AUTHENTICATION_FAILED"
                )
            elif status == 404:
                code = "NOT_FOUND"
            elif status == 429:
                code = "RATE_LIMITED"
            else:
                code = "UPSTREAM_ERROR"
            raise GitHubClientError(code, status=status)

        try:
            return response.json()
        except ValueError:
            raise GitHubClientError("UPSTREAM_ERROR") from None

    def read_file(
        self,
        owner: str,
        repository: str,
        path: str,
        ref: str,
        max_chars: int,
    ) -> dict[str, object]:
        # Endpoint contract: https://docs.github.com/en/rest/repos/contents#get-repository-content
        encoded_owner = quote(owner, safe="")
        encoded_repository = quote(repository, safe="")
        encoded_path = quote(path, safe="/")
        endpoint = (
            f"{self._settings.api_base_url}/repos/{encoded_owner}/"
            f"{encoded_repository}/contents/{encoded_path}"
        )
        payload = self._get_json(endpoint, {"ref": ref})
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "file"
            or not isinstance(payload.get("content"), str)
        ):
            raise GitHubClientError("UNSUPPORTED_CONTENT")
        try:
            encoded_content = payload["content"].replace("\n", "").replace("\r", "")
            raw_content = base64.b64decode(encoded_content, validate=True)
            text = raw_content.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise GitHubClientError("UNSUPPORTED_CONTENT") from None

        encoded_ref = quote(ref, safe="")
        source_url = (
            f"https://github.com/{encoded_owner}/{encoded_repository}/blob/"
            f"{encoded_ref}/{encoded_path}"
        )
        return {
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
            "source_url": source_url,
        }

    def list_issues(
        self,
        owner: str,
        repository: str,
        state: str,
        limit: int,
    ) -> list[dict[str, object]]:
        # Endpoint contract: https://docs.github.com/en/rest/issues/issues#list-repository-issues
        encoded_owner = quote(owner, safe="")
        encoded_repository = quote(repository, safe="")
        endpoint = (
            f"{self._settings.api_base_url}/repos/{encoded_owner}/"
            f"{encoded_repository}/issues"
        )
        payload = self._get_json(
            endpoint,
            {
                "state": state,
                "per_page": str(limit),
                "sort": "created",
                "direction": "desc",
            },
        )

        if not isinstance(payload, list):
            raise GitHubClientError("UPSTREAM_ERROR")

        try:
            issues: list[dict[str, object]] = []
            for item in payload:
                if not isinstance(item, dict):
                    raise TypeError("issue is not an object")
                if "pull_request" in item:
                    continue
                raw_labels = item.get("labels", [])
                if not isinstance(raw_labels, list):
                    raise TypeError("labels is not a list")
                labels = [
                    label.get("name", "") if isinstance(label, dict) else str(label)
                    for label in raw_labels
                ]
                user = item.get("user") or {}
                if not isinstance(user, dict):
                    raise TypeError("user is not an object")
                issues.append(
                    {
                        "number": item["number"],
                        "title": item["title"],
                        "state": item["state"],
                        "author": user.get("login", "unknown"),
                        "labels": labels,
                        "created_at": item["created_at"],
                        "url": item["html_url"],
                    }
                )
            return issues
        except (KeyError, TypeError, AttributeError):
            raise GitHubClientError("UPSTREAM_ERROR") from None
