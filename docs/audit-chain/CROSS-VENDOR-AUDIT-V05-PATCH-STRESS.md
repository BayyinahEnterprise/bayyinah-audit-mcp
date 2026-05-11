# CROSS-VENDOR-AUDIT-V05 patch stress-test: F-V05-002 wrapper-side coverage

Auditor: GPT-5 (ChatGPT, Extended reasoning), 2026-05-11.
Driver: third Claude instance (Cowork).
Thinking time: 1 minute 36 seconds.
Continuation of `CROSS-VENDOR-AUDIT-V05.md` in the same ChatGPT thread.
Purpose: adversarially attack GPT-5's own F-V05-002 wrapper-side sanitization patch before it goes to the F-V05-002 adjudicator. Sharpens the adjudication question from "wrapper or lane #3" to "wrapper covers these classes; lane #3 still owns these classes."

---

## New finding raised by the stress test

### F-V05-010 [HIGH]

- ID: F-V05-010
- Severity: HIGH
- Locus: `bayyinah_audit_mcp/tools/cross_vendor_audit.py` :: `_redact_string`
- Substance: The proposed F-V05-002 wrapper patch (`_redact_string` plus `_sanitize_for_output` as originally drafted) is still bypassable by common non-`sk-` secret formats, quoted JSON keys, JWTs, cookies, OAuth parameters, AWS/GCP credentials, multiline wrapping, short env values, partial fingerprints, and URL-embedded credentials. The wrapper should be upgraded from narrow OpenAI-style redaction to broader credential-surface redaction, while still treating lane #3 as responsible for canonical non-leak guarantees.
- Disposition: must-fix-before-publish
- Cross-reference: F-V05-002 (this strengthens the wrapper-side argument in that finding), F-V05-001 (log-surface scrub), v0.5 raw_result allowlist contract, REVIEW-V3 defer-to-lane-#3 position.

---

## Bypass classes against the originally proposed F-V05-002 patch

For each class: a literal survivor (a string that survives the original `_redact_string` with the canary intact), why it bypasses, and the wrapper-side disposition.

### 1. Custom vendor key without `sk-` prefix

Literal survivor:

```
XAI_KEY=xai-CANARY1234567890abcdef
```

Why it bypasses: The `sk-...` regex does not match `xai-...`. The label regex only catches `api_key`, `token`, `secret`, or `password`, not `XAI_KEY`. The env loop only catches it if this exact value is in one of the four known env vars and is at least 8 chars.

Disposition: wrapper closes this class with provider-prefix patterns plus broader key-label handling.

### 2. Anthropic or vendor admin key label that does not include `api_key`

Literal survivor:

```
ANTHROPIC_ADMIN_KEY=admin-CANARY1234567890abcdef
```

Why it bypasses: The label contains `KEY`, but not the exact `api_key` spelling. The value does not start with `sk-`. The env loop misses it unless the exact admin key is present in the wrapper process env.

Disposition: wrapper closes this class with broader credential-label regex.

### 3. Google ADC or OAuth access token as a bare value

Literal survivor:

```
ya29.CANARY1234567890abcdefghijklmnopqrstuvwxyz
```

Why it bypasses: It has no `sk-` prefix and no recognized label. The env loop only catches it if it is exactly present in the wrapper env.

Disposition: wrapper closes common Google token prefixes such as `ya29.` and `AIza...`; lane #3 still owns arbitrary opaque values without labels or known prefixes.

### 4. AWS SigV4 access key or credential field

Literal survivor:

```
AWS_ACCESS_KEY_ID=AKIACANARY1234567890
```

Why it bypasses: `AWS_ACCESS_KEY_ID` does not match `api_key`, `token`, `secret`, or `password`. The value does not start with `sk-`. The env loop only catches exact env values at length >= 8.

Disposition: wrapper closes common AWS access-key labels, `AKIA...`, `ASIA...`, `X-Amz-Signature`, and SigV4 credential parameters.

### 5. Bare JWT

