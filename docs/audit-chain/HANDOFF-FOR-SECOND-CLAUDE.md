# Handoff: independent code review of Bayyinah Audit MCP Server v0.1

You're a second Claude instance. The first Claude (in another Cowork window) drove ChatGPT to produce this MCP server, applied three local patches, and confirmed all seven tools register and respond. This package is for you to do an independent review against the spec.

## Your job

Read the spec (`Bayyinah-MCP-Server-Setup-Guide.docx` - Pat will paste the text or attach the file). Read the code in this folder. Produce a written review that answers, for each of the seven tools and the project scaffolding:

1. Does the implementation match the spec contract? (Inputs, outputs, error envelopes, env-var behaviour, lazy-import pattern.)
2. Are there obvious bugs or missing edge cases the smoke test wouldn't catch?
3. Are there security or correctness issues? (Subprocess, file paths, network calls, logging of secrets.)
4. Are there code-style or architectural drift items worth surfacing?

Don't try to fix things in code; produce a markdown review as `REVIEW-V1.md` in this folder. The first Claude will turn your findings into a follow-up prompt for ChatGPT.

## Constraints to verify particularly

- **Stateless.** No global mutable state outside import-time config. Walk for `_` / `global` / module-level mutation.
- **Provider-neutral.** `bayyinah_audit_artifact` returns a prompt envelope; it must NOT call any LLM API itself. The only tool that touches LLM keys is `bayyinah_cross_vendor_audit`, and only at invocation time.
- **No secret logging.** Search for any path where API keys, env values, or file contents could land in stderr/stdout/log records.
- **Lazy imports.** `cross_vendor_audit` should import `bayyinah_audit_orchestrator` only inside the tool function, not at module top. `check_attributions` should import `pdfplumber` only when a `.pdf` path is passed.
- **Path safety.** `BAYYINAH_AUDIT_ROOT` is the base for relative paths. Verify path resolution doesn't allow escape (e.g. `../../etc/passwd`) or symlink confusion.
- **Section-ref normalisation.** `§9.1`, `9.1`, and `Section 9.1` must all hit the same record. Five seeded sections only: 5.2, 9.1, 14.5, 18.10, 23.3. Anything else returns `not_found`.

## Already-known issues (no need to re-flag)

These three are already documented in `PATCHES.md` and queued for the next ChatGPT round:

1. `audit_artifact.py` had a triple-backtick fence inside an f-string (caused truncation in extraction).
2. `NotRequired` inside `TypedDict` broke MCP tool registration.
3. `typing.TypedDict` not accepted by Pydantic 2.13 on Python <3.12.

If you find more, add them.

## What to ignore

- **The `bayyinah-audit-mcp/` extras vs the v3 framework's own code.** You're not auditing the Bayyinah framework - just this MCP server that wraps it. Section content quality, framework section numbering, etc. are out of scope.
- **Style nits unless they suggest a bug.** Don't bikeshed naming, comment density, or import order. Surface only items that affect correctness, security, or maintainability.

## Scope and length

Keep your review under 1,500 words. Section it by file. End with a punch list of "must fix before publishing" vs "nice to have."

## Pointers

- Spec: `Bayyinah-MCP-Server-Setup-Guide.docx` (Pat will provide).
- ChatGPT conversation that produced the code: `https://chatgpt.com/c/6a014a3f-8a00-83ea-a20a-196587e109a9`.
- Local patches applied: see `PATCHES.md` in this folder.
- All code lives under this folder (`bayyinah-audit-mcp/`); shell out and grep freely.
- Smoke test that passes: `tests/test_smoke.py::test_imports_and_registers_all_tools`.

When you finish the review, tell Pat: "Review written to `bayyinah-audit-mcp/REVIEW-V1.md` - hand to the other Claude for the next ChatGPT round." That's all you need to do.
