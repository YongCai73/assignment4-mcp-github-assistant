from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .service import GitHubWorkflowService
from .validation import validate_focus, validate_repo_identifier


mcp = FastMCP(
    "GitHub Workflow Assistant",
    instructions=(
        "Read-only GitHub assistant. Use only the returned repository evidence, "
        "and do not infer unobserved repository state."
    ),
)
_service = GitHubWorkflowService()


# Registration pattern adapted from the official MCP Python SDK examples:
# https://github.com/modelcontextprotocol/python-sdk
@mcp.tool()
def read_repository_file(
    owner: str,
    repository: str,
    path: str,
    ref: str = "main",
    max_chars: int = 6000,
) -> dict[str, object]:
    """Read one UTF-8 text file from a GitHub repository without modifying it."""

    return _service.read_repository_file(owner, repository, path, ref, max_chars)


@mcp.tool()
def list_repository_issues(
    owner: str,
    repository: str,
    state: str = "open",
    limit: int = 10,
) -> dict[str, object]:
    """List a compact, read-only view of repository issues (excluding pull requests)."""

    return _service.list_repository_issues(owner, repository, state, limit)


def build_review_prompt(
    owner: object,
    repository: object,
    review_focus: object = "maintenance risks and documentation gaps",
) -> str:
    safe_owner = validate_repo_identifier(owner, "owner")
    safe_repository = validate_repo_identifier(repository, "repository")
    safe_focus = validate_focus(review_focus)
    identity = f"{safe_owner}/{safe_repository}"
    return f"""Review GitHub repository {identity} with this focus: {safe_focus}.

Follow this evidence-first sequence:
1. Call list_repository_issues for {identity} first.
2. Call read_repository_file for README.md on the relevant reference.
3. Separate direct observations from recommendations.
4. Cite issue numbers and the source_url returned by the file tool.
5. If a tool returns an error, state the limitation and stop making claims that depend on it.

Do not claim access to files, branches, issues, commits, or repository state that the two tools did not return. Do not recommend a write action as though it has already happened."""


@mcp.prompt()
def review_repository_activity(
    owner: str,
    repository: str,
    review_focus: str = "maintenance risks and documentation gaps",
) -> str:
    """Prepare an evidence-grounded repository activity review."""

    return build_review_prompt(owner, repository, review_focus)


def main() -> None:
    mcp.run(transport="stdio")
