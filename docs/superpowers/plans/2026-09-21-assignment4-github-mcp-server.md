# Assignment 4 GitHub Workflow MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and document a secure, read-only Python MCP server that Claude Desktop can use to read a GitHub file, list GitHub issues, and invoke a repository-review prompt.

**Architecture:** Claude Desktop launches a FastMCP stdio server. The MCP boundary delegates to a service that validates all inputs, loads a token from a project-local `.env`, and uses a narrow `httpx` GitHub client; the boundary maps all failures to stable non-sensitive dictionaries. Canvas-only documentation and the architecture diagram live outside the Git repository.

**Tech Stack:** Python 3.12, MCP Python SDK/FastMCP, httpx, python-dotenv, pytest, draw.io, python-docx.

**Spec:** `docs/superpowers/specs/2026-09-21-assignment4-github-mcp-server-design.md`

## Global Constraints

- All production code is Python 3.12.
- The MCP surface is exactly two read-only tools plus one prompt.
- Authentication uses a project-local `.env` read with `pathlib.Path`; do not use `os.path`, `os.getenv`, or system environment variables.
- Never log, return, commit, or place the GitHub token in Claude Desktop configuration.
- Validate every user-controlled value before configuration loading or network access.
- No shell execution, repository cloning, GitHub writes, or Canvas automation.
- Cite adapted MCP and GitHub API patterns beside the relevant code.
- Keep Canvas table, diagram, and reflections outside the Git repository.
- Use `apply_patch` for source and documentation edits.
- Follow red-green-refactor for every production function.

## Review Focus

1. **Encoded path traversal (`%2e%2e`, `%2f`, `%5c`)** must be rejected before the transport is called; test in Task 2.
2. **GitHub issues endpoint returning pull requests** must not expose PRs as issues; test in Task 3.
3. **A `403` caused by rate exhaustion rather than authentication** must map to `RATE_LIMITED`; test in Task 3.
4. **An absent or placeholder `.env` token** must not crash server startup and must map to `CONFIGURATION_ERROR`; test in Tasks 1 and 4.
5. **Malicious upstream bodies containing a token, path, or stack trace** must not appear in public output or logs; test in Tasks 3, 4, and 6.

---

### Task 1: Project foundation and secure configuration

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `src/github_workflow_mcp/__init__.py`
- Create: `src/github_workflow_mcp/errors.py`
- Create: `src/github_workflow_mcp/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: the repository root inferred from `src/github_workflow_mcp/config.py`.
- Produces: `Settings(token: str, api_base_url: str)`, `ConfigurationError`, and `load_settings(env_path: Path | None = None) -> Settings`.

- [ ] **Step 1: Add dependency and ignore configuration**

Create `requirements.txt` with compatible bounds that will be resolved and tested in Python 3.12:

```text
mcp[cli]>=1.12,<2
httpx>=0.27,<1
python-dotenv>=1.0,<2
pytest>=8,<9
```

Create `.gitignore` containing `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.DS_Store`, and test coverage outputs. Create `.env.example` containing placeholder values only.

- [ ] **Step 2: Create the Python 3.12 virtual environment and install dependencies**

Run:

```bash
/Users/joecai/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Expected: installation exits 0 and `.venv/bin/python --version` reports Python 3.12.x. Network access requires explicit user approval.

- [ ] **Step 3: Write failing configuration tests**

`tests/conftest.py` adds `<repo>/src` to `sys.path` using `Path`. `tests/test_config.py` proves:

```python
def test_load_settings_reads_project_local_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GITHUB_TOKEN=github_pat_test_only\nGITHUB_API_BASE_URL=https://api.github.com\n")
    settings = load_settings(env)
    assert settings.token == "github_pat_test_only"
    assert settings.api_base_url == "https://api.github.com"


@pytest.mark.parametrize("token", ["", "github_pat_replace_with_your_token", "replace_me"])
def test_load_settings_rejects_missing_or_placeholder_token(tmp_path, token):
    env = tmp_path / ".env"
    env.write_text(f"GITHUB_TOKEN={token}\n")
    with pytest.raises(ConfigurationError) as exc:
        load_settings(env)
    assert "github_pat_test_only" not in str(exc.value)
```

