# Bayyinah Audit MCP Server

[![CI](https://github.com/BayyinahEnterprise/bayyinah-audit-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/BayyinahEnterprise/bayyinah-audit-mcp/actions/workflows/ci.yml)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm_Noncommercial_1.0.0-orange.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the **Bayyinah Audit Framework** as seven structured tools any MCP-compatible client (Claude Desktop, Cline, Continue, etc.) can call.

This is **Lane 4** of the four-lane Bayyinah audit substrate. The server is a thin wiring layer over substrate held in `data/section_index.json` and over an external lane-3 orchestrator that the operator brings.

## Tools exposed

| Tool | Purpose |
|---|---|
| `bayyinah_audit_artifact` | Audit a single artifact (file path) against the framework |
| `bayyinah_run_furqan_lint` | Invoke the `furqan-lint` CLI on a target tree |
| `bayyinah_check_attributions` | Validate citation / attribution integrity in a document |
| `bayyinah_cross_vendor_audit` | Run multi-vendor model consensus audit (lane 3 contract) |
| `bayyinah_lookup_section` | Look up a section by its identifier (e.g. `9.1`, `14.5`) |
| `bayyinah_list_sections` | Enumerate all available framework sections |
| `bayyinah_generate_round_report` | Produce a structured audit round report |

## For consumers

Bring your own lane-3 implementation. The wrapper expects `bayyinah_audit_orchestrator.run_cross_vendor_audit(**payload)` (or another compatible callable in that module) to return a dict, a `Consensus` object, or an error envelope.

The bundled `section_index.json` contains a placeholder five-entry sample (`5.2`, `9.1`, `14.5`, `18.10`, `23.3`); point `BAYYINAH_SECTION_INDEX` at your full framework index for production use.

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
pip install -e ".[pdf]"          # PDF attribution checks
pip install -e ".[cross-vendor]" # multi-vendor LLM consensus
```

## Run

Default stdio transport (for desktop MCP clients):

```bash
python -m bayyinah_audit_mcp
```

SSE transport:

```bash
python -m bayyinah_audit_mcp --transport sse --port 8000
```

Streamable HTTP transport:

```bash
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

## Develop

```bash
pip install -e ".[all]"
pip install pytest
pytest
```

CI runs the matrix `{3.10, 3.11, 3.12, 3.13}` on every push and pull request.

## Audit-chain record

The `docs/audit-chain/` directory contains the six-round cross-instance review record (`REVIEW-V1.md` through `REVIEW-V6.md`), patch ledger (`PATCHES.md`), substrate reconciliation notes, and handoff documents that produced this v0.5.5 release candidate. Preserved per Bayyinah Audit Framework §14.5 immutability discipline.

## Status

**v0.5.5** -- release candidate. Lane 4 of the four-lane Bayyinah audit substrate. 43 tests passing across the cross-vendor audit cycle-guard (`F-V05-DICT-CYCLE-LOOP` closed in v0.5.5), tool registration, section lookup, and attribution checks.

The v1.0.0 cut follows the publish checklist in the release notes after the Sonar gate and one more cross-instance pass.

## License

[PolyForm Noncommercial License 1.0.0](LICENSE).

You may use, copy, modify, and share this software for any non-commercial purpose -- research, evaluation, personal projects, and internal review at a company. Commercial use requires a separate license; contact the author below.

Required Notice: Copyright (c) 2026 Bilal Syed Arfeen / BayyinahEnterprise.

## Authorship

Bilal Syed Arfeen (BayyinahEnterprise)
