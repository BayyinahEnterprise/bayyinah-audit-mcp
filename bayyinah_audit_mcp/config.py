"""Environment configuration for the Bayyinah Audit MCP server.

Security note:
    BAYYINAH_PATH_STRICT defaults to off for local stdio backward compatibility.
    SSE/HTTP transports must set BAYYINAH_PATH_STRICT=1 so client-supplied paths
    are constrained to BAYYINAH_AUDIT_ROOT and symlink escapes are rejected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

Severity = Literal["HIGH", "MED", "LOW"]

VALID_SEVERITIES: tuple[str, ...] = ("HIGH", "MED", "LOW")
SEVERITY_RANK: dict[str, int] = {"LOW": 1, "MED": 2, "HIGH": 3}


@dataclass(frozen=True)
class BayyinahConfig:
    """Frozen runtime configuration.

    API keys are intentionally excluded. Cross-vendor audit reads keys only when
    that tool is invoked.
    """

    audit_root: Path
    framework_prompt: Path | None
    framework_pdf: Path | None
    section_index: Path | None
    furqan_lint_cmd: str
    severity_threshold: Severity
    path_strict: bool


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def _severity(value: str | None) -> Severity:
    normalized = (value or "MED").strip().upper()
    if normalized not in VALID_SEVERITIES:
        return "MED"
    return normalized  # type: ignore[return-value]


def _bool_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on", "strict"}


def load_config(env: Mapping[str, str] | None = None) -> BayyinahConfig:
    """Load configuration from environment variables."""

    source = env if env is not None else os.environ

    audit_root_raw = source.get("BAYYINAH_AUDIT_ROOT") or os.getcwd()
    audit_root = Path(audit_root_raw).expanduser().resolve()

    return BayyinahConfig(
        audit_root=audit_root,
        framework_prompt=_optional_path(source.get("BAYYINAH_FRAMEWORK_PROMPT")),
        framework_pdf=_optional_path(source.get("BAYYINAH_FRAMEWORK_PDF")),
        section_index=_optional_path(source.get("BAYYINAH_SECTION_INDEX")),
        furqan_lint_cmd=source.get("BAYYINAH_FURQAN_LINT_CMD", "furqan-lint"),
        severity_threshold=_severity(source.get("BAYYINAH_SEVERITY_THRESHOLD")),
        path_strict=_bool_env(source.get("BAYYINAH_PATH_STRICT")),
    )


def resolve_path(path: str | Path, config: BayyinahConfig | None = None) -> Path:
    """Resolve an absolute or root-relative path.

    BAYYINAH_AUDIT_ROOT is the base for relative paths. Absolute paths are
    allowed by default for backward compatibility.

    When BAYYINAH_PATH_STRICT=1, the resolved path must remain inside
    BAYYINAH_AUDIT_ROOT after symlink resolution. This prevents arbitrary local
    file reads when the server is exposed through SSE/HTTP.
    """

    cfg = config or load_config()
    raw = Path(path).expanduser()

    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        resolved = (cfg.audit_root / raw).resolve()

    if cfg.path_strict and not resolved.is_relative_to(cfg.audit_root):
        raise ValueError(
            f"Path '{resolved}' is outside BAYYINAH_AUDIT_ROOT '{cfg.audit_root}'. "
            "Set BAYYINAH_PATH_STRICT=0 only for trusted local stdio use."
        )

    return resolved


def severity_blocks(severity: str, threshold: str) -> bool:
    """Return whether severity meets or exceeds the configured block threshold."""

    return SEVERITY_RANK.get(severity.upper(), 0) >= SEVERITY_RANK.get(
        threshold.upper(), SEVERITY_RANK["MED"]
    )
