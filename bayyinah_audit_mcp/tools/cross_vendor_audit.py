"""bayyinah_cross_vendor_audit tool.

This tool delegates to lane #3 when the optional orchestrator is installed.
The import is intentionally lazy so base server startup does not require API
clients or keys.
"""

from __future__ import annotations

import inspect
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from bayyinah_audit_mcp.config import load_config, resolve_path

Severity = Literal["HIGH", "MED", "LOW"]
Verdict = Literal["ship", "ship_with_caveats", "hold"]

LOGGER = logging.getLogger(__name__)

# v0.5.3 (CROSS-VENDOR-AUDIT-V05-PATCH-STRESS hardening): the v0.5.2 patch
# closed F-V05-002 with a narrow five-pattern regex set. GPT-5's adversarial
# stress test surfaced 15 bypass classes still surviving that regex set,
# including non-sk- vendor keys, bare JWTs, cookies, basic-auth URLs, quoted
# JSON keys, multi-line wrapped secrets, fingerprinted echoes, PEM blocks,
# and AWS/GCP credential shapes. The hardened layers below close those 15
# classes wrapper-side. The 16th class (arbitrary unlabeled opaque values)
# stays with lane #3 by contract -- see LANE-3-CONTRACT-V05.md.

SECRET_ENV_NAMES: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_ADMIN_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "XAI_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)

# Lower the env-redaction floor from the implicit >= 8 to 4 chars, with a
# denylist of trivial values to keep false-positive risk bounded.
MIN_ENV_SECRET_REDACT_CHARS = 4
MAX_FLEXIBLE_ENV_SECRET_CHARS = 1024

ENV_VALUE_REDACTION_DENYLIST: frozenset[str] = frozenset(
    {
        "true",
        "false",
        "none",
        "null",
        "test",
        "prod",
        "dev",
        "local",
    }
)

# Tolerate whitespace and zero-width separators between characters of an
# env-bound secret value, catching multi-line wrapping leaks (bypass class 12).
ENV_WRAP_SEPARATOR_RE = r"[\s​‌‍﻿]*"

REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM private-key blocks (bypass class 15).
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            flags=re.DOTALL,
        ),
        "<REDACTED>",
    ),
    # Authorization headers across schemes: Bearer, Basic, Token, ApiKey, API-Key,
    # plus missing-scheme forms (bypass classes 6, plus the original v0.5.2 catch).
    (
        re.compile(
            r"(?i)\b(Authorization\s*:\s*(?:(?:Bearer|Basic|Token|ApiKey|API-Key)\s+)?)[^\s,;]+"
        ),
        r"\1<REDACTED>",
    ),
    # Cookie and Set-Cookie header values (bypass class 7).
    (
        re.compile(r"(?i)\b((?:Set-)?Cookie\s*:\s*)[^\r\n]+"),
        r"\1<REDACTED>",
    ),
    # Basic-auth credentials embedded in URLs (bypass class 10).
    (
        re.compile(r"(?i)\b(https?://)[^/\s:@]+:[^/\s@]+@"),
        r"\1<REDACTED>@",
    ),
    # Quoted-or-unquoted credential-label key-value matching, covering JSON,
    # query params, env-style, header-style, and common vendor labels
    # (bypass classes 1, 2, 4, 7-9, 11).
    (
        re.compile(
            r"""(?ix)
            (
                ["']?
                (?:
                    x[_-]?api[_-]?key
                  | api[_-]?key
                  | apikey
                  | key
                  | token
                  | access[_-]?token
                  | refresh[_-]?token
                  | id[_-]?token
                  | session[_-]?token
                  | auth[_-]?token
                  | csrf[_-]?token
                  | xsrf[_-]?token
                  | jwt
                  | bearer
                  | secret
                  | client[_-]?secret
                  | password
                  | passwd
                  | pwd
                  | code
                  | state
                  | signature
                  | sig
                  | credential
                  | aws[_-]?access[_-]?key[_-]?id
                  | aws[_-]?secret[_-]?access[_-]?key
                  | aws[_-]?session[_-]?token
                  | x[_-]?amz[_-]?signature
                  | anthropic[_-]?admin[_-]?key
                  | anthropic[_-]?api[_-]?key
                  | openai[_-]?api[_-]?key
                  | google[_-]?api[_-]?key
                  | xai[_-]?api[_-]?key
                )
                ["']?
                \s*(?:=|:)\s*
                ["']?
            )
            ([^"'\s,;&<>]{4,})
            """
        ),
        r"\1<REDACTED>",
    ),
    # Partial / fingerprinted echoes (bypass class 14).
    (
        re.compile(
            r"\b(?:sk|xai)-[A-Za-z0-9_\-.]{4,}(?:\.{3}|…)[A-Za-z0-9_\-.]{4,}\b"
        ),
        "<REDACTED>",
    ),
    (
        re.compile(
            r"(?i)\b(?:fingerprint|fp|sha256|last[_-]?4)\s*(?:=|:)\s*[A-Fa-f0-9:._-]{4,}"
        ),
        "<REDACTED>",
    ),
    # Vendor-prefix bare-value shapes (bypass classes 3, 4, 5, plus the
    # original v0.5.2 sk- catches widened to permit dots).
    (
        re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_\-.]{8,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bxai-[A-Za-z0-9_\-.]{8,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bya29\.[A-Za-z0-9_\-.]{10,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "<REDACTED>",
    ),
    (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "<REDACTED>",
    ),
    # v0.5.4: defense-in-depth on additional vendor prefixes the spec
    # does not explicitly target. The lane #3 contract still owns the
    # canonical non-leak guarantee for these vendors; the wrapper just
    # catches the most common bare-value forms.
    (
        re.compile(r"\bpplx-[A-Za-z0-9_\-]{20,}\b"),  # Perplexity
        "<REDACTED>",
    ),
    (
        re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}\b"),  # Groq
        "<REDACTED>",
    ),
    (
        re.compile(r"\br8_[A-Za-z0-9_\-]{20,}\b"),  # Replicate
        "<REDACTED>",
    ),
    (
        re.compile(r"\bhf_[A-Za-z0-9_\-]{20,}\b"),  # HuggingFace
        "<REDACTED>",
    ),
    # Bare JWTs: three dot-separated base64url segments (bypass class 5).
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b"),
        "<REDACTED>",
    ),
)


class CrossVendorAuditInput(BaseModel):
    """Input model for bayyinah_cross_vendor_audit."""

    model_config = ConfigDict(extra="forbid")

    artifact_text: str | None = Field(
        default=None,
        description="Inline artifact text to audit.",
    )
    artifact_path: str | None = Field(
        default=None,
        description="Root-relative or absolute artifact path.",
    )
    audit_goal: str = Field(
        default="Run cross-vendor Bayyinah validation.",
        description="Specific audit objective.",
    )
    section_refs: list[str] = Field(
        default_factory=list,
        description="Bayyinah section references to emphasize.",
    )
    validator_panel: list[str] = Field(
        default_factory=lambda: ["anthropic", "openai"],
        description="Validator names requested from lane #3.",
    )
    timeout_seconds: int = Field(
        default=180,
        ge=10,
        le=1800,
        description="Requested orchestrator timeout.",
    )


class Finding(BaseModel):
    """Bayyinah finding wire shape returned by lane #3."""

    model_config = ConfigDict(extra="ignore")

    severity: Severity
    section_ref: str
    message: str
    location: str


class Consensus(BaseModel):
    """Structured cross-vendor consensus envelope returned by lane #3.

    v0.5.4 adds ``metadata`` as a forward-compat hatch for lane #3
    implementations that surface fields beyond the four canonical ones.
    Wrapper still scrubs every string value reachable inside the dict
    via ``_scrub_dict`` so a metadata payload containing a raw API key
    is redacted on the way out.
    """

    model_config = ConfigDict(extra="ignore")

    verdict: Verdict
    reasoning: str
    agreed_findings: list[Finding]
    disagreement_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossVendorAuditOutput(BaseModel):
    status: str
    reason: Optional[str] = None
    consensus: Optional[Consensus] = None
    solo_findings: Optional[dict[str, list[Finding]]] = None
    validator_panel: Optional[list[str]] = None
    api_keys_present: Optional[list[str]] = None


