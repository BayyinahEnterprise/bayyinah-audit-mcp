"""bayyinah_generate_round_report tool."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Literal
from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field

from bayyinah_audit_mcp.config import load_config, severity_blocks

Severity = Literal["HIGH", "MED", "LOW"]


class FindingInput(BaseModel):
    """Bayyinah finding format."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity = Field(description="Finding severity: HIGH, MED, or LOW.")
    section_ref: str = Field(description="Bayyinah section reference.")
    message: str = Field(description="Concise finding message.")
    location: str = Field(description="Artifact location, page, line, field, or global.")


class GenerateRoundReportInput(BaseModel):
    """Input model for bayyinah_generate_round_report."""

    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(default=1, ge=1, description="Round number.")
    findings: list[FindingInput] = Field(
        default_factory=list,
        description="Findings in Bayyinah finding format.",
    )
    artifact_name: str = Field(default="artifact", description="Audited artifact name.")
    auditor: str = Field(default="Bayyinah Audit MCP", description="Auditor label.")
    title: str = Field(default="Bayyinah Audit Round Report", description="Report title.")
    severity_threshold: Severity | None = Field(
        default=None,
        description="Override BAYYINAH_SEVERITY_THRESHOLD for blocked status.",
    )
    include_empty_sections: bool = Field(
        default=True,
        description="Include empty report sections when no findings are present.",
    )


class ReportCounts(TypedDict):
    HIGH: int
    MED: int
    LOW: int
    TOTAL: int


class GenerateRoundReportOutput(TypedDict):
    status: str
    blocked: bool
    threshold: str
    counts: ReportCounts
    report: str


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _counts(findings: list[FindingInput]) -> ReportCounts:
    counter = Counter(finding.severity for finding in findings)
    return {
        "HIGH": counter.get("HIGH", 0),
        "MED": counter.get("MED", 0),
        "LOW": counter.get("LOW", 0),
        "TOTAL": len(findings),
    }


def _decision(blocked: bool, findings: list[FindingInput]) -> str:
    if blocked:
        return "BLOCKED - One or more findings meet or exceed the configured severity threshold."
    if findings:
        return "PASS WITH FINDINGS - Findings are present below the configured block threshold."
    return "PASS - No findings were supplied for this round."


def _findings_table(findings: list[FindingInput]) -> str:
    if not findings:
        return "No findings reported."

    lines = [
        "| # | Severity | Section | Location | Message |",
        "|---:|---|---|---|---|",
    ]

    severity_order = {"HIGH": 0, "MED": 1, "LOW": 2}
    sorted_findings = sorted(
        enumerate(findings, start=1),
        key=lambda pair: (severity_order[pair[1].severity], pair[0]),
    )

    for idx, finding in sorted_findings:
        lines.append(
            "| "
            f"{idx} | "
            f"{finding.severity} | "
            f"§{_escape_cell(finding.section_ref.lstrip('§'))} | "
            f"{_escape_cell(finding.location)} | "
            f"{_escape_cell(finding.message)} |"
        )

    return "\n".join(lines)


def bayyinah_generate_round_report(
    request: GenerateRoundReportInput,
) -> GenerateRoundReportOutput:
    """Render findings into a canonical Bayyinah Round-N report."""

    config = load_config()
    threshold = request.severity_threshold or config.severity_threshold
    blocked = any(severity_blocks(finding.severity, threshold) for finding in request.findings)
    counts = _counts(request.findings)
    generated_at = datetime.now(timezone.utc).isoformat()

    sections: list[str] = [
        f"# {request.title}",
        "",
        f"**Round:** {request.round_number}",
        f"**Artifact:** {request.artifact_name}",
        f"**Auditor:** {request.auditor}",
        f"**Generated:** {generated_at}",
        f"**Severity threshold:** {threshold}",
        "",
        "## Decision",
        "",
        _decision(blocked, request.findings),
        "",
        "## Counts",
        "",
        f"- HIGH: {counts['HIGH']}",
        f"- MED: {counts['MED']}",
        f"- LOW: {counts['LOW']}",
        f"- TOTAL: {counts['TOTAL']}",
        "",
        "## Findings",
        "",
        _findings_table(request.findings),
    ]

    if request.include_empty_sections or request.findings:
        sections.extend(
            [
                "",
                "## Required Remediation",
                "",
                (
                    "Resolve all blocking findings and rerun the round."
                    if blocked
                    else "No blocking remediation required at the configured threshold."
                ),
                "",
                "## Audit Contract",
                "",
                "Findings use Bayyinah format: `{severity, section_ref, message, location}`.",
            ]
        )

    report = "\n".join(sections)
    status = "blocked" if blocked else "ok"

    return {
        "status": status,
        "blocked": blocked,
        "threshold": threshold,
        "counts": counts,
        "report": report,
    }