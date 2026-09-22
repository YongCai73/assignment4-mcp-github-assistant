from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import unquote

from .errors import InputValidationError


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def validate_repo_identifier(value: object, field_name: str) -> str:
    message = f"{field_name.replace('_', ' ').capitalize()} is not allowed."
    if not isinstance(value, str):
        raise InputValidationError(message)
    if value != value.strip() or not _IDENTIFIER_RE.fullmatch(value):
        raise InputValidationError(message)
    return value


def validate_path(value: object) -> str:
    message = "Repository path is not allowed."
    if not isinstance(value, str) or not (1 <= len(value) <= 240):
        raise InputValidationError(message)
    if value != value.strip() or _CONTROL_RE.search(value):
        raise InputValidationError(message)

    decoded = unquote(value)
    if decoded.startswith("/") or "\\" in decoded:
        raise InputValidationError(message)

    parts = decoded.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InputValidationError(message)
    if PurePosixPath(decoded).is_absolute():
        raise InputValidationError(message)
    return value


def validate_ref(value: object) -> str:
    message = "Git reference is not allowed."
    if not isinstance(value, str) or not (1 <= len(value) <= 100):
        raise InputValidationError(message)
    if value != value.strip() or _CONTROL_RE.search(value):
        raise InputValidationError(message)

    decoded = unquote(value)
    if decoded != value or not _REF_RE.fullmatch(value):
        raise InputValidationError(message)
    if ".." in value or "@{" in value or value.startswith("/") or value.endswith("/"):
        raise InputValidationError(message)
    return value


def validate_state(value: object) -> str:
    if not isinstance(value, str) or value not in {"open", "closed", "all"}:
        raise InputValidationError("Issue state must be open, closed, or all.")
    return value


def validate_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 50):
        raise InputValidationError("Issue limit must be an integer from 1 to 50.")
    return value


def validate_max_chars(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (256 <= value <= 12000):
        raise InputValidationError("max_chars must be an integer from 256 to 12000.")
    return value


def validate_focus(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise InputValidationError("Review focus is not allowed.")
    if _CONTROL_RE.search(value):
        raise InputValidationError("Review focus is not allowed.")
    return value
