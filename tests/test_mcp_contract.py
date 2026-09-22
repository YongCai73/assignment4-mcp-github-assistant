from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from github_workflow_mcp import mcp_server


def test_review_prompt_names_both_tools_and_prohibits_unsupported_claims():
    prompt = mcp_server.build_review_prompt(
        "owner",
        "repo",
        "documentation gaps",
    )

    assert "list_repository_issues" in prompt
    assert "read_repository_file" in prompt
    assert "Do not claim" in prompt
    assert "owner/repo" in prompt
    assert "documentation gaps" in prompt


def test_tool_functions_delegate_to_service(monkeypatch):
    calls: list[tuple[str, tuple[object, ...]]] = []

    class FakeService:
        def read_repository_file(self, *args: object) -> dict[str, object]:
            calls.append(("read", args))
            return {"ok": True, "kind": "file"}

        def list_repository_issues(self, *args: object) -> dict[str, object]:
            calls.append(("issues", args))
            return {"ok": True, "kind": "issues"}

    monkeypatch.setattr(mcp_server, "_service", FakeService())

    assert mcp_server.read_repository_file("o", "r", "README.md", "main", 6000) == {
        "ok": True,
        "kind": "file",
    }
    assert mcp_server.list_repository_issues("o", "r", "open", 10) == {
        "ok": True,
        "kind": "issues",
    }
    assert calls == [
        ("read", ("o", "r", "README.md", "main", 6000)),
        ("issues", ("o", "r", "open", 10)),
    ]


def test_stdio_server_lists_exact_public_contract():
    repo_root = Path(__file__).resolve().parents[1]

    async def inspect_server() -> tuple[set[str], set[str]]:
        parameters = StdioServerParameters(
            command=str(repo_root / ".venv" / "bin" / "python"),
            args=[str(repo_root / "server.py")],
            cwd=str(repo_root),
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                prompts = await session.list_prompts()
                return (
                    {tool.name for tool in tools.tools},
                    {prompt.name for prompt in prompts.prompts},
                )

    tool_names, prompt_names = asyncio.run(inspect_server())

    assert tool_names == {"read_repository_file", "list_repository_issues"}
    assert prompt_names == {"review_repository_activity"}
