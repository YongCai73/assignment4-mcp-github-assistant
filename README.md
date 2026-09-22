# GitHub Workflow Assistant MCP Server

This project is a local, read-only Model Context Protocol (MCP) server for Assignment 4. Claude Desktop can use it to read one text file from a GitHub repository, list repository issues, and generate an evidence-grounded repository activity review. The server does not clone repositories, run shell commands, modify GitHub, or place credentials in the MCP configuration.

## Architecture overview

Claude Desktop launches `server.py` over stdio. The FastMCP boundary exposes exactly two tools and one prompt. Each tool delegates to a service boundary that validates inputs before it loads local configuration. A narrow `httpx` client then calls the GitHub REST API. All output returns through a fixed result envelope so upstream response bodies, headers, tokens, stack traces, and local paths are not disclosed.

```text
Claude Desktop
    -> FastMCP stdio server
    -> validation and service boundary
    -> project-local .env credential loader
    -> read-only GitHub REST client
    -> GitHub Contents and Issues endpoints
```

## Prerequisites

- Python 3.12
- Claude Desktop
- A fine-grained GitHub personal access token with read-only access to repository contents and issues
- A private GitHub repository for the assignment submission

## Local setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy the placeholder file and edit only the local `.env`:

```bash
cp .env.example .env
```

Use this format:

```dotenv
GITHUB_TOKEN=your_fine_grained_token_here
GITHUB_API_BASE_URL=https://api.github.com
```

The `.env` file is ignored by Git. Do not paste the token into `claude_desktop_config.json`, the README, screenshots, commits, or chat messages.

## Tests

Run all unit and MCP contract tests:

```bash
.venv/bin/python -m pytest -q
```

The tests use `httpx.MockTransport`; they do not require a real token or GitHub network access. They cover configuration, input validation, GitHub response normalization, error mapping, service envelopes, and an actual MCP stdio handshake.

## Run the local server

The server normally runs as a child process of Claude Desktop. For a basic startup check:

```bash
.venv/bin/python server.py
```

It will wait silently for MCP messages on standard input. Use `Control-C` to stop a manual run.

## Claude Desktop configuration

The checked-in `claude_desktop_config.json` contains the absolute Python and server paths for this computer. Merge its `github-workflow-assistant` entry into the existing Claude Desktop configuration, then fully quit and restart Claude Desktop. The token remains in the project-local `.env`; there is deliberately no `env` block in the Claude configuration.

If the repository is moved, update both absolute paths in the configuration. If Claude reports that the server disconnected, run the Python and test commands above from Terminal first.

## MCP tools

### `read_repository_file`

Reads one UTF-8 text file and returns bounded content plus a GitHub source URL.

Example arguments:

```json
{
  "owner": "octocat",
  "repository": "Hello-World",
  "path": "README.md",
  "ref": "main",
  "max_chars": 6000
}
```

### `list_repository_issues`

Returns a compact issue list and removes pull-request records returned by GitHub's shared issues endpoint.

Example arguments:

```json
{
  "owner": "octocat",
  "repository": "Hello-World",
  "state": "open",
  "limit": 10
}
```

## MCP prompt

### `review_repository_activity`

This prompt tells Claude to call `list_repository_issues` first and `read_repository_file` for `README.md` second. It requires observations and recommendations to be separated, asks for issue-number and source-URL citations, and says not to claim access to repository state the tools did not return.

Example arguments:

```json
{
  "owner": "octocat",
  "repository": "Hello-World",
  "review_focus": "maintenance risks and documentation gaps"
}
```

## Security best practices

### Input sanitization

Every user-controlled field is allowlisted and length-bounded before the server loads `.env` or creates an HTTP client. Repository paths reject absolute paths, traversal components, control characters, backslashes, empty components, and encoded separator/traversal variants. Git references reject control characters, encoded input, `..`, and `@{`. Numeric arguments reject booleans and enforce explicit ranges.

### Error disclosure

The GitHub adapter maps network and HTTP failures to stable codes. The service returns only fixed public messages. It never returns upstream bodies, request headers, exception representations, local paths, or tokens. Logs contain only an operation name, normalized code, optional HTTP status, and a random correlation ID.

## Offline exploit demonstration

Run both deterministic security checks:

```bash
.venv/bin/python scripts/demo_security_checks.py
```

The first check submits traversal and header-injection payloads and verifies that zero HTTP requests occur. The second supplies a mocked GitHub 500 response containing a fake token, a private path, and a stack trace, then verifies that none appear in public output or logs. A successful run ends with `OVERALL: PASS`.

## Demo checklist

1. Show that `.env` is ignored and the token is absent from the Claude configuration.
2. Run `.venv/bin/python -m pytest -q`.
3. Run `.venv/bin/python scripts/demo_security_checks.py`.
4. Restart Claude Desktop and confirm two tools plus one prompt are listed.
5. Invoke `review_repository_activity` against a repository the token can read.
6. Show one normal tool result and one controlled invalid-input result.

## Troubleshooting

- `CONFIGURATION_ERROR`: create `.env` in this repository and replace the placeholder token.
- `AUTHENTICATION_FAILED`: check token expiry and read access to the selected repository.
- `NOT_FOUND`: verify owner, repository, path, ref, and token access.
- `RATE_LIMITED`: wait for GitHub's rate-limit window to reset.
- Server disconnected: verify the absolute paths in `claude_desktop_config.json`, the virtual environment, and dependency installation.

## Limitations

- Only UTF-8 repository files are supported.
- File output is capped at 12,000 characters.
- Issue output is capped at 50 records and intentionally excludes issue bodies and pull requests.
- The server has no write tools and cannot create issues, edit files, merge code, or run commands.
- The design is local to this computer; its Claude Desktop paths must change if the repository moves.

## Code citations

- MCP server registration and stdio structure follow the [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- File retrieval uses GitHub's [Get repository content](https://docs.github.com/en/rest/repos/contents#get-repository-content) endpoint contract.
- Issue retrieval uses GitHub's [List repository issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues) endpoint contract.

## AI assistance disclosure

OpenAI Codex assisted with the initial architecture, implementation scaffolding, test cases, and documentation. I reviewed the design decisions, retained responsibility for the final configuration and demonstration, and will verify the live Claude Desktop and GitHub behavior on my own account before submission.
