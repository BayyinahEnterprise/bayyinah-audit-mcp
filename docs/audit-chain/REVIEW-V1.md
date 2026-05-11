# REVIEW-V1: independent code review of Bayyinah Audit MCP Server v0.1.0

Reviewer: second Claude instance.
Scope: spec (`Bayyinah-MCP-Server-Setup-Guide.docx`) versus code under `bayyinah_audit_mcp/`.
Known-fixed in `PATCHES.md` (P1-P3) not re-flagged.

---

## `bayyinah_audit_mcp/server.py`

**Bug (stateless violation).** Line 58 calls `mcp = create_mcp()` at module import. The handoff calls out "no global mutable state outside import-time config"; a FastMCP instance is mutable global state. It is also wasteful: `__main__.main()` constructs a second instance with the user-supplied host/port, and `test_smoke` constructs a third. Any side effects of FastMCP construction (logger handlers, signal hooks, port binding intent) run at import time for every consumer that simply imports `server`. Drop line 58; let callers invoke `create_mcp()` explicitly.

**Minor.** `_new_fastmcp` swallows `TypeError` to absorb SDK constructor drift; an unrelated `TypeError` from our own kwargs would also silently fall back. Annotate the SDK range it covers.

## `bayyinah_audit_mcp/__main__.py`

Argparse contract matches the spec ("stdio", "sse", "streamable-http"). Inherits the import-time side effect from `server.py`.

## `bayyinah_audit_mcp/config.py`

**Security (path escape).** `resolve_path` calls `Path(...).expanduser().resolve()` and accepts both absolute paths and `..`-relative paths. There is no check that the resolved path stays under `audit_root`. The docstring explicitly permits absolute paths, but the handoff asks us to "verify path resolution doesn't allow escape (e.g. `../../etc/passwd`) or symlink confusion." Today, an MCP client can pass `path: "/etc/passwd"` to `check_attributions` or `audit_artifact` and the server happily reads it. For stdio on a single trusted user this is acceptable; for the SSE/HTTP transport the README and spec advertise, it is an arbitrary-local-file-read primitive. `.resolve()` also follows symlinks, so a symlink inside `audit_root` pointing out is followed silently. Recommend: optional `BAYYINAH_PATH_STRICT=1` that enforces `resolved.is_relative_to(audit_root)` (default off for back-compat; document as required for any remote transport).

**Minor.** `_severity` silently coerces unknown values to `"MED"`. Surface a warning in the loader rather than fail-quiet so users discover typos.

## `bayyinah_audit_mcp/sections.py`

Section-ref normalisation matches the spec: `§9.1`, `9.1`, and `Section 9.1` all reduce to `9.1`. Five seeded sections (5.2, 9.1, 14.5, 18.10, 23.3) match the spec.

**Perf.** Every `lookup_section()` / `list_sections()` call re-reads and re-parses `section_index.json`. With the bundled index this is cheap, but `bayyinah_audit_artifact` calls `lookup_section` once per `section_refs` entry, so a single audit prompt with five refs does five JSON loads. Cache the parsed index per resolved path; invalidate on env change.

**Edge case.** `_section_sort_key` returns `(999999,)` on `ValueError`. If a custom index has a key like "9.1a", normalisation will keep "9.1" (regex matches), so this rarely fires. Acceptable.

## `bayyinah_audit_mcp/tools/list_sections.py`

Matches contract. No issues.

## `bayyinah_audit_mcp/tools/lookup_section.py`

Matches contract. The `# type: ignore[return-value]` is a smell-symptom of returning the underlying `SectionLookup` TypedDict through a tool-specific TypedDict that does not declare the same shape; harmless functionally.

## `bayyinah_audit_mcp/tools/audit_artifact.py`

**Provider neutrality.** Confirmed: this tool returns a prompt envelope; it never imports any LLM client. ✓

**Bug (empty-file warning is misleading).** If `artifact_path` resolves but `_read_text` returns an empty body, the code falls back to `request.artifact_text` (often `None`), then warns "No artifact_text or readable artifact_path content was provided." The user did supply a path. Surface a distinct "path read, file empty" warning.

**Minor (path safety).** Inherits the `resolve_path` issue; file contents land inside `audit_prompt`, so this is a primary leak vector.

P1 fence fix in place.

## `bayyinah_audit_mcp/tools/check_attributions.py`

**Lazy import.** `pdfplumber` is imported inside `_extract_pdf_text` only when a `.pdf` path is passed. ✓

**Bug (silent corpus failure).** `_load_corpus_text` returns `""` on `OSError`. Downstream, every citation reads as unresolved - indistinguishable from "citations are bad." Carry the error string through to the output envelope.

**Bug (false positives on month-year).** `AUTHOR_YEAR_RE` matches any capitalised token followed by a four-digit year, so "December 2024" and any "<Word> 2025" in prose register as citations. Add a stop-list (months/weekdays) or require parenthesised `(Author, YYYY)`.

**Minor.** All synthetic findings hardcode `section_ref: "14.5"`. Defensible (attribution = §14.5), but if §14.5 is itself the unresolved ref, the resulting finding is mildly tautological.

