from __future__ import annotations

import pytest

from github_workflow_mcp.config import Settings, load_settings
from github_workflow_mcp.errors import ConfigurationError


def test_load_settings_reads_project_local_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "GITHUB_TOKEN=github_pat_test_only\n"
        "GITHUB_API_BASE_URL=https://api.github.com\n",
        encoding="utf-8",
    )

    settings = load_settings(env)

    assert settings == Settings(
        token="github_pat_test_only",
        api_base_url="https://api.github.com",
    )


@pytest.mark.parametrize(
    "token",
    ["", "github_pat_replace_with_your_token", "replace_me", "changeme"],
)
def test_load_settings_rejects_missing_or_placeholder_token(tmp_path, token):
    env = tmp_path / ".env"
    env.write_text(f"GITHUB_TOKEN={token}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env)

    if token:
        assert token not in str(exc.value)
    assert "GITHUB_TOKEN" in str(exc.value)


def test_load_settings_rejects_missing_dotenv_without_exposing_path(tmp_path):
    missing = tmp_path / "private" / ".env"

    with pytest.raises(ConfigurationError) as exc:
        load_settings(missing)

    assert str(missing) not in str(exc.value)


def test_load_settings_rejects_non_https_api_url(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "GITHUB_TOKEN=github_pat_test_only\n"
        "GITHUB_API_BASE_URL=http://api.github.test\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env)

    assert "https" in str(exc.value).lower()


def test_load_settings_allows_injected_https_api_url_for_testing(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "GITHUB_TOKEN=github_pat_test_only\n"
        "GITHUB_API_BASE_URL=https://api.github.test/\n",
        encoding="utf-8",
    )

    settings = load_settings(env)

    assert settings.api_base_url == "https://api.github.test"
