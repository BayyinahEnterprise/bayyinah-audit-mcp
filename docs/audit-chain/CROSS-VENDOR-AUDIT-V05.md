# CROSS-VENDOR-AUDIT-V05: independent cross-vendor audit of Bayyinah Audit MCP Server v0.5

Auditor: GPT-5 (ChatGPT, Extended reasoning), 2026-05-10.
Driver: third Claude instance (Cowork).
Scope: v0.5 deltas only. REVIEW-V1.md, REVIEW-V2.md, and REVIEW-V3.md findings not re-flagged unless v0.5 reintroduced them.
Thinking time: 1 minute 16 seconds.

## Why this round exists

REVIEW-V1 through REVIEW-V3 were all produced by Claude instances:

- REVIEW-V1.md -- second Claude's v0.1 review (input to v0.3 patches).
- REVIEW-V2.md -- second Claude's v0.4 delta review (input to v0.5 patches).
- REVIEW-V3.md -- second Claude's v0.5 intra-vendor verdict (verdict: shippable; deferred contract-boundary leak vectors to v0.6).

PMD v1.2 cross-vendor rotation requires a non-producer-vendor pass before a publication-bound release. The v0.5 producers (and REVIEW-V3 reviewer) were all Claude. ChatGPT was producer for v0.1 through v0.3 only and is therefore eligible as auditor for v0.5. This round is that cross-vendor pass. Output: CROSS-VENDOR-AUDIT-V05.md (canonical). REVIEW-V4.md is preserved as a duplicate-content historical cell under the intra-Claude numbering scheme; second Claude noted on 2026-05-11 that separating chains is cleaner discipline.

## Cross-vendor disagreement to surface for the adjudicator

REVIEW-V3.md characterised the consensus/reason/solo_findings leak surface as a "contract-boundary issue, not a wrapper bug" and deferred it to v0.6, recommending that lane #3 own the canary requirement in its own test suite. GPT-5 (F-V05-002 below) characterises the same surface as `must-fix-before-publish` HIGH and proposes wrapper-side sanitization (`_redact_string` plus `_sanitize_for_output`). This is a genuine cross-vendor friction, not a misunderstanding. An adjudicator pass per PMD v1.2 cross-vendor rotation is the next move if v0.5 is to publish on hardened consensus. The remaining sections record GPT-5's findings verbatim.

---

## secret-leak

### F-V05-001 [HIGH]

- ID: F-V05-001
- Severity: HIGH
- Locus: `bayyinah_audit_mcp/tools/cross_vendor_audit.py` :: exception handler in `bayyinah_cross_vendor_audit`
- Substance: The v0.5 canary test proves the returned MCP response does not echo the exception string, but the handler still calls `LOGGER.exception` with `%r exc`. If lane #3 raises `ValueError("boom; key was sk-...")`, the canary can leak into server logs even though `result.model_dump_json()` is clean. This is a real secret-leak vector outside the response surface.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 real-test-gap closure for exception scrub; related to v0.3 secret-leak hardening. Not flagged in REVIEW-V3.md.

### F-V05-002 [HIGH]

- ID: F-V05-002
- Severity: HIGH
- Locus: `bayyinah_audit_mcp/tools/cross_vendor_audit.py` :: `_normalize_result` and `_normalize_solo_findings`
- Substance: The raw_result allowlist blocks unknown keys such as `raw_log`, but allowed fields are still unsanitized. A lane #3 orchestrator can leak secrets through `reason`, `consensus`, `solo_findings[].message`, `solo_findings[].location`, `status`, or `validator_panel`. The current v0.5 raw_result test only proves that an omitted disallowed key is dropped. It does not prove that allowed fields are safe.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 raw_result allowlist contract; related to v0.3 exception scrub. REVIEW-V3.md surfaced the same surface but deferred to v0.6 as a contract-boundary issue. Cross-vendor disagreement noted above.

## path-safety

### F-V05-003 [MEDIUM]

- ID: F-V05-003
- Severity: MEDIUM
- Locus: `README.md` :: Run and Security sections
- Substance: The Security section correctly says `BAYYINAH_PATH_STRICT=1` is required for SSE/HTTP, but the SSE and streamable HTTP copy-paste run snippets do not set it inline. A user following the visible run examples can expose the server over network transport with strict path containment off.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 README Security section; related to prior BAYYINAH_PATH_STRICT hardening.

