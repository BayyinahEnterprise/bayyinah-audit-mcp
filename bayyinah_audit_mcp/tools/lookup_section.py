"""bayyinah_lookup_section tool."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bayyinah_audit_mcp.sections import lookup_section


class LookupSectionInput(BaseModel):
    """Input model for bayyinah_lookup_section."""

    model_config = ConfigDict(extra="forbid")

    section_ref: str = Field(
        description="Section reference, such as '9.1', '§9.1', or 'Section 9.1'."
    )


class LookupSectionOutput(BaseModel):
    status: str
    requested_ref: str
    section_ref: str
    label: str
    title: Optional[str] = None
    summary: Optional[str] = None
    reason: Optional[str] = None


def bayyinah_lookup_section(request: LookupSectionInput) -> LookupSectionOutput:
    """Look up a Bayyinah Framework section by reference."""

    result = lookup_section(request.section_ref)
    return LookupSectionOutput(**result)
