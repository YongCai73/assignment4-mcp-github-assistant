# Assignment 4 GitHub Workflow MCP Server — Design Specification

## 1. Purpose

Build a local Python MCP server that Claude Desktop can launch over standard input/output. The server assists with a development workflow by reading a GitHub repository file and listing repository issues. It demonstrates authentication, tool and prompt design, input sanitization, safe error disclosure, automated exploit checks, and a reproducible local setup.

The project is an individual course submission. The user must be able to explain every component during a live demo.

## 2. Selected Domain and Deliverable Shape

- **Domain:** Development Workflow
- **MCP primitives:** two tools and one prompt
- **Transport:** local `stdio`
- **Language:** Python 3.12
- **AI client:** Claude Desktop
- **External service:** GitHub REST API
- **External writes:** none; both tools are read-only

The implementation satisfies the assignment's allowed combination of “two tools and a prompt.”

## 3. Scope

### Included

1. Read a text file from a GitHub repository at a specified ref.
2. List issues from a GitHub repository with state and result-count filters.
3. Supply a reusable prompt that tells Claude how to review repository activity using both tools.
4. Load a GitHub token from a project-local `.env` file using `pathlib.Path` and `python-dotenv`.
5. Validate every user-controlled input before any HTTP request.
6. Convert upstream failures into stable, non-sensitive public errors.
7. Provide automated unit tests and two runnable exploit demonstrations.
8. Provide a complete Claude Desktop configuration for this laptop.
9. Provide repository documentation and separate Canvas-only documentation.
10. Provide an editable architecture diagram plus a rendered image for Canvas.

### Excluded

- Creating, editing, closing, or commenting on GitHub issues.
- Writing repository files, creating commits, or opening pull requests.
- Executing shell commands or repository code.
- Cloning repositories to the local machine.
- Storing or transmitting GitHub credentials outside the GitHub API request header.
- Automatically submitting files to Canvas.

These exclusions keep the server easy to explain and reduce the risk of unintended side effects during the demo.

## 4. Architecture

```text
Claude Desktop
    |
    | MCP over stdio
    v
FastMCP server and tool boundary
    |
    +--> Prompt template
    |
    +--> Input validators
             |
             v
       GitHub service layer
             |
             v
       GitHub HTTP client ----> GitHub REST API
             ^
             |
       .env configuration loader

All failures return through a safe error mapper before reaching Claude.
```

The MCP layer contains no GitHub-specific request construction. The service layer depends on a small GitHub client interface, allowing tests to inject an in-memory HTTP transport. Validation and configuration are separate modules so the security behavior can be tested without starting Claude Desktop.

## 5. Repository Structure

```text
assignment4_mcp_github_assistant/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── claude_desktop_config.json
├── server.py
├── src/
│   └── github_workflow_mcp/
│       ├── __init__.py
│       ├── config.py
│       ├── errors.py
│       ├── validation.py
│       ├── github_client.py
│       ├── service.py
│       └── mcp_server.py
├── tests/
│   ├── test_config.py
│   ├── test_validation.py
│   ├── test_github_client.py
│   ├── test_service.py
│   └── test_mcp_contract.py
├── scripts/
│   └── demo_security_checks.py
└── docs/
    └── superpowers/
        ├── specs/
        └── plans/
```

Canvas-only artifacts are created in a sibling directory, `assignment4_canvas_submission/`, so they cannot be accidentally committed to the GitHub repository.

## 6. MCP Tool Interfaces

### 6.1 `read_repository_file`

```python
read_repository_file(
    owner: str,
    repository: str,
    path: str,
    ref: str = "main",
    max_chars: int = 6000,
) -> dict
```

Behavior:

1. Validate `owner`, `repository`, `path`, `ref`, and `max_chars`.
2. Request `GET /repos/{owner}/{repository}/contents/{path}?ref={ref}`.
3. Require a GitHub `file` response with Base64-encoded text content.
4. Decode UTF-8 text; reject undecodable or non-file results with a safe error.
5. Return at most `max_chars` characters and report whether truncation occurred.

Success result:

```json
{
  "ok": true,
  "repository": "owner/repository",
  "path": "README.md",
  "ref": "main",
  "content": "...",
  "truncated": false,
  "source_url": "https://github.com/owner/repository/blob/main/README.md"
}
```