## test-coverage

### F-V05-004 [MEDIUM]

- ID: F-V05-004
- Severity: MEDIUM
- Locus: `tests/test_tools.py::test_cross_vendor_audit_exception_path_does_not_leak_canary`
- Substance: The test checks `result.model_dump_json()`, but does not capture `caplog` or otherwise assert that the canary is absent from logs. This misses F-V05-001.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 real-test-gap closure.

### F-V05-005 [MEDIUM]

- ID: F-V05-005
- Severity: MEDIUM
- Locus: `tests/test_tools.py::test_cross_vendor_audit_does_not_leak_via_raw_result`
- Substance: The test only covers secret data in a disallowed `raw_log` field. It should also cover secret data inside allowed fields such as `reason`, `consensus`, `solo_findings`, and `validator_panel`. This misses F-V05-002.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 raw_result allowlist test.

## packaging-CI

### F-V05-006 [LOW]

- ID: F-V05-006
- Severity: LOW
- Locus: `.github/workflows/ci.yml` :: test job
- Substance: CI runs pytest but does not build the package or validate README rendering. That is why the broken README Markdown fences can survive 14/14 pytest passing. Add a packaging check such as `python -m build` plus `twine check dist/*`, or a Markdown fence lint step.
- Disposition: nice-to-have
- Cross-reference: v0.4 CI introduction; related to F-V05-007.

### F-V05-007 [LOW]

- ID: F-V05-007
- Severity: LOW
- Locus: `pyproject.toml` :: `[project.optional-dependencies].cross-vendor`
- Substance: The cross-vendor extra installs vendor SDKs, but not `bayyinah_audit_orchestrator` itself. If lane #3 is intentionally external, this is acceptable, but README should explicitly say that the extra does not install the orchestrator and that the tool remains unavailable without the lane #3 package/module.
- Disposition: accept-with-rationale
- Cross-reference: v0.4 packaging; v0.5 cross-vendor test hardening.

## documentation

### F-V05-008 [MEDIUM]

- ID: F-V05-008
- Severity: MEDIUM
- Locus: `README.md` :: all fenced code blocks
- Substance: The README fences are malformed. Several opening fences are never closed, so PyPI/GitHub rendering can turn most of the README into one large code block and obscure install, run, security, and environment guidance.
- Disposition: must-fix-before-publish
- Cross-reference: v0.5 README Security section; related to F-V05-006. Also independently observed during T00 substrate reconciliation by the driver instance.

## other

### F-V05-009 [LOW]

- ID: F-V05-009
- Severity: LOW
- Locus: `bayyinah_audit_mcp/tools/cross_vendor_audit.py` :: `inspect.isawaitable` branch
- Substance: When the orchestrator returns an awaitable, the tool returns an error but does not close the coroutine object. This can produce "coroutine was never awaited" warnings and noisy runtime behavior. It is not a publish blocker, but it is cheap to close if the object exposes `close()`.
- Disposition: nice-to-have
- Cross-reference: v0.5 TODO comment documenting sync-first contract.

---

## Auditor-proposed patches

GPT-5 supplied two full-file patches alongside the findings. They are reproduced verbatim below as part of the audit chain. Acceptance and absorption decisions are deferred to the producer pass that follows REVIEW-V4 (and to the cross-vendor adjudicator on F-V05-002 specifically).

### Patched `bayyinah_audit_mcp/tools/cross_vendor_audit.py`

Introduces `SECRET_PATTERNS`, `_redact_string`, `_sanitize_for_output`, `_sanitize_string`, `_sanitize_validator_panel`. Sanitizes every field that flows back through `_normalize_result` and `_normalize_solo_findings`. Switches the exception handler from `LOGGER.exception("...: %r", exc)` (which echoes the full repr to logs) to `LOGGER.error("...: %s", type(exc).__name__)` (type name only). Closes the awaitable on the rejection path.

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
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(Authorization\s*:\s*Bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*(?:=|:)\s*)[^\s,;]+"),
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
    return [
        value
        for name in SECRET_ENV_NAMES
        if (value := os.environ.get(name)) and len(value) >= 8
    ]


