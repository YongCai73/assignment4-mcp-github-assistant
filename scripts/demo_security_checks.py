from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path

import httpx


_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from github_workflow_mcp.config import Settings
from github_workflow_mcp.github_client import GitHubClient
from github_workflow_mcp.service import GitHubWorkflowService


def run_input_sanitization_demo() -> dict[str, object]:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json=[], request=request)

    transport = httpx.MockTransport(handler)
    service = GitHubWorkflowService(
        settings_loader=lambda: Settings("github_pat_offline_demo"),
        client_factory=lambda settings: GitHubClient(settings, transport=transport),
    )

    traversal = service.read_repository_file(
        "owner",
        "repository",
        "../../etc/passwd",
        "main",
        6000,
    )
    header_injection = service.read_repository_file(
        "owner",
        "repository",
        "README.md",
        "main\nAuthorization: Bearer stolen",
        6000,
    )
    blocked = (
        traversal.get("error", {}).get("code") == "INVALID_INPUT"
        and header_injection.get("error", {}).get("code") == "INVALID_INPUT"
        and request_count == 0
    )
    return {
        "check": "input_sanitization",
        "blocked": blocked,
        "network_requests": request_count,
    }


def run_error_disclosure_demo() -> dict[str, object]:
    token = "github_pat_never_leak"
    unsafe_fragments = (token, "/Users/private/secret.env", "Traceback: internal")
    malicious_body = " | ".join(unsafe_fragments)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=malicious_body, request=request)

    service = GitHubWorkflowService(
        settings_loader=lambda: Settings(token),
        client_factory=lambda settings: GitHubClient(
            settings,
            transport=httpx.MockTransport(handler),
        ),
    )

    log_buffer = io.StringIO()
    handler_for_capture = logging.StreamHandler(log_buffer)
    logger = logging.getLogger("github_workflow_mcp.service")
    previous_level = logger.level
    logger.addHandler(handler_for_capture)
    logger.setLevel(logging.WARNING)
    try:
        result = service.list_repository_issues("owner", "repository", "open", 10)
    finally:
        logger.removeHandler(handler_for_capture)
        logger.setLevel(previous_level)
        handler_for_capture.close()

    public_material = json.dumps(result, sort_keys=True) + log_buffer.getvalue()
    secret_exposed = any(fragment in public_material for fragment in unsafe_fragments)
    error = result.get("error", {})
    error_code = error.get("code") if isinstance(error, dict) else None
    blocked = error_code == "UPSTREAM_ERROR" and not secret_exposed
    return {
        "check": "error_disclosure",
        "blocked": blocked,
        "secret_exposed": secret_exposed,
        "error_code": error_code,
    }


def main() -> int:
    results = [run_input_sanitization_demo(), run_error_disclosure_demo()]
    for result in results:
        print(json.dumps(result, sort_keys=True))
    passed = all(result["blocked"] is True for result in results)
    print(f"OVERALL: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
