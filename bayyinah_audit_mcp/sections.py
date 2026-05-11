"""Section index loading and lookup helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict

from bayyinah_audit_mcp.config import BayyinahConfig, load_config, resolve_path


class SectionEntry(TypedDict):
    title: str
    summary: str


class SectionLookup(TypedDict, total=False):
    status: str
    requested_ref: str
    section_ref: str
    label: str
    title: str
    summary: str
    reason: str


SECTION_REF_RE = re.compile(
    r"(?:§\s*|section\s+)?(?P<ref>\d+(?:\.\d+)+)",
    flags=re.IGNORECASE,
)


def bundled_section_index_path() -> Path:
    return Path(__file__).parent / "data" / "section_index.json"


def normalize_section_ref(value: str) -> str:
    """Normalize values like '§9.1', 'Section 9.1', and '9.1' to '9.1'."""

    match = SECTION_REF_RE.search(value.strip())
    if not match:
        return value.strip().lstrip("§").strip()
    return match.group("ref")


def _section_sort_key(section_ref: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in section_ref.split("."))
    except ValueError:
        return (999999,)


@lru_cache(maxsize=16)
def _load_section_index_from_path(path_string: str) -> dict[str, SectionEntry]:
    path = Path(path_string)

    with path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = json.load(handle)

    normalized: dict[str, SectionEntry] = {}
    for key, value in raw.items():
        ref = normalize_section_ref(key)
        title = str(value.get("title", "")).strip()
        summary = str(value.get("summary", "")).strip()
        normalized[ref] = {"title": title, "summary": summary}

    return normalized


def load_section_index(config: BayyinahConfig | None = None) -> dict[str, SectionEntry]:
    """Load the configured or bundled section index.

    The parsed JSON is cached by resolved path to avoid repeated disk reads
    during multi-section tool calls.
    """

    cfg = config or load_config()
    if cfg.section_index is not None:
        path = resolve_path(cfg.section_index, cfg)
    else:
        path = bundled_section_index_path().resolve()

    return dict(_load_section_index_from_path(str(path)))


def lookup_section(
    section_ref: str,
    config: BayyinahConfig | None = None,
) -> SectionLookup:
    """Look up a section by reference."""

    requested = section_ref
    normalized_ref = normalize_section_ref(section_ref)
    index = load_section_index(config)

    if normalized_ref not in index:
        return {
            "status": "not_found",
            "requested_ref": requested,
            "section_ref": normalized_ref,
            "label": f"§{normalized_ref}",
            "reason": "Section reference is not in the loaded Bayyinah section index.",
        }

    entry = index[normalized_ref]
    return {
        "status": "ok",
        "requested_ref": requested,
        "section_ref": normalized_ref,
        "label": f"§{normalized_ref}",
        "title": entry["title"],
        "summary": entry["summary"],
    }


def list_sections(config: BayyinahConfig | None = None) -> list[SectionLookup]:
    """Return the full section index in numeric section order."""

    index = load_section_index(config)
    sections: list[SectionLookup] = []

    for ref in sorted(index.keys(), key=_section_sort_key):
        entry = index[ref]
        sections.append(
            {
                "status": "ok",
                "requested_ref": ref,
                "section_ref": ref,
                "label": f"§{ref}",
                "title": entry["title"],
                "summary": entry["summary"],
            }
        )

    return sections