def _secret_values_from_env() -> list[str]:
    """Return env values that look like real credentials.

    Lowered floor at MIN_ENV_SECRET_REDACT_CHARS = 4 to catch short keys; the
    denylist keeps trivial values (`true`, `false`, `none`, `null`, etc.)
    out of the redaction set to bound false-positive risk.
    """

    values: list[str] = []

    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if not value:
            continue

        stripped = value.strip()
        if len(stripped) < MIN_ENV_SECRET_REDACT_CHARS:
            continue

        if stripped.lower() in ENV_VALUE_REDACTION_DENYLIST:
            continue

        values.append(stripped)

    return values


def _flexible_secret_pattern(secret_value: str) -> re.Pattern[str] | None:
    """Build a regex that tolerates wrap-whitespace between secret characters.

    Catches multi-line wrapping leaks (e.g. a key line-broken across a
    traceback). Skipped if the secret is longer than
    MAX_FLEXIBLE_ENV_SECRET_CHARS to keep regex compile cost bounded.
    """

    if len(secret_value) > MAX_FLEXIBLE_ENV_SECRET_CHARS:
        return None

    escaped_chars = [re.escape(character) for character in secret_value]
    return re.compile(ENV_WRAP_SEPARATOR_RE.join(escaped_chars))


def _redact_env_values(value: str) -> str:
    redacted = value

    for secret_value in _secret_values_from_env():
        redacted = redacted.replace(secret_value, "<REDACTED>")

        flexible_pattern = _flexible_secret_pattern(secret_value)
        if flexible_pattern is not None:
            redacted = flexible_pattern.sub("<REDACTED>", redacted)

    return redacted


def _scrub(text: str) -> str:
    """Redact common credential shapes plus env-bound secret values.

    Two layers:

    1. Env-bound value substitution against SECRET_ENV_NAMES, with flexible
       whitespace matching so wrapped secrets do not survive.
    2. REDACTION_RULES regex tuple covering 15 bypass classes that survived
       the narrower v0.5.2 regex set.

    The 16th class (arbitrary unlabeled opaque values) belongs to lane #3
    per LANE-3-CONTRACT-V05.md.
    """

    redacted = _redact_env_values(text)

    for pattern, replacement in REDACTION_RULES:
        redacted = pattern.sub(replacement, redacted)

    return redacted


def _scrub_dict(value: Any, _seen: set[int] | None = None) -> Any:
    """Recursively scrub string leaves inside a nested dict/list structure.

    v0.5.4: Consensus.metadata accepts arbitrary dict shapes from lane #3.
    Every string leaf is run through _scrub so a key value buried inside a
    nested debug dict is still redacted. Non-string leaves pass through
    unchanged.

    v0.5.5 (F-V05-DICT-CYCLE-LOOP): defense-in-depth cycle guard. Lane #3
    is contractually-bound to return JSON-serialisable structures (no
    cycles by construction), but a buggy or adversarial lane-#3 impl
    returning a self-referential structure would hang this walker. The
    `_seen` set tracks `id()` of containers already entered on the
    current recursion path; revisiting yields the literal cycle-sentinel
    string `"<cycle>"` rather than recursing further. The guard is per-
    call (None default + freshly constructed set on first entry) so
    sibling containers with the same memory reuse pattern do not
    poison each other.
    """

    if isinstance(value, str):
        return _scrub(value)

    if isinstance(value, (dict, list, tuple)):
        if _seen is None:
            _seen = set()
        container_id = id(value)
        if container_id in _seen:
            return "<cycle>"
        _seen = _seen | {container_id}

        if isinstance(value, dict):
            return {k: _scrub_dict(v, _seen) for k, v in value.items()}
        if isinstance(value, list):
            return [_scrub_dict(item, _seen) for item in value]
        return tuple(_scrub_dict(item, _seen) for item in value)

    return value


def _scrub_optional(value: Any) -> str | None:
    if value is None:
        return None
    return _scrub(str(value))