**Path safety.** Same as `audit_artifact`. PDFs at arbitrary paths can be ingested and their text reflected back.

## `bayyinah_audit_mcp/tools/furqan_lint.py`

**Subprocess.** Uses `subprocess.run(list, shell=False, check=False)` with `shlex.split` for the configured command. Safe from shell injection. ✓

**Bug (status mislabelled).** When `completed.returncode != 0` and the parser extracts no findings (e.g. furqan-lint crashed and only emitted a stack trace to stderr), the code falls through to `status = "completed_with_findings"` with an empty findings list. Mislabel - it should be `"error"` (or surface `returncode` + `stderr` more loudly). Add a branch: `if completed.returncode != 0 and not findings: status = "error"`.

**Security (extra_args pass-through).** `extra_args` is appended unchecked. Low risk on stdio, higher on SSE. Whitelist flags or document `extra_args` as trusted input.

**Info leak.** Raw `stdout`/`stderr` flow back to the client; lint tools sometimes echo file contents. Truncate at a configurable cap.

## `bayyinah_audit_mcp/tools/cross_vendor_audit.py`

**Lazy import.** `bayyinah_audit_orchestrator` imported inside the function. ✓ Returns `"unavailable"` envelope when missing.

**Provider neutrality at server boundary.** The tool itself does not call any LLM; it delegates. ✓ Keys are read at invocation only. ✓

**Secret leakage risk (medium).**
1. `payload["api_keys"]` passes raw key VALUES to the orchestrator. Consider letting lane #3 read its own env instead.
2. The exception handler returns `f"... raised {type(exc).__name__}: {exc}"`. If the orchestrator raises `ValueError(payload)` (or wraps the payload in its message), the secret values land in the MCP response. Return only `type(exc).__name__` and a generic reason; log full `repr(exc)` server-side.
3. `raw_result: result` echoes whatever lane #3 returns. If lane #3 ever includes the key dict or auth headers in its result, the secrets travel back. Use an allowlist normaliser instead of echoing.

**Minor (consistency).** This is the only `async def` tool in the project. The MCP SDK accepts both, but mixing makes testability and stubbing awkward. PATCHES.md already flags this.

## `bayyinah_audit_mcp/tools/generate_round_report.py`

Matches contract. `severity_blocks` math is correct (LOW < MED < HIGH). Markdown rendering escapes pipes and newlines in cells. `severity_threshold` override works.

**Minor.** `_decision`'s "PASS - No findings were supplied" runs when the caller passes an empty list. Consider an input flag distinguishing "no findings checked" from "findings checked, none found."

## `pyproject.toml`

Per PATCHES.md, add `typing_extensions>=4.7` as an explicit dependency. The package now imports it directly across every tool module; relying on transitive resolution from pydantic is fragile.

`requires-python = ">=3.11"` is conservative now that `typing_extensions.TypedDict` is used everywhere - the code runs on 3.10 (the `__pycache__` dirs in this checkout are 3.10). Either lower the floor and add CI for 3.10, or annotate why 3.11 is required.

## `tests/test_smoke.py`

Asserts only registration. The lack of a `lookup_section("§9.1") == lookup_section("Section 9.1")` test is a gap given normalisation is a named spec requirement. Introspection of `_tool_manager._tools` couples to FastMCP internals.

## `data/section_index.json`

Five seeded entries match the spec. Content quality out of scope per the brief.

---

## Punch list

### Must fix before publishing

1. **`server.py:58`** - delete the module-level `mcp = create_mcp()`. Violates the stateless contract and creates a stray FastMCP at import.
2. **`config.py:resolve_path`** - add a containment guard (e.g. `BAYYINAH_PATH_STRICT`) and document that SSE/HTTP transport requires it. Today the server reads arbitrary local files for any MCP client.
3. **`cross_vendor_audit.py`** - scrub the exception path and `raw_result` echo so API key values cannot leak back to the MCP client.
4. **`furqan_lint.py`** - fix the status mislabel when `returncode != 0` and findings are empty; return `"error"`, not `"completed_with_findings"`.
5. **`pyproject.toml`** - add `typing_extensions>=4.7` as an explicit dependency.

### Nice to have

1. Replace TypedDict outputs with Pydantic models (the P2 contract loosening goes away).
2. Make all tools sync (per PATCHES.md item).
3. Cache `load_section_index()` per process.
4. Add stop-list to `AUTHOR_YEAR_RE` to drop month/weekday false positives.
5. Surface corpus-load failures as warnings in `check_attributions` output.
6. Whitelist or document `furqan_lint.extra_args`; truncate stdout/stderr in the response envelope.
7. Distinguish "path read, file empty" from "no artifact supplied" in `audit_artifact` warnings.
8. Add per-tool functional pytest cases (especially section-ref normalisation and threshold gating).
9. Lower `requires-python` to 3.10 with CI, or document why 3.11 is the floor.
10. Replace test introspection of `_tool_manager._tools` with the SDK's public list-tools path once it stabilises.
