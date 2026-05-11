"""FastMCP server wiring for the Bayyinah Audit MCP server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from bayyinah_audit_mcp.tools.audit_artifact import bayyinah_audit_artifact
from bayyinah_audit_mcp.tools.check_attributions import bayyinah_check_attributions
from bayyinah_audit_mcp.tools.cross_vendor_audit import bayyinah_cross_vendor_audit
from bayyinah_audit_mcp.tools.furqan_lint import bayyinah_run_furqan_lint
from bayyinah_audit_mcp.tools.generate_round_report import (
    bayyinah_generate_round_report,
)
from bayyinah_audit_mcp.tools.list_sections import bayyinah_list_sections
from bayyinah_audit_mcp.tools.lookup_section import bayyinah_lookup_section

SERVER_NAME = "bayyinah-audit-mcp"

TOOL_REGISTRY: tuple[tuple[str, Callable[..., Any]], ...] = (
    ("bayyinah_audit_artifact", bayyinah_audit_artifact),
    ("bayyinah_run_furqan_lint", bayyinah_run_furqan_lint),
    ("bayyinah_check_attributions", bayyinah_check_attributions),
    ("bayyinah_cross_vendor_audit", bayyinah_cross_vendor_audit),
    ("bayyinah_lookup_section", bayyinah_lookup_section),
    ("bayyinah_list_sections", bayyinah_list_sections),
    ("bayyinah_generate_round_report", bayyinah_generate_round_report),
)

TOOL_NAMES: tuple[str, ...] = tuple(name for name, _ in TOOL_REGISTRY)


def _new_fastmcp(host: str, port: int) -> FastMCP:
    """Create a FastMCP instance while tolerating minor SDK constructor drift."""

    try:
        return FastMCP(SERVER_NAME, host=host, port=port)
    except TypeError:
        try:
            return FastMCP(SERVER_NAME, port=port)
        except TypeError:
            return FastMCP(SERVER_NAME)


def create_mcp(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Create and register a fresh Bayyinah Audit MCP server."""

    mcp = _new_fastmcp(host=host, port=port)

    for name, func in TOOL_REGISTRY:
        mcp.tool(name=name)(func)

    return mcp
