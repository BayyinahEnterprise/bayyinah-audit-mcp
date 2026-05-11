"""Smoke tests for Bayyinah Audit MCP server registration."""

from __future__ import annotations

import asyncio

from bayyinah_audit_mcp.server import TOOL_NAMES, create_mcp


def test_fastmcp_registers_all_public_tools() -> None:
    mcp = create_mcp()
    tools = asyncio.run(mcp.list_tools())
    registered_names = {tool.name for tool in tools}

    assert set(TOOL_NAMES) == registered_names
    assert registered_names == {
        "bayyinah_audit_artifact",
        "bayyinah_run_furqan_lint",
        "bayyinah_check_attributions",
        "bayyinah_cross_vendor_audit",
        "bayyinah_lookup_section",
        "bayyinah_list_sections",
        "bayyinah_generate_round_report",
    }
