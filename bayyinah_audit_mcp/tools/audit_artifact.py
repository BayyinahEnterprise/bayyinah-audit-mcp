"""bayyinah_audit_artifact tool."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

from bayyinah_audit_mcp.config import load_config, resolve_path
from bayyinah_audit_mcp.sections import lookup_section, normalize_section_ref


class AuditArtifactInput(BaseModel):
    """Input model for bayyinah_audit_artifact."""

    model_config = ConfigDict(extra="forbid")

    artifact_text: str | None = Field(
        default=None,
        description="Inline artifact text to audit.",
    )
    artifact_path: str | None = Field(
        default=None,
        description="Root-relative or absolute artifact path.",
    )
    artifact_name: str | None = Field(
        default=None,
        description="Human-readable artifact name.",
    )
    artifact_kind: str = Field(
        default="document",
        description="Artifact type, such as document, code, invoice, report, or prompt.",
    )
    audit_goal: str = Field(
        default="Run a Bayyinah structural honesty audit.",
        description="Specific audit objective for the calling agent.",
    )
    section_refs: list[str] = Field(
        default_factory=list,
        description="Optional section references to emphasize, such as ['9.1', '14.5'].",
    )
    include_framework_prompt: bool = Field(
        default=True,
        description="Include BAYYINAH_FRAMEWORK_PROMPT text when configured.",
    )
    max_artifact_chars: int = Field(
        default=12000,
        ge=1000,
        le=100000,
        description="Maximum inline artifact characters to include in the prompt scaffold.",
    )


class AuditArtifactOutput(TypedDict):
    status: str
    tool: str
    audit_prompt: str
    framework_prompt_loaded: bool
    artifact_descriptor: str
    section_refs: list[str]
    warnings: list[str]


def _read_text(path: Path, max_chars: int) -> tuple[str, str | None]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", f"Could not read artifact_path '{path}': {exc}"

    if len(text) > max_chars:
        return (
            text[:max_chars],
            f"Artifact text was truncated to {max_chars} characters for prompt size control.",
        )

    return text, None


def _read_framework_prompt(path: Path | None) -> tuple[str, bool, str | None]:
    if path is None:
        return "", False, None

    try:
        text = path.expanduser().read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", False, f"Could not read BAYYINAH_FRAMEWORK_PROMPT '{path}': {exc}"

    return text, True, None


def _section_context(section_refs: list[str]) -> tuple[list[str], str]:
    normalized_refs: list[str] = []
    lines: list[str] = []

    for ref in section_refs:
        normalized = normalize_section_ref(ref)
        normalized_refs.append(normalized)
        found = lookup_section(normalized)
        if found["status"] == "ok":
            lines.append(
                f"- §{found['section_ref']} - {found['title']}: {found['summary']}"
            )
        else:
            lines.append(f"- §{normalized} - not in loaded section index")

    if not lines:
        lines.append("- No section emphasis provided. Use the full Bayyinah audit lens.")

    return normalized_refs, "\n".join(lines)


def bayyinah_audit_artifact(request: AuditArtifactInput) -> AuditArtifactOutput:
    """Return a provider-neutral Bayyinah audit prompt scaffold."""

    config = load_config()
    warnings: list[str] = []
    artifact_body = request.artifact_text or ""
    artifact_source = "inline artifact_text"
    artifact_path_given = bool(request.artifact_path)
    artifact_path_read = False

    if request.artifact_path:
        try:
            path = resolve_path(request.artifact_path, config)
        except ValueError as exc:
            warnings.append(str(exc))
        else:
            artifact_source = str(path)
            artifact_path_read = True
            artifact_body_from_file, warning = _read_text(
                path, request.max_artifact_chars
            )
            if warning:
                warnings.append(warning)
            if artifact_body_from_file:
                artifact_body = artifact_body_from_file
            elif not warning:
                warnings.append(f"artifact_path '{path}' was read but the file was empty.")

    if not artifact_body:
        if not artifact_path_given:
            warnings.append(
                "No artifact_text or artifact_path was provided. "
                "The scaffold still instructs the calling agent how to run the audit."
            )
        elif not artifact_path_read:
            warnings.append(
                "artifact_path was provided but could not be read. "
                "The scaffold still instructs the calling agent how to run the audit."
            )

    framework_text = ""
    framework_loaded = False
    if request.include_framework_prompt:
        framework_text, framework_loaded, framework_warning = _read_framework_prompt(
            config.framework_prompt
        )
        if framework_warning:
            warnings.append(framework_warning)

    normalized_refs, section_context = _section_context(request.section_refs)

    artifact_name = request.artifact_name or artifact_source
    artifact_descriptor = (
        f"name={artifact_name}; kind={request.artifact_kind}; source={artifact_source}"
    )

    framework_block = (
        framework_text
        if framework_loaded
        else "No external framework prompt configured. Use the section context and Bayyinah output contract below."
    )

    artifact_block = (
        artifact_body
        if artifact_body
        else "[Artifact content not embedded. Request it from the MCP client context or inspect artifact_path if available.]"
    )

    audit_prompt = f"""You are acting as a Bayyinah Audit Framework evaluator.

Goal:
{request.audit_goal}

Artifact descriptor:
{artifact_descriptor}

Relevant Bayyinah sections:
{section_context}

Framework prompt / governing instructions:
{framework_block}

Artifact to evaluate:
~~~text
{artifact_block}
~~~

Required audit behavior:
1. Compare visible claims, hidden assumptions, source attributions, section references, and structural consistency.
2. Do not invent evidence. If a needed source or substrate is unavailable, state that explicitly.
3. Use Bayyinah finding format exactly:
   - severity: HIGH | MED | LOW
   - section_ref: string
   - message: concise finding
   - location: artifact location, section, line, page, field, or "global"
4. Separate confirmed findings from cautions and unavailable checks.
5. If no findings are present, return an empty findings list and explain what was checked.
"""

    return {
        "status": "ok",
        "tool": "bayyinah_audit_artifact",
        "audit_prompt": audit_prompt,
        "framework_prompt_loaded": framework_loaded,
        "artifact_descriptor": artifact_descriptor,
        "section_refs": normalized_refs,
        "warnings": warnings,
    }