- [ ] **Step 4: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`

Expected: collection fails because `github_workflow_mcp.config` does not exist.

- [ ] **Step 5: Implement the minimal configuration module**

Implement an immutable `Settings` dataclass. Resolve the default file as `Path(__file__).resolve().parents[2] / ".env"`, load it with `dotenv_values`, allow only `https://api.github.com` unless a test injects another `https://` URL, reject placeholders, and raise `ConfigurationError("GitHub authentication is not configured. Add GITHUB_TOKEN to the project .env file.")` without including the token.

`errors.py` defines `ConfigurationError`, `InputValidationError`, and `GitHubClientError(code: str, status: int | None = None)`; their string forms contain safe messages only.

- [ ] **Step 6: Run configuration tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`

Expected: all configuration tests pass.

- [ ] **Step 7: Commit the foundation**

```bash
git add .gitignore .env.example requirements.txt src/github_workflow_mcp tests/conftest.py tests/test_config.py
git commit -m "feat: add secure project configuration"
```

---

### Task 2: Input sanitization boundary

**Files:**
- Create: `src/github_workflow_mcp/validation.py`
- Create: `tests/test_validation.py`

**Interfaces:**
- Consumes: `InputValidationError` from `errors.py`.
- Produces: `validate_repo_identifier`, `validate_path`, `validate_ref`, `validate_state`, `validate_limit`, `validate_max_chars`, and `validate_focus`.

- [ ] **Step 1: Write failing allowlist and range tests**

Tests cover accepted values and one behavior per test:

```python
def test_repository_identifier_accepts_github_style_name():
    assert validate_repo_identifier("openai-python_2.0", "repository") == "openai-python_2.0"


@pytest.mark.parametrize("payload", ["../../etc/passwd", "/etc/passwd", "src\\secret.py", "src/%2e%2e/secret", "src//file.py"])
def test_path_rejects_traversal_and_ambiguous_separators(payload):
    with pytest.raises(InputValidationError):
        validate_path(payload)


def test_ref_rejects_header_injection():
    with pytest.raises(InputValidationError):
        validate_ref("main\nAuthorization: Bearer stolen")


@pytest.mark.parametrize("limit", [0, 51, True, "10"])
def test_limit_rejects_out_of_range_or_non_integer(limit):
    with pytest.raises(InputValidationError):
        validate_limit(limit)
