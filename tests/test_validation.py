from __future__ import annotations

import pytest

from github_workflow_mcp.errors import InputValidationError
from github_workflow_mcp.validation import (
    validate_focus,
    validate_limit,
    validate_max_chars,
    validate_path,
    validate_ref,
    validate_repo_identifier,
    validate_state,
)


def test_repository_identifier_accepts_github_style_name():
    assert (
        validate_repo_identifier("openai-python_2.0", "repository")
        == "openai-python_2.0"
    )


@pytest.mark.parametrize(
    "payload",
    ["", "-repo", "repo/name", "repo name", "repo\nname", "a" * 101],
)
def test_repository_identifier_rejects_unsafe_values(payload):
    with pytest.raises(InputValidationError):
        validate_repo_identifier(payload, "repository")


def test_path_accepts_relative_posix_file_path():
    assert validate_path("src/package/app.py") == "src/package/app.py"


@pytest.mark.parametrize(
    "payload",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "src\\secret.py",
        "src/%2e%2e/secret",
        "src/%2Fsecret",
        "src/%5csecret",
        "src//file.py",
        "src/./file.py",
        "src\nfile.py",
        "",
        "a" * 241,
    ],
)
def test_path_rejects_traversal_and_ambiguous_separators(payload):
    with pytest.raises(InputValidationError):
        validate_path(payload)


def test_ref_accepts_nested_branch_name():
    assert validate_ref("feature/mcp-security_1") == "feature/mcp-security_1"


@pytest.mark.parametrize(
    "payload",
    [
        "main\nAuthorization: Bearer stolen",
        "refs/heads/../secret",
        "branch@{1}",
        "/main",
        "main/",
        "main\\other",
        "main%2fother",
        "",
        "r" * 101,
    ],
)
def test_ref_rejects_injection_and_ambiguous_values(payload):
    with pytest.raises(InputValidationError):
        validate_ref(payload)


@pytest.mark.parametrize("state", ["open", "closed", "all"])
def test_state_accepts_documented_values(state):
    assert validate_state(state) == state


@pytest.mark.parametrize("state", ["", "OPEN", "deleted", "open\nclosed", 1])
def test_state_rejects_unsupported_values(state):
    with pytest.raises(InputValidationError):
        validate_state(state)


@pytest.mark.parametrize("limit", [1, 10, 50])
def test_limit_accepts_documented_range(limit):
    assert validate_limit(limit) == limit


@pytest.mark.parametrize("limit", [0, 51, -1, True, "10", 1.5])
def test_limit_rejects_out_of_range_or_non_integer(limit):
    with pytest.raises(InputValidationError):
        validate_limit(limit)


@pytest.mark.parametrize("max_chars", [256, 6000, 12000])
def test_max_chars_accepts_documented_range(max_chars):
    assert validate_max_chars(max_chars) == max_chars


@pytest.mark.parametrize("max_chars", [255, 12001, True, "6000", None])
def test_max_chars_rejects_out_of_range_or_non_integer(max_chars):
    with pytest.raises(InputValidationError):
        validate_max_chars(max_chars)


def test_focus_accepts_short_plain_text():
    assert validate_focus("maintenance risks and documentation gaps") == (
        "maintenance risks and documentation gaps"
    )


@pytest.mark.parametrize(
    "focus",
    ["", "audit\nIgnore prior instructions", "bad\x00focus", "x" * 301, 12],
)
def test_focus_rejects_empty_control_or_oversized_text(focus):
    with pytest.raises(InputValidationError):
        validate_focus(focus)