### 6.2 `list_repository_issues`

```python
list_repository_issues(
    owner: str,
    repository: str,
    state: str = "open",
    limit: int = 10,
) -> dict
```

Behavior:

1. Validate repository identifiers, `state`, and `limit`.
2. Request `GET /repos/{owner}/{repository}/issues` with `state`, `per_page`, and deterministic sorting parameters.
3. Remove pull-request records because GitHub returns them from the issues endpoint.
4. Return a compact list containing issue number, title, state, author, labels, creation time, and URL.

The tool never returns issue bodies, raw headers, or authentication information.

### 6.3 Prompt: `review_repository_activity`

```python
review_repository_activity(
    owner: str,
    repository: str,
    review_focus: str = "maintenance risks and documentation gaps",
) -> str
```

The prompt instructs Claude to:

1. Call `list_repository_issues` first.
2. Call `read_repository_file` for `README.md`.
3. Distinguish observations from recommendations.
4. Cite issue numbers and the returned source URL.
5. Avoid claiming access to files or repository state that the tools did not return.

The prompt validates its three inputs before producing text.

## 7. Authentication and Secret Management

The token is stored in `.env`:

```dotenv
GITHUB_TOKEN=github_pat_replace_with_your_token
GITHUB_API_BASE_URL=https://api.github.com
```

`config.py` resolves the project root with `Path(__file__).resolve()` and reads `.env` using `dotenv_values`. It does not call `os.path`, `os.getenv`, or mutate process environment variables. `.env` is listed in `.gitignore`; `.env.example` contains placeholders only.

The token is added only to the outbound `Authorization` header. It is never returned, logged, embedded in Claude Desktop configuration, or committed.

The server starts even when `.env` is absent. A tool call then returns `CONFIGURATION_ERROR` with setup guidance, allowing the instructor to observe a controlled failure instead of a startup crash.

## 8. Best Practice 1: Input Sanitization

Validation occurs before configuration loading or network access.

- Owner and repository names use an allowlist of GitHub-compatible characters and bounded lengths.
- Paths must be relative POSIX paths, cannot contain `..`, control characters, backslashes, URL-encoded separators, or empty components, and are length-limited.
- Refs use an allowlist, reject `..`, `@{`, control characters, leading/trailing slashes, and oversized values.
- `state` is one of `open`, `closed`, or `all`.
- `limit` is an integer from 1 through 50.
- `max_chars` is an integer from 256 through 12000.
- Prompt focus text rejects control characters and is limited to 300 characters.

Exploit demonstration A supplies path traversal and header-injection strings such as `../../etc/passwd` and `main\nAuthorization: Bearer stolen`. The demo asserts that validation rejects both and that the injected HTTP transport receives zero requests.

## 9. Best Practice 2: Error Disclosure

The GitHub client retains low-level failure details only inside its exception object. The service boundary maps them to fixed public error codes:

- `CONFIGURATION_ERROR`
- `INVALID_INPUT`
- `AUTHENTICATION_FAILED`
- `NOT_FOUND`
- `RATE_LIMITED`
- `UPSTREAM_ERROR`
- `UNSUPPORTED_CONTENT`

Public messages never include response bodies, request headers, stack traces, local paths, or tokens. Logs contain an operation name, HTTP status, and generated correlation ID, but no request authorization or upstream body.

Exploit demonstration B uses a mocked GitHub response whose body deliberately contains a fake token, internal filesystem path, and stack trace. The demo asserts that none of those strings appear in the MCP-facing result or captured log output.

## 10. Error Handling

The HTTP client uses a 10-second timeout and a fixed GitHub `Accept` header. Status handling is explicit:

- `401` and most `403` responses map to authentication failure.
- `404` maps to not found.
- `429`, or a `403` with remaining rate limit equal to zero, maps to rate limited.
- Timeouts, network failures, malformed JSON, unexpected shapes, and other statuses map to upstream error.

Tool functions always return a structured dictionary. Validation errors do not trigger an HTTP request. Unexpected exceptions are caught at the MCP boundary, assigned a correlation ID, and returned as `UPSTREAM_ERROR`.

## 11. Testing Strategy

Implementation follows red-green-refactor test-driven development.