def _read_artifact(path: Path | None, inline_text: str | None) -> str:
    if inline_text:
        return inline_text

    if path is None:
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _api_key_providers_present() -> list[str]:
    provider_to_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "xai": "XAI_API_KEY",
    }
    return [
        provider
        for provider, env_name in provider_to_env.items()
        if os.environ.get(env_name)
    ]


def _select_callable(orchestrator_module: Any) -> Any | None:
    for name in (
        "run_cross_vendor_audit",
        "cross_vendor_audit",
        "audit",
        "run_audit",
    ):
        candidate = getattr(orchestrator_module, name, None)
        if callable(candidate):
            return candidate

    cls = getattr(orchestrator_module, "BayyinahAuditOrchestrator", None)
    if cls is not None:
        instance = cls()
        for name in (
            "run_cross_vendor_audit",
            "cross_vendor_audit",
            "audit",
            "run_audit",
        ):
            candidate = getattr(instance, name, None)
            if callable(candidate):
                return candidate

    return None


def _filtered_kwargs(func: Any, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return payload

    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )

    if accepts_var_kwargs:
        return payload

    return {
        key: value
        for key, value in payload.items()
        if key in signature.parameters
    }


def _normalize_severity(value: Any) -> Severity:
    severity = str(value or "LOW").upper()
    if severity in {"HIGH", "MED", "LOW"}:
        return severity  # type: ignore[return-value]
    return "LOW"


def _normalize_finding(value: Any) -> Finding | None:
    if isinstance(value, Finding):
        return Finding(
            severity=value.severity,
            section_ref=value.section_ref,
            message=_scrub(value.message),
            location=_scrub(value.location),
        )

    if not isinstance(value, dict):
        return None

    return Finding(
        severity=_normalize_severity(value.get("severity")),
        section_ref=str(value.get("section_ref", "")),
        message=_scrub(str(value.get("message", ""))),
        location=_scrub(str(value.get("location", "global"))),
    )


def _normalize_solo_findings(value: Any) -> dict[str, list[Finding]] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, list[Finding]] = {}

    for provider, findings in value.items():
        if not isinstance(findings, list):
            continue

        provider_findings: list[Finding] = []
        for item in findings:
            finding = _normalize_finding(item)
            if finding is not None:
                provider_findings.append(finding)

        normalized[str(provider)] = provider_findings

    return normalized


def _normalize_verdict(value: Any) -> Verdict:
    verdict = str(value or "hold").strip().lower()
    if verdict in {"ship", "ship_with_caveats", "hold"}:
        return verdict  # type: ignore[return-value]
    return "hold"


def _normalize_consensus(value: Any) -> Consensus | None:
    if value is None:
        return None

    if isinstance(value, Consensus):
        return Consensus(
            verdict=value.verdict,
            reasoning=_scrub(value.reasoning),
            agreed_findings=[
                finding
                for finding in (_normalize_finding(item) for item in value.agreed_findings)
                if finding is not None
            ],
            disagreement_count=value.disagreement_count,
            metadata=_scrub_dict(value.metadata) if value.metadata else {},
        )

    if not isinstance(value, dict):
        return None

    raw_findings = value.get("agreed_findings", [])
    agreed_findings: list[Finding] = []

    if isinstance(raw_findings, list):
        agreed_findings = [
            finding
            for finding in (_normalize_finding(item) for item in raw_findings)
            if finding is not None
        ]

    try:
        disagreement_count = int(value.get("disagreement_count", 0))
    except (TypeError, ValueError):
        disagreement_count = 0

    raw_metadata = value.get("metadata")
    metadata = _scrub_dict(raw_metadata) if isinstance(raw_metadata, dict) else {}

    return Consensus(
        verdict=_normalize_verdict(value.get("verdict")),
        reasoning=_scrub(str(value.get("reasoning", ""))),
        agreed_findings=agreed_findings,
        disagreement_count=disagreement_count,
        metadata=metadata,
    )