```

Also test Unicode control characters, `@{`, `..` refs, invalid states, `max_chars` outside 256–12000, and focus text over 300 characters.

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_validation.py -q`

Expected: collection fails because `validation.py` does not exist.

- [ ] **Step 3: Implement minimal validators**

Use compiled regular expressions plus `PurePosixPath`. Decode a lowercase copy with `urllib.parse.unquote` before checking encoded traversal and separators. Reject bool explicitly before integer bounds because `bool` is a subclass of `int`. Return normalized original strings without silently repairing unsafe input.

- [ ] **Step 4: Run validator tests and full suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_validation.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit input validation**

```bash
git add src/github_workflow_mcp/validation.py tests/test_validation.py
git commit -m "feat: sanitize MCP tool inputs"
```

---

### Task 3: GitHub REST client and upstream error mapping

**Files:**
- Create: `src/github_workflow_mcp/github_client.py`
- Create: `tests/test_github_client.py`

**Interfaces:**
- Consumes: validated strings, `Settings`, and `GitHubClientError`.
- Produces: `GitHubClient(settings: Settings, transport: httpx.BaseTransport | None = None)`, `read_file(...) -> dict`, and `list_issues(...) -> list[dict]`.

- [ ] **Step 1: Write failing successful-response tests**

Use `httpx.MockTransport` to assert the real request and response behavior:

```python
def test_read_file_decodes_utf8_and_reports_truncation():
    payload = base64.b64encode("abcdef".encode()).decode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"type": "file", "content": payload}, request=request))
    client = GitHubClient(Settings("github_pat_test", "https://api.github.com"), transport=transport)
    result = client.read_file("owner", "repo", "README.md", "main", max_chars=4)
    assert result["content"] == "abcd"
    assert result["truncated"] is True


def test_list_issues_removes_pull_requests():
    response = [
        {"number": 1, "title": "Issue", "state": "open", "user": {"login": "alice"}, "labels": [], "created_at": "2026-09-01T00:00:00Z", "html_url": "https://github.com/o/r/issues/1"},
        {"number": 2, "title": "PR", "state": "open", "user": {"login": "bob"}, "labels": [], "created_at": "2026-09-02T00:00:00Z", "html_url": "https://github.com/o/r/pull/2", "pull_request": {}},
    ]
    # Mock transport returns response; assert only issue 1 remains.
```

- [ ] **Step 2: Run successful-response tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_github_client.py -q`

Expected: collection fails because `GitHubClient` does not exist.

- [ ] **Step 3: Implement request construction and response normalization**

Use an `httpx.Client` with a 10-second timeout, GitHub API version/accept headers, a fixed user agent, and `Authorization: Bearer <token>`. Add adjacent comments citing:

- `https://github.com/modelcontextprotocol/python-sdk`
- `https://docs.github.com/en/rest/repos/contents#get-repository-content`
- `https://docs.github.com/en/rest/issues/issues#list-repository-issues`

Build browser URLs with `urllib.parse.quote`. Never return response headers, bodies, or the token.

- [ ] **Step 4: Write failing upstream-error tests**

Add tests for:

```python
@pytest.mark.parametrize(
    (status, headers, expected_code),
    [
        (401, {}, "AUTHENTICATION_FAILED"),
        (403, {"X-RateLimit-Remaining": "0"}, "RATE_LIMITED"),
        (404, {}, "NOT_FOUND"),
        (429, {}, "RATE_LIMITED"),
        (500, {}, "UPSTREAM_ERROR"),
    ],
)
def test_statuses_map_without_disclosing_response_body(status, headers, expected_code):
    secret_body = "token=github_pat_never_leak /Users/private Traceback"
    # Mock response, call client, assert exception.code and absence of secret_body.
```

Also cover timeout, malformed JSON, invalid Base64, non-file content, and non-UTF-8 bytes.

- [ ] **Step 5: Run new tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_github_client.py -q`

Expected: new error-mapping tests fail because mapping is incomplete.

- [ ] **Step 6: Implement safe error mapping and verify GREEN**

Map statuses exactly as specified. Raise only `GitHubClientError(code, status)`; do not attach or stringify upstream bodies. Map decoding failures to `UNSUPPORTED_CONTENT` and request/JSON failures to `UPSTREAM_ERROR`.

Run:

```bash
.venv/bin/python -m pytest tests/test_github_client.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass without warnings.

- [ ] **Step 7: Commit the GitHub client**

```bash
git add src/github_workflow_mcp/github_client.py tests/test_github_client.py
git commit -m "feat: add safe GitHub read client"
```

---

### Task 4: Service boundary and stable public results

**Files:**
- Create: `src/github_workflow_mcp/service.py`
- Create: `tests/test_service.py`

**Interfaces:**
- Consumes: validators, `load_settings`, and `GitHubClient`.
- Produces: `GitHubWorkflowService` with `read_repository_file(...) -> dict` and `list_repository_issues(...) -> dict`.

- [ ] **Step 1: Write failing validation-before-network test**

Inject counters for settings and client creation:

```python
def test_invalid_input_returns_error_before_loading_settings_or_network():
    settings_calls = 0
    client_calls = 0
    service = GitHubWorkflowService(settings_loader=count_settings, client_factory=count_client)
    result = service.read_repository_file("owner", "repo", "../../etc/passwd", "main", 6000)
    assert result == {"ok": False, "error": {"code": "INVALID_INPUT", "message": "Repository path is not allowed."}}
    assert settings_calls == 0
    assert client_calls == 0
```

- [ ] **Step 2: Run test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_service.py -q`

Expected: collection fails because the service does not exist.

- [ ] **Step 3: Implement success paths and safe exception boundary**

Validate first, load settings second, create the client third. Return a success envelope with repository identity and source URL. On errors, return fixed messages by code. Generate a 12-character correlation ID only for upstream failures and log `operation`, `code`, `status`, and `correlation_id`; never log inputs, headers, body, or exception repr.

- [ ] **Step 4: Write failing disclosure and configuration tests**

Tests assert:

```python
def test_missing_token_becomes_configuration_error_without_server_crash():
    service = GitHubWorkflowService(settings_loader=raise_configuration_error)
    result = service.list_repository_issues("owner", "repo", "open", 10)
    assert result["error"]["code"] == "CONFIGURATION_ERROR"


def test_upstream_secret_is_absent_from_result_and_logs(caplog):
    # Fake client raises GitHubClientError after a mocked body contains a fake token/path/trace.
    # Assert those strings are absent from json.dumps(result) and caplog.text.
```

- [ ] **Step 5: Run tests and verify RED, then implement mappings**

Run: `.venv/bin/python -m pytest tests/test_service.py -q`

Expected before mapping: tests fail on wrong/missing codes. Implement fixed public messages and rerun until green.

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest -q
git add src/github_workflow_mcp/service.py tests/test_service.py
git commit -m "feat: add safe GitHub workflow service"
```

---

### Task 5: FastMCP tools, prompt, and stdio contract

**Files:**
- Create: `src/github_workflow_mcp/mcp_server.py`
- Create: `server.py`
- Create: `tests/test_mcp_contract.py`

**Interfaces:**
- Consumes: `GitHubWorkflowService` and validation functions.
- Produces: FastMCP server `mcp`, tools `read_repository_file` and `list_repository_issues`, prompt `review_repository_activity`, and root `server.py` entry point.

- [ ] **Step 1: Write failing direct contract tests**

Test prompt content and tool delegation with an injected fake service:

```python
def test_review_prompt_names_both_tools_and_prohibits_unsupported_claims():
    prompt = build_review_prompt("owner", "repo", "documentation gaps")
    assert "list_repository_issues" in prompt
    assert "read_repository_file" in prompt
    assert "Do not claim" in prompt
```

Add a subprocess integration test using the public MCP client APIs `ClientSession`, `StdioServerParameters`, and `stdio_client`. It initializes the server, lists tools and prompts, and asserts exact names:

```python
assert {tool.name for tool in tools.tools} == {"read_repository_file", "list_repository_issues"}
assert {prompt.name for prompt in prompts.prompts} == {"review_repository_activity"}
```

- [ ] **Step 2: Run contract tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_mcp_contract.py -q`

Expected: imports fail because the MCP server is not implemented.

- [ ] **Step 3: Implement FastMCP registration and entry point**

Create `FastMCP("GitHub Workflow Assistant")`. Register two `@mcp.tool()` functions and one `@mcp.prompt()` function. Add a comment beside the decorators citing `https://github.com/modelcontextprotocol/python-sdk`. Root `server.py` prepends the `src` directory with `Path`, imports `main`, and runs stdio only under `if __name__ == "__main__":`.

- [ ] **Step 4: Run contract tests and full suite**

```bash
.venv/bin/python -m pytest tests/test_mcp_contract.py -q
.venv/bin/python -m pytest -q
```

Expected: exactly two tools and one prompt are listed, and the subprocess exits cleanly after the client session closes.

- [ ] **Step 5: Commit the MCP surface**

```bash
git add src/github_workflow_mcp/mcp_server.py server.py tests/test_mcp_contract.py
git commit -m "feat: expose GitHub tools through MCP"
```

---

### Task 6: Offline exploit demonstrations

**Files:**
- Create: `scripts/demo_security_checks.py`
- Create: `tests/test_security_demo.py`

**Interfaces:**
- Consumes: validation, service, settings, GitHub client, and `httpx.MockTransport`.
- Produces: `run_input_sanitization_demo() -> dict`, `run_error_disclosure_demo() -> dict`, and a CLI that exits 0 only when both checks pass.

- [ ] **Step 1: Write failing demo tests**

```python
def test_security_demo_reports_both_exploits_blocked():
    input_result = run_input_sanitization_demo()
    disclosure_result = run_error_disclosure_demo()
    assert input_result == {"check": "input_sanitization", "blocked": True, "network_requests": 0}
    assert disclosure_result["check"] == "error_disclosure"
    assert disclosure_result["blocked"] is True
    assert disclosure_result["secret_exposed"] is False
```

- [ ] **Step 2: Run test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_security_demo.py -q`

Expected: import fails because the demo script does not exist.

- [ ] **Step 3: Implement the two deterministic exploits**

Input exploit calls the service with `../../etc/passwd` and header-injection ref input while counting transport requests. Disclosure exploit returns HTTP 500 with `github_pat_never_leak`, `/Users/private/secret.env`, and `Traceback: internal` in the body, then asserts all are absent from public output and captured logs. Print one JSON line per check plus `OVERALL: PASS`.

- [ ] **Step 4: Run test, CLI, and full suite**

```bash
.venv/bin/python -m pytest tests/test_security_demo.py -q
.venv/bin/python scripts/demo_security_checks.py
.venv/bin/python -m pytest -q
```

Expected: both exploit checks print blocked `true`, network requests are zero for sanitization, secret exposure is false, and all tests pass.

- [ ] **Step 5: Commit security demonstrations**

```bash
git add scripts/demo_security_checks.py tests/test_security_demo.py
git commit -m "test: demonstrate MCP security controls"
```

---

### Task 7: Repository documentation and Claude Desktop configuration

**Files:**
- Create: `README.md`
- Create: `claude_desktop_config.json`
- Create: `tests/test_repository_artifacts.py`

**Interfaces:**
- Consumes: verified project commands and absolute local repository path.
- Produces: clean-checkout setup instructions and a syntactically valid Claude Desktop server entry.

- [ ] **Step 1: Write failing artifact tests**

Tests parse JSON and inspect required files:

```python
def test_claude_config_uses_venv_python_and_contains_no_secret():
    config = json.loads((ROOT / "claude_desktop_config.json").read_text())
    server = config["mcpServers"]["github-workflow-assistant"]
    assert server["command"].endswith("/.venv/bin/python")
    assert server["args"] == [str(ROOT / "server.py")]
    assert "GITHUB_TOKEN" not in json.dumps(config)


def test_readme_contains_every_demo_and_setup_command():
    text = (ROOT / "README.md").read_text()
    for required in ["python3 -m venv", "pip install -r requirements.txt", "pytest -q", "demo_security_checks.py", "Claude Desktop", "Code citations"]:
        assert required in text
```

Also assert `.env` is ignored and `.env.example` contains no token matching `github_pat_[A-Za-z0-9_]{20,}`.

- [ ] **Step 2: Run artifact tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_repository_artifacts.py -q`

Expected: README/config files are missing.

- [ ] **Step 3: Write the README and configuration**

README sections: purpose, architecture overview, prerequisites, virtual environment, `.env`, tests, local server, Claude Desktop, tool examples, prompt example, security best practices, exploit demonstration, troubleshooting, demo checklist, limitations, and code citations. Use the exact absolute paths from the spec in `claude_desktop_config.json` and no `env` block.

- [ ] **Step 4: Verify documentation and clean-checkout commands**

Run:

```bash
.venv/bin/python -m pytest tests/test_repository_artifacts.py -q
.venv/bin/python -m pytest -q
git status --short
```

Expected: tests pass; only intended Task 7 files are uncommitted.

- [ ] **Step 5: Commit repository documentation**

```bash
git add README.md claude_desktop_config.json tests/test_repository_artifacts.py
git commit -m "docs: add setup and Claude Desktop configuration"
```

---

### Task 8: Architecture diagram and Canvas-only documentation

**Files:**
- Create outside repository: `../assignment4_canvas_submission/Assignment4_MCP_Architecture.drawio`
- Create outside repository: `../assignment4_canvas_submission/Assignment4_MCP_Architecture.png`
- Create outside repository: `../assignment4_canvas_submission/Assignment4_Canvas_Documentation.docx`
- Create outside repository: `../assignment4_canvas_submission/build_canvas_document.py`

**Interfaces:**
- Consumes: the final implementation, actual test evidence, repository URL when available, and actual debugging notes recorded during Tasks 1–7.
- Produces: an editable diagram, rendered diagram, and Canvas-ready document containing the required table and three reflections.

- [ ] **Step 1: Generate and validate the architecture diagram**

Use the draw.io skill to create a left-to-right diagram with these visible components and boundaries:

```text
Claude Desktop -> FastMCP stdio server -> Input validators -> Service boundary -> GitHub HTTP client -> GitHub REST API
                                                    ^                 |
                                                    |                 v
                                              .env loader       Safe error mapper
```

Use a dotted “Local machine” boundary around Claude, FastMCP, validators, service, client, and `.env`; keep GitHub REST API outside. Label the successful data flow and the blocked/error return flow. Run draw.io structural validation, export a width-capped PNG, inspect it visually, then export the final embedded diagram image.

- [ ] **Step 2: Record actual reflection evidence**

Create a short implementation log listing the actual failed test or compatibility issue that required the most reasoning, the reason the two tool boundaries stayed separate, and verified limitations. Reflections may mention only events observed during Tasks 1–7; do not invent debugging stories.

- [ ] **Step 3: Build the Canvas DOCX**

Before authoring, run the document artifact-operation marker once. Create a polished document with:

- A table: GitHub link, `Development Workflow`, `Input Sanitization`, `Error Disclosure`.
- The architecture diagram with caption.
- Three titled reflection paragraphs answering the assignment questions.
- AI disclosure: the assistant helped design, implement, test, debug, and format; the student reviewed the code and remains responsible for it.

Do not place this document or diagram inside the Git repository.

- [ ] **Step 4: Render and visually inspect every DOCX page**

Run the bundled `render_docx.py`, inspect every PNG at full resolution, repair clipping/spacing/page-break defects, and rerender until clean. Run a text extraction check for all required headings and table values.

- [ ] **Step 5: Verify repository isolation**

Run: `git status --short`

Expected: no Canvas document, `.drawio`, or diagram PNG appears in the repository status.

---

### Task 9: Final verification, private GitHub publication, and manual integrations

**Files:**
- Modify only if verification finds a defect.
- Produce outside repository: `../assignment4_canvas_submission/Assignment4_Submission_Checklist.md`.

**Interfaces:**
- Consumes: complete repository and Canvas artifacts.
- Produces: verification evidence, a private GitHub URL, and a short list of account-bound actions.

- [ ] **Step 1: Run the complete local verification gate**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/demo_security_checks.py
.venv/bin/python -m json.tool claude_desktop_config.json
git status --short
git log --oneline --decorate -10
```

Expected: all tests pass without warnings, both exploits show `OVERALL: PASS`, config parses, worktree is clean, and task commits are visible.

- [ ] **Step 2: Run secret and policy scans**

Scan tracked files for GitHub-token patterns, `GITHUB_TOKEN=` with a non-placeholder value, `os.path`, `os.getenv`, `subprocess`, `shell=True`, and Canvas artifact names. Expected: zero secret/policy violations. Confirm `.env` is ignored with `git check-ignore .env`.

- [ ] **Step 3: Rehearse the server contract locally**

Use the MCP stdio integration test to list exactly two tools and one prompt. If the user has created `.env`, make one read-only call to the private repository and confirm the returned source URL and issue list; otherwise report the live-call step as the only remaining credential-bound check.

- [ ] **Step 4: Create the private GitHub repository after user authentication**

Use GitHub CLI only after the user authorizes network access and confirms the authenticated account. Create a private repository, push `main`, and verify remote visibility is private. Add the instructor using the identity the user confirms; record that TA access remains a user action until the TA identity is supplied.

- [ ] **Step 5: Configure Claude Desktop with the user present**

Have the user merge `claude_desktop_config.json` into Claude Desktop's real configuration and restart Claude Desktop. Do not request or copy the GitHub token into chat. Verify the server and prompt appear; run the same read-only demo used in Step 3.

- [ ] **Step 6: Produce the submission checklist**

The checklist identifies:

1. Private GitHub URL and access status.
2. Canvas DOCX path.
3. Demo commands.
4. Claude Desktop connection status.
5. The two exploit results.
6. Remaining user-only actions, if any.

Commit no Canvas artifacts. If a production-code defect was fixed during final verification, add its regression test first, then make a focused final commit.