Literal survivor:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.CANARY1234567890abcdef.signatureCANARY1234567890
```

Why it bypasses: The JWT has no recognized label, no `sk-` prefix, and is not necessarily an env var.

Disposition: wrapper closes common JWT shape matching.

### 6. Authorization token without literal `Bearer`

Literal survivor:

```
Authorization: Token CANARY1234567890abcdef
```

Why it bypasses: The authorization regex only matches `Authorization: Bearer ...`. The generic token regex expects `token=` or `token:`, not `Token <value>`.

Disposition: wrapper closes this class by redacting `Authorization:` values for `Bearer`, `Basic`, `Token`, `ApiKey`, `API-Key`, and missing scheme forms.

### 7. Cookie or session secret

Literal survivor:

```
Cookie: session=CANARY1234567890abcdef; csrftoken=CANARYcsrf1234567890
```

Why it bypasses: `session` and `csrftoken` are not in the recognized label set. The Bearer regex does not apply. The env loop misses values not exactly in env.

Disposition: wrapper closes this by redacting `Cookie` and `Set-Cookie` header values as sensitive by default.

### 8. OAuth code exchange artifact

Literal survivor:

```
https://example.test/callback?code=CANARYcode1234567890abcdef&state=CANARYstate1234567890
```

Why it bypasses: `code` and `state` are not recognized labels. No `sk-` prefix is present. Env substitution usually misses these transient artifacts.

Disposition: wrapper closes this for `code`, `state`, `access_token`, `refresh_token`, and related URL parameters.

### 9. URL query key named `key`, not `api_key`

Literal survivor:

```
https://api.example.test/v1/models?key=CANARY1234567890abcdef
```

Why it bypasses: The regex catches `api_key=...`, but not plain `key=...`. The value has no `sk-` prefix and is not necessarily in env.

Disposition: wrapper closes common URL key parameters, including `key=`, `apiKey=`, `api_key=`, and signature fields.

### 10. Basic-auth URL credential

Literal survivor:

```
https://user:CANARY1234567890abcdef@api.example.test/v1
```

Why it bypasses: There is no recognized label before the value, no Bearer, and no `sk-` prefix.

Disposition: wrapper closes this by redacting `https://user:password@host` style credentials.

### 11. Quoted JSON key

Literal survivor:

```json
{"api_key":"xai-CANARY1234567890abcdef"}
```

Why it bypasses: The regex expects `api_key` followed directly by optional whitespace and `:` or `=`, but JSON has a closing quote between the key and the colon. The value does not start with `sk-`.

Disposition: wrapper closes this with quote-aware key-value matching.

### 12. Multiline wrapped secret

Literal survivor:

```
ValueError: provider returned sk-test-
CANARY-must-never-appear-anywhere
```

Why it bypasses: The `sk-...` regex does not cross line breaks. Exact env substitution misses the value if the original env value is unwrapped.

Disposition: wrapper partially closes this with flexible env-value redaction that tolerates whitespace and zero-width wrapping. Lane #3 still owns preventing transformed or intentionally fragmented secret output.

### 13. Short env value below the `>= 8` floor

Literal survivor:

```
Provider key was abc1234
```

Why it bypasses: The env loop ignores env values shorter than 8 chars. There is no label and no known prefix.

Disposition: wrapper lowers the env redaction floor to 4 chars with exclusions for trivial boolean/null values. Lane #3 owns anything shorter than 4 chars.

### 14. Truncated or fingerprinted echo

Literal survivor:

```
Provider rejected key sk-...9f3a
```

Why it bypasses: The `sk-` regex requires at least 8 allowed chars immediately after `sk-`; `sk-...9f3a` breaks that shape. Exact env substitution misses partials.

Disposition: wrapper closes common partial/fingerprint shapes such as `sk-...last4`, `xai-...last4`, `sha256:...`, `fingerprint=...`, and `last4=...`.

### 15. PEM private key material

Literal survivor:

```
-----BEGIN PRIVATE KEY-----
CANARY1234567890abcdef
-----END PRIVATE KEY-----
```

Why it bypasses: No existing pattern targets PEM blocks. Env substitution only catches exact values.

Disposition: wrapper closes PEM private-key blocks.

### 16. Arbitrary unlabeled opaque value

Literal survivor:

```
The provider returned CANARY1234567890abcdef as the failing credential.
```

Why it bypasses: There is no label, no known prefix, no URL/header context, and the value is not necessarily in env.

Disposition: lane #3 owns this class. Wrapper cannot safely distinguish arbitrary opaque strings from normal content without unacceptable false positives.

---

## A. Final hardened patch (full file)

GPT-5 supplied the full file as part of this stress-test response. Key changes from the original F-V05-002 patch:

