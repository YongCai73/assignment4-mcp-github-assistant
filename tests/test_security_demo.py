from __future__ import annotations

from scripts.demo_security_checks import (
    run_error_disclosure_demo,
    run_input_sanitization_demo,
)


def test_security_demo_reports_both_exploits_blocked():
    input_result = run_input_sanitization_demo()
    disclosure_result = run_error_disclosure_demo()

    assert input_result == {
        "check": "input_sanitization",
        "blocked": True,
        "network_requests": 0,
    }
    assert disclosure_result["check"] == "error_disclosure"
    assert disclosure_result["blocked"] is True
    assert disclosure_result["secret_exposed"] is False
    assert disclosure_result["error_code"] == "UPSTREAM_ERROR"
