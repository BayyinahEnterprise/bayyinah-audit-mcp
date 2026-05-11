"""bayyinah_check_attributions tool."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypedDict

from bayyinah_audit_mcp.config import load_config, resolve_path
from bayyinah_audit_mcp.sections import (
    SECTION_REF_RE,
    load_section_index,
    normalize_section_ref,
)

Severity = Literal["HIGH", "MED", "LOW"]

AUTHOR_YEAR_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-z'’\-]+(?:\s+(?:&|and)\s+[A-Z][A-Za-z'’\-]+|\s+et\s+al\.)?)"
    r"\s*,?\s*\(?(?P<year>(?:19|20)\d{2})\)?",
    flags=re.UNICODE,
)

DATE_WORD_STOPLIST = {
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "SEPT",
    "OCT",
    "NOV",
    "DEC",
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
    "MON",
    "TUE",
    "TUES",
    "WED",
    "THU",
    "THUR",
    "THURS",
    "FRI",
    "SAT",
    "SUN",
}


class CheckAttributionsInput(BaseModel):
    """Input model for bayyinah_check_attributions."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Root-relative or absolute document path.")
    corpus_path: str | None = Field(
        default=None,
        description="Optional JSON/text corpus path for author-year citation resolution.",
    )
    section_refs: list[str] = Field(
        default_factory=list,
        description="Optional explicit section references to check in addition to extracted refs.",
    )
    max_chars: int = Field(
        default=250000,
        ge=1000,
        le=2000000,
        description="Maximum extracted text characters to scan.",
    )


class Finding(TypedDict):
    severity: Severity
    section_ref: str
    message: str
    location: str


class AttributionCheckOutput(BaseModel):
    status: str
    path: str
    checked_section_refs: list[str]
    unresolved_section_refs: list[str]
    checked_citations: list[str]
    unresolved_citations: list[str]
    findings: list[Finding]
    warnings: list[str]
    reason: Optional[str] = None


def _extract_pdf_text(path: Path, max_chars: int) -> tuple[str, str | None]:
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except ImportError:
        return (
            "",
            "pdf extra not installed. Install with: pip install -e '.[pdf]' or pip install pdfplumber",
        )

    try:
        chunks: list[str] = []
        total_chars = 0

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                chunks.append(page_text)
                total_chars += len(page_text)
                if total_chars >= max_chars:
                    break

        return "\n".join(chunks)[:max_chars], None
    except Exception as exc:
        return "", f"Could not extract PDF text from '{path}': {exc}"


def _extract_text(path: Path, max_chars: int) -> tuple[str, str | None]:
    if path.suffix.lower() == ".pdf":
        return _extract_pdf_text(path, max_chars)

    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars], None
    except OSError as exc:
        return "", f"Could not read text from '{path}': {exc}"


def _load_corpus_text(corpus_path: Path | None) -> tuple[str, list[str]]:
    warnings: list[str] = []

    if corpus_path is None:
        return "", warnings

    try:
        raw = corpus_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", [f"Could not read corpus_path '{corpus_path}': {exc}"]

    if not raw.strip():
        return "", [f"corpus_path '{corpus_path}' was read but the file was empty."]

    if corpus_path.suffix.lower() == ".json":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            warnings.append(
                f"corpus_path '{corpus_path}' is not valid JSON ({exc}); falling back to raw text search."
            )
            return raw.lower(), warnings

        return json.dumps(parsed, ensure_ascii=False).lower(), warnings

    return raw.lower(), warnings


def _extract_section_refs(text: str, explicit_refs: list[str]) -> list[str]:
    refs = {normalize_section_ref(ref) for ref in explicit_refs}

    for match in SECTION_REF_RE.finditer(text):
        refs.add(normalize_section_ref(match.group("ref")))

    return sorted(
        refs,
        key=lambda value: tuple(int(part) for part in value.split(".") if part.isdigit()),
    )


def _extract_author_year_citations(text: str) -> list[str]:
    citations: set[str] = set()

    for match in AUTHOR_YEAR_RE.finditer(text):
        author = match.group("author").strip()
        first_token = re.split(r"\s+", author, maxsplit=1)[0].upper().rstrip(".")

        if first_token in DATE_WORD_STOPLIST:
            continue

        citations.add(f"{author} {match.group('year')}")

    return sorted(citations)


def _citation_resolves(citation: str, corpus_text: str) -> bool:
    if not corpus_text:
        return False

    parts = citation.rsplit(" ", 1)
    if len(parts) != 2:
        return False

    author, year = parts
    primary_author = author.replace("et al.", "").split("&")[0].split(" and ")[0].strip()
    return primary_author.lower() in corpus_text and year in corpus_text


def bayyinah_check_attributions(
    request: CheckAttributionsInput,
) -> AttributionCheckOutput:
    """Check section references and author-year citations against local indexes."""

    config = load_config()
    warnings: list[str] = []

    try:
        path = resolve_path(request.path, config)
    except ValueError as exc:
        return AttributionCheckOutput(
            status="error",
            path=request.path,
            checked_section_refs=[],
            unresolved_section_refs=[],
            checked_citations=[],
            unresolved_citations=[],
            findings=[],
            warnings=[],
            reason=str(exc),
        )

    text, extraction_error = _extract_text(path, request.max_chars)

    if extraction_error:
        return AttributionCheckOutput(
            status="error",
            path=str(path),
            checked_section_refs=[],
            unresolved_section_refs=[],
            checked_citations=[],
            unresolved_citations=[],
            findings=[],
            warnings=[],
            reason=extraction_error,
        )

    section_index = load_section_index(config)
    checked_section_refs = _extract_section_refs(text, request.section_refs)
    unresolved_section_refs = [
        ref for ref in checked_section_refs if ref not in section_index
    ]

    try:
        corpus_path = (
            resolve_path(request.corpus_path, config) if request.corpus_path else None
        )
    except ValueError as exc:
        return AttributionCheckOutput(
            status="error",
            path=str(path),
            checked_section_refs=checked_section_refs,
            unresolved_section_refs=unresolved_section_refs,
            checked_citations=[],
            unresolved_citations=[],
            findings=[],
            warnings=[],
            reason=str(exc),
        )

    corpus_text, corpus_warnings = _load_corpus_text(corpus_path)
    warnings.extend(corpus_warnings)

    checked_citations = _extract_author_year_citations(text)
    unresolved_citations: list[str] = []

    if corpus_path is not None and corpus_text:
        unresolved_citations = [
            citation
            for citation in checked_citations
            if not _citation_resolves(citation, corpus_text)
        ]

    findings: list[Finding] = []

    for ref in unresolved_section_refs:
        findings.append(
            {
                "severity": "MED",
                "section_ref": "14.5",
                "message": f"Section reference §{ref} does not resolve against the loaded section index.",
                "location": f"{path.name}: section reference §{ref}",
            }
        )

    for citation in unresolved_citations:
        findings.append(
            {
                "severity": "MED",
                "section_ref": "14.5",
                "message": f"Author-year citation '{citation}' was not resolved against the provided corpus.",
                "location": f"{path.name}: citation {citation}",
            }
        )

    if findings:
        status = "completed_with_findings"
    elif warnings:
        status = "ok_with_warnings"
    else:
        status = "ok"

    return AttributionCheckOutput(
        status=status,
        path=str(path),
        checked_section_refs=checked_section_refs,
        unresolved_section_refs=unresolved_section_refs,
        checked_citations=checked_citations,
        unresolved_citations=unresolved_citations,
        findings=findings,
        warnings=warnings,
    )
