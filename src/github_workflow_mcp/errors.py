from __future__ import annotations


class ConfigurationError(RuntimeError):
    """Raised when local, non-secret configuration is unusable."""


class InputValidationError(ValueError):
    """Raised when a tool argument fails the public input contract."""


_SAFE_CLIENT_MESSAGES = {
    "AUTHENTICATION_FAILED": "GitHub authentication failed. Check the local credential and its repository access.",
    "NOT_FOUND": "The requested GitHub resource was not found or is not accessible.",
    "RATE_LIMITED": "GitHub rate limiting prevented this request. Try again later.",
    "UPSTREAM_ERROR": "GitHub could not complete the request. Try again later.",
    "UNSUPPORTED_CONTENT": "The requested repository content is not supported as UTF-8 text.",
}


class GitHubClientError(RuntimeError):
    """A GitHub failure containing only safe, normalized details."""

    def __init__(self, code: str, status: int | None = None) -> None:
        self.code = code
        self.status = status
        super().__init__(_SAFE_CLIENT_MESSAGES.get(code, _SAFE_CLIENT_MESSAGES["UPSTREAM_ERROR"]))