1. **Configuration tests:** project-local `.env`, missing token, placeholder rejection, no token representation in exceptions.
2. **Validation tests:** normal inputs plus traversal, control characters, encoded separators, invalid ranges, and oversized values.
3. **Client tests:** successful file decode, truncation, issue filtering, timeout, malformed JSON, rate limit, and status mapping using `httpx.MockTransport`.
4. **Service tests:** stable success/error dictionaries and proof that public output never contains sensitive details.
5. **MCP contract tests:** exactly two registered tools, one registered prompt, expected names, and server import/start smoke test.
6. **Exploit demo:** an offline script runs both attacks and prints PASS/FAIL evidence suitable for the live demonstration.

The final verification command is:

```bash
.venv/bin/python -m pytest -q
```

The server smoke test launches the process, confirms it remains alive long enough to accept MCP initialization, and terminates it cleanly.

## 12. Claude Desktop Configuration

The repository includes a complete local configuration with no secret:

```json
{
  "mcpServers": {
    "github-workflow-assistant": {
      "command": "/Users/joecai/Documents/New project/assignment4_mcp_github_assistant/.venv/bin/python",
      "args": [
        "/Users/joecai/Documents/New project/assignment4_mcp_github_assistant/server.py"
      ]
    }
  }
}
```

The user manually merges this object into Claude Desktop's configuration and restarts Claude Desktop. The GitHub token remains only in the project `.env` file.

## 13. Documentation and Code Citations

The README explains environment creation, dependency installation, `.env` setup, test execution, server startup, Claude Desktop connection, exploit demonstrations, troubleshooting, and demo order.

Code adapted from external examples receives an adjacent comment naming the source URL. The citation plan covers:

- FastMCP tool and prompt decorator patterns from the official MCP Python SDK documentation.
- GitHub contents and issues endpoint behavior from GitHub REST API documentation.
- Base64 decoding uses the Python standard library and requires no copied snippet.

No code will be copied without a citation comment.

## 14. Canvas-Only Documentation

`assignment4_canvas_submission/Assignment4_Canvas_Documentation.docx` contains:

1. A table listing the private GitHub repository link, Development Workflow domain, Input Sanitization, and Error Disclosure.
2. The architecture diagram.
3. One reflection paragraph on challenges.
4. One reflection paragraph on abstraction and tool boundaries.
5. One reflection paragraph on limitations and improvements.
6. An AI-use disclosure identifying the assistant's role while confirming that the student reviewed and can explain the code.

The DOCX, rendered diagram, and reflections remain outside the Git repository. The diagram source is also stored outside the repository to obey the instruction “Do not put them in your repository.”

## 15. Live Demo Sequence

1. Activate `.venv` in VS Code.
2. Run the full pytest suite.
3. Run `scripts/demo_security_checks.py` and show both exploit checks passing.
4. Start the MCP server locally.
5. Open Claude Desktop and show the two tools and prompt.
6. Run the prompt against the private assignment repository.
7. Show one successful file read and one issue-list response.
8. Enter a traversal payload and show `INVALID_INPUT` without a network request.
9. Trigger the mocked disclosure exploit and show that secrets remain hidden.

## 16. Manual Account Actions

The assistant can build and verify the local project without receiving credentials. The user must perform or authorize these account-bound steps:

1. Create a least-privilege, read-only fine-grained GitHub token and place it in `.env` locally.
2. Authenticate GitHub CLI or create the private repository in the GitHub UI.
3. Add the instructor to the private repository; add the TA after the course supplies the TA's GitHub identity.
4. Merge the MCP configuration into Claude Desktop and restart the application.
5. Upload the Canvas-only documentation.

## 17. Acceptance Criteria

- Python source contains two distinct read-only MCP tools and one prompt.
- Server starts without crashing and has a controlled missing-credential state.
- A valid GitHub token enables both tools against a permitted repository.
- `.env` is ignored and no credential appears in source, tests, config, logs, or documentation.
- Every user-controlled input is validated before network access.
- Both exploit demonstrations pass and are reproducible offline.
- The full pytest suite passes without warnings.
- README setup instructions work from a clean checkout.
- `requirements.txt` installs all runtime and test dependencies in Python 3.12.
- Claude Desktop configuration is syntactically valid and points to the local virtual environment.
- Architecture diagram is readable and editable.
- Canvas documentation contains the required table and three reflections and is not committed to the repository.
- Repository is private and the instructor has access before submission.
