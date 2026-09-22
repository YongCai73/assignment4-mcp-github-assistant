from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

from .errors import ConfigurationError


_TOKEN_ERROR = (
    "GitHub authentication is not configured. "
    "Add GITHUB_TOKEN to the project .env file."
)
_PLACEHOLDER_TOKENS = {
    "github_pat_replace_with_your_token",
    "replace_me",
    "changeme",
}


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    api_base_url: str = "https://api.github.com"


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def load_settings(env_path: Path | None = None) -> Settings:
    """Load GitHub settings from a project-local dotenv file."""

    path = env_path if env_path is not None else _default_env_path()
    values = dotenv_values(path)

    raw_token = values.get("GITHUB_TOKEN")
    token = raw_token.strip() if isinstance(raw_token, str) else ""
    if not token or token.lower() in _PLACEHOLDER_TOKENS:
        raise ConfigurationError(_TOKEN_ERROR)

    raw_base_url = values.get("GITHUB_API_BASE_URL") or "https://api.github.com"
    base_url = str(raw_base_url).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ConfigurationError("GitHub API base URL must be a valid HTTPS URL.")

    return Settings(token=token, api_base_url=base_url)
