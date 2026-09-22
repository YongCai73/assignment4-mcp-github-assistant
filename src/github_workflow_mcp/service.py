from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from typing import Protocol

from .config import Settings, load_settings
from .errors import ConfigurationError, GitHubClientError, InputValidationError
from .github_client import GitHubClient
from .validation import (
    validate_limit,
    validate_max_chars,
    validate_path,
    validate_ref,
    validate_repo_identifier,
    validate_state,
)


_LOGGER = logging.getLogger(__name__)
_PUBLIC_ERROR_MESSAGES = {
    "AUTHENTICATION_FAILED": (
        "GitHub authentication failed. Check the local credential and its repository access."
    ),
    "NOT_FOUND": "The requested GitHub resource was not found or is not accessible.",
    "RATE_LIMITED": "GitHub rate limiting prevented this request. Try again later.",
    "UPSTREAM_ERROR": "GitHub could not complete the request. Try again later.",
    "UNSUPPORTED_CONTENT": (
        "The requested repository content is not supported as UTF-8 text."
    ),
}


class _Client(Protocol):
    def read_file(
        self,
        owner: str,
        repository: str,
        path: str,
        ref: str,
        max_chars: int,
    ) -> dict[str, object]: ...

    def list_issues(
        self,
        owner: str,
        repository: str,
        state: str,
        limit: int,
    ) -> list[dict[str, object]]: ...


class GitHubWorkflowService:
    """Validation and disclosure boundary for the MCP-facing operations."""

    def __init__(
        self,
        settings_loader: Callable[[], Settings] = load_settings,
        client_factory: Callable[[Settings], _Client] = GitHubClient,
    ) -> None:
        self._settings_loader = settings_loader
        self._client_factory = client_factory

    @staticmethod
    def _invalid_input(exc: InputValidationError) -> dict[str, object]:
        return {
            "ok": False,
            "error": {"code": "INVALID_INPUT", "message": str(exc)},
        }

    @staticmethod
    def _configuration_error() -> dict[str, object]:
        return {
            "ok": False,
            "error": {
                "code": "CONFIGURATION_ERROR",
                "message": "GitHub authentication is not configured on this computer.",
            },
        }

    @staticmethod
    def _upstream_error(
        operation: str,
        code: str = "UPSTREAM_ERROR",
        status: int | None = None,
    ) -> dict[str, object]:
        safe_code = code if code in _PUBLIC_ERROR_MESSAGES else "UPSTREAM_ERROR"
        correlation_id = secrets.token_hex(6)
        _LOGGER.warning(
            "operation=%s code=%s status=%s correlation_id=%s",
            operation,
            safe_code,
            status,
            correlation_id,
        )
        return {
            "ok": False,
            "error": {
                "code": safe_code,
                "message": _PUBLIC_ERROR_MESSAGES[safe_code],
                "correlation_id": correlation_id,
            },
        }

    def read_repository_file(
        self,
        owner: object,
        repository: object,
        path: object,
        ref: object = "main",
        max_chars: object = 6000,
    ) -> dict[str, object]:
        try:
            safe_owner = validate_repo_identifier(owner, "owner")
            safe_repository = validate_repo_identifier(repository, "repository")
            safe_path = validate_path(path)
            safe_ref = validate_ref(ref)
            safe_max_chars = validate_max_chars(max_chars)
        except InputValidationError as exc:
            return self._invalid_input(exc)

        try:
            settings = self._settings_loader()
        except ConfigurationError:
            return self._configuration_error()

        try:
            result = self._client_factory(settings).read_file(
                safe_owner,
                safe_repository,
                safe_path,
                safe_ref,
                safe_max_chars,
            )
        except GitHubClientError as exc:
            return self._upstream_error(
                "read_repository_file",
                code=exc.code,
                status=exc.status,
            )
        except Exception:
            return self._upstream_error("read_repository_file")

        return {
            "ok": True,
            "repository": f"{safe_owner}/{safe_repository}",
            "path": safe_path,
            "ref": safe_ref,
            **result,
        }

    def list_repository_issues(
        self,
        owner: object,
        repository: object,
        state: object = "open",
        limit: object = 10,
    ) -> dict[str, object]:
        try:
            safe_owner = validate_repo_identifier(owner, "owner")
            safe_repository = validate_repo_identifier(repository, "repository")
            safe_state = validate_state(state)
            safe_limit = validate_limit(limit)
        except InputValidationError as exc:
            return self._invalid_input(exc)

        try:
            settings = self._settings_loader()
        except ConfigurationError:
            return self._configuration_error()

        try:
            issues = self._client_factory(settings).list_issues(
                safe_owner,
                safe_repository,
                safe_state,
                safe_limit,
            )
        except GitHubClientError as exc:
            return self._upstream_error(
                "list_repository_issues",
                code=exc.code,
                status=exc.status,
            )
        except Exception:
            return self._upstream_error("list_repository_issues")

        return {
            "ok": True,
            "repository": f"{safe_owner}/{safe_repository}",
            "state": safe_state,
            "count": len(issues),
            "issues": issues,
        }