- `SECRET_ENV_NAMES` expanded to include `ANTHROPIC_ADMIN_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, and the three AWS credential env vars.
- `MIN_ENV_SECRET_REDACT_CHARS = 4` (lowered from the implicit >= 8 floor).
- `ENV_VALUE_REDACTION_DENYLIST` to skip trivial values (`true`, `false`, `none`, `null`, etc.) that would otherwise over-fire.
- `_flexible_secret_pattern` builds a regex that tolerates whitespace and zero-width separators between the characters of an env-bound secret, catching multiline-wrapped leaks.
- `REDACTION_RULES` is a tuple of `(pattern, replacement)` covering PEM blocks, expanded `Authorization:` schemes, Cookie/Set-Cookie headers, basic-auth URLs, an exhaustive quoted-or-unquoted credential-label regex (with `x-api-key`, `access_token`, `refresh_token`, `session_token`, `csrf_token`, `jwt`, `client_secret`, `code`, `state`, `signature`, AWS labels, vendor-specific labels), partial-fingerprint shapes, vendor-prefix patterns (`sk-`, `xai-`, `AIza`, `ya29.`, `AKIA`/`ASIA`, `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`, `github_pat_`, `xox[baprs]-`), and bare JWTs.

Full file is in the ChatGPT thread at `chatgpt.com/c/6a0160c6-8bf0-83ea-8752-4fb4a85d2469` and reproduced verbatim below:

~~~python
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
from typing_extensions import TypedDict

from bayyinah_audit_mcp.config import load_config, resolve_path

Severity = Literal["HIGH", "MED", "LOW"]

LOGGER = logging.getLogger(__name__)

SECRET_ENV_NAMES = (
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

MIN_ENV_SECRET_REDACT_CHARS = 4
MAX_FLEXIBLE_ENV_SECRET_CHARS = 1024

ENV_VALUE_REDACTION_DENYLIST = {
    "true",
    "false",
    "none",
    "null",
    "test",
    "prod",
    "dev",
    "local",
}

ENV_WRAP_SEPARATOR_RE = r"[\s​‌‍﻿]*"

REDACTION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            flags=re.DOTALL,
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"(?i)\b(Authorization\s*:\s*(?:(?:Bearer|Basic|Token|ApiKey|API-Key)\s+)?)[^\s,;]+"
        ),
        r"\1[REDACTED_SECRET]",
    ),
    (
        re.compile(r"(?i)\b((?:Set-)?Cookie\s*:\s*)[^\r\n]+"),
        r"\1[REDACTED_SECRET]",
    ),
    (
        re.compile(r"(?i)\b(https?://)[^/\s:@]+:[^/\s@]+@"),
        r"\1[REDACTED_SECRET]@",
    ),
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
        r"\1[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"\b(?:sk|xai)-[A-Za-z0-9_\-.]{4,}(?:\.{3}|…)[A-Za-z0-9_\-.]{4,}\b"
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"(?i)\b(?:fingerprint|fp|sha256|last[_-]?4)\s*(?:=|:)\s*[A-Fa-f0-9:._-]{4,}"
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bsk-[A-Za-z0-9_\-.]{8,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bxai-[A-Za-z0-9_\-.]{8,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bya29\.[A-Za-z0-9_\-.]{10,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b"),
        "[REDACTED_SECRET]",
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


class Finding(TypedDict):
    severity: Severity
    section_ref: str
    message: str
    location: str


class CrossVendorAuditOutput(BaseModel):
    status: str
    reason: Optional[str] = None
    consensus: Optional[Any] = None
    solo_findings: Optional[dict[str, list[Finding]]] = None
    validator_panel: Optional[list[str]] = None
    api_keys_present: Optional[list[str]] = None


def _secret_values_from_env() -> list[str]:
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
    if len(secret_value) > MAX_FLEXIBLE_ENV_SECRET_CHARS:
        return None

    escaped_chars = [re.escape(character) for character in secret_value]
    return re.compile(ENV_WRAP_SEPARATOR_RE.join(escaped_chars))


def _redact_env_values(value: str) -> str:
    redacted = value

    for secret_value in _secret_values_from_env():
        redacted = redacted.replace(secret_value, "[REDACTED_SECRET]")

        flexible_pattern = _flexible_secret_pattern(secret_value)
        if flexible_pattern is not None:
            redacted = flexible_pattern.sub("[REDACTED_SECRET]", redacted)

    return redacted


def _redact_string(value: str) -> str:
    redacted = _redact_env_values(value)

    for pattern, replacement in REDACTION_RULES:
        redacted = pattern.sub(replacement, redacted)

    return redacted


def _sanitize_for_output(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _redact_string(value)

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_output(item) for item in value]

    if isinstance(value, dict):
        return {
            str(_sanitize_for_output(key)): _sanitize_for_output(item)
            for key, item in value.items()
        }

    return _redact_string(str(value))


def _sanitize_string(value: Any) -> str:
    return _redact_string(str(value))


def _sanitize_validator_panel(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return [_sanitize_string(item) for item in fallback]

    return [_sanitize_string(item) for item in value]


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


def _normalize_solo_findings(value: Any) -> dict[str, list[Finding]] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, list[Finding]] = {}

    for provider, findings in value.items():
        if not isinstance(findings, list):
            continue

        provider_findings: list[Finding] = []
        for item in findings:
            if not isinstance(item, dict):
                continue

            severity = str(item.get("severity", "LOW")).upper()
            if severity not in {"HIGH", "MED", "LOW"}:
                severity = "LOW"

            provider_findings.append(
                {
                    "severity": severity,
                    "section_ref": _sanitize_string(item.get("section_ref", "")),
                    "message": _sanitize_string(item.get("message", "")),
                    "location": _sanitize_string(item.get("location", "global")),
                }
            )

        normalized[_sanitize_string(provider)] = provider_findings

    return normalized


def _normalize_result(
    result: Any,
    validator_panel: list[str],
    key_providers: list[str],
) -> CrossVendorAuditOutput:
    if isinstance(result, dict):
        validator_panel_from_result = result.get("validator_panel")
        return CrossVendorAuditOutput(
            status=_sanitize_string(result.get("status", "ok")),
            reason=_sanitize_string(result["reason"])
            if result.get("reason") is not None
            else None,
            consensus=_sanitize_for_output(result.get("consensus")),
            solo_findings=_normalize_solo_findings(result.get("solo_findings")),
            validator_panel=_sanitize_validator_panel(
                validator_panel_from_result,
                validator_panel,
            ),
            api_keys_present=key_providers,
        )

    return CrossVendorAuditOutput(
        status="ok",
        consensus=_sanitize_for_output(result),
        validator_panel=_sanitize_validator_panel(validator_panel, validator_panel),
        api_keys_present=key_providers,
    )


def bayyinah_cross_vendor_audit(
    request: CrossVendorAuditInput,
) -> CrossVendorAuditOutput:
    """Delegate to lane #3 cross-vendor orchestrator when installed."""

    try:
        import bayyinah_audit_orchestrator
    except ImportError:
        return CrossVendorAuditOutput(
            status="unavailable",
            reason="lane #3 not installed: could not import bayyinah_audit_orchestrator.",
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
            reason=_sanitize_string(exc),
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
            close = getattr(result, "close", None)
            if callable(close):
                close()
            # DELIBERATE: this server is sync-first; if lane #3 ever ships async-only we revisit at v0.6.
            return CrossVendorAuditOutput(
                status="error",
                reason="lane #3 orchestrator returned an awaitable, but bayyinah_cross_vendor_audit expects a synchronous callable. See server logs.",
                validator_panel=request.validator_panel,
                api_keys_present=key_providers,
            )
    except Exception as exc:
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
~~~

---

## B. Residual class enumeration (lane #3 contract requirements)

Six explicit contract requirements that lane #3's own test suite must satisfy if the adjudicator splits responsibility:

1. Lane #3's own test suite must prove no raw, encoded, base64-wrapped, compressed, hashed, or otherwise transformed API keys are emitted through `status`, `reason`, `consensus`, `solo_findings`, raw logs, exceptions, telemetry, or callback traces.

2. Lane #3's own test suite must prove arbitrary opaque non-env credentials without labels or known prefixes are not included in any returned field or log surface.

3. Lane #3's own test suite must prove secrets shorter than 4 characters, if supported by any provider or test harness, are never emitted in wrapper-visible output.

4. Lane #3's own test suite must prove partially redacted fingerprints do not disclose useful entropy such as first 6 plus last 4, last 8, token hash prefixes, account-scoped credential IDs, or request-correlated signing material.

5. Lane #3's own test suite must prove screenshots, PDFs, attachments, tool traces, request dumps, response dumps, and provider SDK debug objects cannot carry credentials into wrapper-normalized fields.

6. Lane #3's own test suite must prove exception objects, nested causes, `repr()`, SDK response objects, and validation errors are converted to safe structured summaries before crossing into the MCP wrapper.

---

## What this changes for the adjudicator

The original adjudication question was binary: wrapper-side sanitization (CROSS-VENDOR-AUDIT-V05) or push to lane #3 (REVIEW-V3). The stress-test refactors that into a layered question:

- **Wrapper-side coverage with the hardened patch above closes classes 1 through 15.** A Tier 1 adjudicator (Perplexity recommended) should rule on (a) whether the hardened patch's regex set is acceptable as drafted, (b) whether the false-positive risk on broad labels like `code`, `state`, `key`, and `signature` is tolerable for the wrapper's audience, and (c) whether the env-redaction floor at 4 chars introduces unacceptable over-firing.
- **Lane #3 contract requirements cover the irreducible residual: class 16 plus the six structural contracts above.** Bilal/Fraz can decide whether bayyinah_audit_orchestrator gets these six contract tests on its own side.

The wrapper-or-lane-#3 question is no longer binary; the adjudicator's call is on the boundary and the patch quality, not on the existence of a boundary.

Source: [ChatGPT thread](https://chatgpt.com/c/6a0160c6-8bf0-83ea-8752-4fb4a85d2469)
