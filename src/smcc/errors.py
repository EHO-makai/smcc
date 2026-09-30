"""SMCC error types. Errors carry the file path and cause so a human can act on them."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError


class SMCCError(Exception):
    """Base class for all SMCC errors."""


class SMCCFileError(SMCCError):
    """A file could not be read or parsed as YAML."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


class SMCCValidationError(SMCCError):
    """An SMCC object failed schema validation."""

    def __init__(self, path: Path | None, cause: ValidationError) -> None:
        self.path = path
        self.cause = cause
        location = str(path) if path is not None else "<in-memory object>"
        details = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc']) or '<object>'}: {err['msg']}"
            for err in cause.errors()
        )
        super().__init__(f"{location}: {details}")
