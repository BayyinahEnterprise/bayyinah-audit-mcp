"""bayyinah_list_sections tool."""

from __future__ import annotations

from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field

from bayyinah_audit_mcp.sections import list_sections


class ListSectionsInput(BaseModel):
    """Input model for bayyinah_list_sections."""

    model_config = ConfigDict(extra="forbid")

    include_summaries: bool = Field(
        default=True,
        description="Include section summaries in the returned index.",
    )


class ListedSection(TypedDict):
    section_ref: str
    label: str
    title: str
    summary: str


class ListSectionsOutput(TypedDict):
    status: str
    count: int
    sections: list[ListedSection]


def bayyinah_list_sections(request: ListSectionsInput) -> ListSectionsOutput:
    """Return the loaded Bayyinah section index."""

    raw_sections = list_sections()
    sections: list[ListedSection] = []

    for item in raw_sections:
        sections.append(
            {
                "section_ref": item["section_ref"],
                "label": item["label"],
                "title": item.get("title", ""),
                "summary": item.get("summary", "") if request.include_summaries else "",
            }
        )

    return {
        "status": "ok",
        "count": len(sections),
        "sections": sections,
    }