def _redact_string(value: str) -> str:
    redacted = value

    for secret_value in _secret_values_from_env():
        redacted = redacted.replace(secret_value, "[REDACTED_SECRET]")

    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)}[REDACTED_SECRET]"
                if match.groups()
                else "[REDACTED_SECRET]"
            ),
            redacted,
        )

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

### Patched `README.md`

Closes all fenced code blocks. Inlines `BAYYINAH_PATH_STRICT=1` into the SSE and streamable-HTTP run snippets. Adds an explicit note that the `cross-vendor` extra does not install the lane #3 orchestrator.

~~~markdown
# Bayyinah Audit MCP Server

## Install

```bash
pip install -e ".[all]"
```

Minimal install:

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[pdf]"
pip install -e ".[cross-vendor]"
```

Note: the `cross-vendor` extra installs vendor SDK dependencies only. The `bayyinah_cross_vendor_audit` tool also requires the optional lane #3 `bayyinah_audit_orchestrator` module to be installed or otherwise importable.

## Run

Default stdio transport:

```bash
python -m bayyinah_audit_mcp
```

SSE transport:

```bash
export BAYYINAH_AUDIT_ROOT="$PWD"
export BAYYINAH_PATH_STRICT="1"
python -m bayyinah_audit_mcp --transport sse --port 8000
```

Streamable HTTP transport:

```bash
export BAYYINAH_AUDIT_ROOT="$PWD"
export BAYYINAH_PATH_STRICT="1"
python -m bayyinah_audit_mcp --transport streamable-http --port 8000
```

## Security

When exposing the server over SSE or streamable HTTP, set `BAYYINAH_PATH_STRICT=1`. This constrains client-supplied file paths to `BAYYINAH_AUDIT_ROOT` after symlink resolution and prevents arbitrary local file reads. Leaving strict mode off is intended only for trusted local stdio use.

## Environment variables

```bash
export BAYYINAH_AUDIT_ROOT="$PWD"
export BAYYINAH_PATH_STRICT="1"
export BAYYINAH_FRAMEWORK_PROMPT="/path/to/SKILL.md"
export BAYYINAH_FRAMEWORK_PDF="/path/to/framework.pdf"
export BAYYINAH_SECTION_INDEX="/path/to/section_index.json"
export BAYYINAH_FURQAN_LINT_CMD="furqan-lint"
export BAYYINAH_SEVERITY_THRESHOLD="MED"
```

Cross-vendor audits read API keys only when `bayyinah_cross_vendor_audit` is invoked:

```bash
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."
export XAI_API_KEY="..."
```

## Claude Desktop config snippet

```json
{
  "mcpServers": {
    "bayyinah-audit": {
      "command": "python",
      "args": ["-m", "bayyinah_audit_mcp"],
      "env": {
        "BAYYINAH_AUDIT_ROOT": "/absolute/path/to/audit/root",
        "BAYYINAH_PATH_STRICT": "1",
        "BAYYINAH_FRAMEWORK_PROMPT": "/absolute/path/to/SKILL.md",
        "BAYYINAH_SEVERITY_THRESHOLD": "MED"
      }
    }
  }
}
```
~~~

---

## Publication-readiness verdict

**PUBLISH-AFTER-PATCH**

Note: REVIEW-V3.md verdict was "shippable as-is." REVIEW-V4 verdict is "PUBLISH-AFTER-PATCH." The two reviews disagree on six items (F-V05-001 through F-V05-005 plus F-V05-008). Adjudication is the next step.

---

## Findings tally

- HIGH: 2 (F-V05-001, F-V05-002)
- MEDIUM: 4 (F-V05-003, F-V05-004, F-V05-005, F-V05-008)
- LOW: 3 (F-V05-006, F-V05-007, F-V05-009)
- must-fix-before-publish: 6
- nice-to-have: 2
- accept-with-rationale: 1

Source: [ChatGPT thread](https://chatgpt.com/c/6a0160c6-8bf0-83ea-8752-4fb4a85d2469)