def _normalize_result(
    result: Any,
    validator_panel: list[str],
    key_providers: list[str],
) -> CrossVendorAuditOutput:
    if isinstance(result, Consensus):
        return CrossVendorAuditOutput(
            status="ok",
            consensus=_normalize_consensus(result),
            validator_panel=validator_panel,
            api_keys_present=key_providers,
        )

    if isinstance(result, dict):
        validator_panel_from_result = result.get("validator_panel")
        return CrossVendorAuditOutput(
            status=str(result.get("status", "ok")),
            reason=_scrub_optional(result.get("reason")),
            consensus=_normalize_consensus(result.get("consensus")),
            solo_findings=_normalize_solo_findings(result.get("solo_findings")),
            validator_panel=validator_panel_from_result
            if isinstance(validator_panel_from_result, list)
            else validator_panel,
            api_keys_present=key_providers,
        )

    return CrossVendorAuditOutput(
        status="ok",
        reason="lane #3 returned a non-dict result; no structured consensus was available.",
        validator_panel=validator_panel,
        api_keys_present=key_providers,
    )


def bayyinah_cross_vendor_audit(
    request: CrossVendorAuditInput,
) -> CrossVendorAuditOutput:
    """Delegate to lane #3 cross-vendor orchestrator when installed."""

    try:
        import bayyinah_audit_orchestrator  # type: ignore[import-not-found]
    except ImportError as exc:
        return CrossVendorAuditOutput(
            status="unavailable",
            reason=_scrub(
                f"lane #3 not installed: could not import bayyinah_audit_orchestrator ({exc})"
            ),
            validator_panel=request.validator_panel,
            api_keys_present=[],
        )

    config = load_config()

    try:
        artifact_path = (
            resolve_path(request.artifact_path, config) if request.artifact_path else None
        )
    except ValueError as exc:
        return CrossVendorAuditOutput(
            status="error",
            reason=_scrub(str(exc)),
            validator_panel=request.validator_panel,
            api_keys_present=[],
        )

    artifact_text = _read_artifact(artifact_path, request.artifact_text)
    key_providers = _api_key_providers_present()

    callable_target = _select_callable(bayyinah_audit_orchestrator)
    if callable_target is None:
        return CrossVendorAuditOutput(
            status="unavailable",
            reason="lane #3 module is installed, but no compatible audit callable was found.",
            validator_panel=request.validator_panel,
            api_keys_present=key_providers,
        )

    payload = {
        "artifact_text": artifact_text,
        "artifact_path": str(artifact_path) if artifact_path else None,
        "audit_goal": request.audit_goal,
        "section_refs": request.section_refs,
        "validator_panel": request.validator_panel,
        "timeout_seconds": request.timeout_seconds,
        "api_keys_present": key_providers,
    }

    try:
        result = callable_target(**_filtered_kwargs(callable_target, payload))
        if inspect.isawaitable(result):
            # v0.5.3: close the coroutine to avoid "coroutine was never
            # awaited" warnings (F-V05-009).
            close = getattr(result, "close", None)
            if callable(close):
                close()
            # DELIBERATE: this server is sync-first; if lane #3 ever ships
            # async-only we revisit at v0.6.
            return CrossVendorAuditOutput(
                status="error",
                reason="lane #3 orchestrator returned an awaitable, but bayyinah_cross_vendor_audit expects a synchronous callable. See server logs.",
                validator_panel=request.validator_panel,
                api_keys_present=key_providers,
            )
    except Exception as exc:
        # F-V05-001 (RE-APPLIED in v0.5.3): the v0.5.2 round reverted this
        # fix and the original LOGGER.exception("...: %r", exc) came back.
        # The %r format echoes the full exception repr (with args, which can
        # carry secrets if lane #3 embedded them in the message). exc_info
        # is also deliberately omitted; the traceback can carry leaked values
        # in local-variable reprs. Log only the exception class name here.
        LOGGER.error(
            "Lane #3 orchestrator failed during bayyinah_cross_vendor_audit: %s",
            type(exc).__name__,
        )
        return CrossVendorAuditOutput(
            status="error",
            reason=f"lane #3 orchestrator raised {type(exc).__name__}; see server logs.",
            validator_panel=request.validator_panel,
            api_keys_present=key_providers,
        )

    return _normalize_result(result, request.validator_panel, key_providers)
