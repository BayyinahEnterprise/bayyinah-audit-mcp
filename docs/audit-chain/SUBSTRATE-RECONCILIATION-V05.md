# Substrate-of-record reconciliation: V04-READY versus v0.5 actual state

Reconciler: third Claude instance (driving from Cowork on 2026-05-10).
Trigger: user asked for a continuation session against ChatGPT. Pre-flight T00 substrate check (Bayyinah Audit Framework v3.0 standing rule 5, "Substrate-of-record uniqueness") surfaced drift between the V04-READY marker and the workspace files. ChatGPT session deferred until reconciliation lands.

## Substrate timeline reconstructed from mtimes

All timestamps UTC, all dates 2026-05-11:

- 03:47:34  `HANDOFF-FOR-SECOND-CLAUDE.md` written (first Claude → second Claude).
- 03:55:12  `REVIEW-V1.md` written (second Claude's v0.1 review).
- 04:17:17  `pyproject.toml` last touched (v0.4 round, `requires-python = ">=3.10"`).
- 04:17:17  `tests/test_smoke.py` last touched (v0.4 rewrite to `mcp.list_tools()`).
- 04:19:37  `V04-READY.txt` written (marker for v0.4, lists 5 deferred items).
- 04:32:13  `bayyinah_audit_mcp/__init__.py` bumped to 0.5.0.
- 04:32:13  `tests/test_tools.py` rewritten with v0.5 tests.
- 04:32:14  `PATCHES.md` updated with v0.5 narrative (lines 189-215).

The V04-READY marker is therefore an artifact of the v0.4 → v0.5 transition. v0.5 patch work landed roughly 13 minutes after the marker was dropped. V04-READY was never archived or annotated, so reading it cold gives a stale picture.

## Findings

### Finding F-V05-RECON-001 [LOW] -- pyproject.toml version lagged __init__.py

- ID: F-V05-RECON-001
- Severity: LOW
- Locus: `pyproject.toml` line 7
- Substance: After the v0.5 patch round, `bayyinah_audit_mcp/__init__.py` was bumped from `"0.4.0"` to `"0.5.0"`, but `pyproject.toml` still carried `version = "0.4.0"`. The two-source-of-truth pattern (PEP 621 `project.version` and package `__version__`) drifted by one minor release.
- Disposition: Closed in this reconciliation. `pyproject.toml` line 7 edited from `"0.4.0"` to `"0.5.0"`. `pytest tests/` reruns clean at 14/14 on Python 3.10.12.
- Cross-reference: PATCHES.md v0.5 section (lines 189-215) names the v0.5 round but does not list the pyproject.toml bump in its "Files added or changed" list; that was the visible drift signal.

### Finding F-V05-RECON-002 [LOW] -- V04-READY.txt is stale but preserved per audit-chain immutability

- ID: F-V05-RECON-002
- Severity: LOW
- Locus: `V04-READY.txt`
- Substance: V04-READY.txt claims "8/8 pytest pass" and lists 5 priority items for the next round. After v0.5, the workspace has 14/14 passing and three of the five items are closed in code (canary-string assertions, empty-file warning test, three-way check_attributions split). A naive reader of V04-READY in isolation would assume those items are still open and could re-invoke an LLM producer to redo work that already shipped.
- Disposition: Not edited. Audit-chain immutability (Bayyinah Audit Framework v3.0 §14.5) forbids retroactive modification of preservation cells. This reconciliation document supersedes V04-READY as the canonical state-of-record for the v0.4 → v0.5 transition.
- Cross-reference: V04-READY.txt; PATCHES.md v0.5 (lines 189-215); this file.

### Finding F-V05-RECON-003 [LOW] -- V04-READY item #5 (PyPI 3.10 wheel availability) verified clean

- ID: F-V05-RECON-003
- Severity: LOW
- Locus: `pyproject.toml` `[project.optional-dependencies]` block (lines 21-36)
- Substance: V04-READY item #5 asked whether the four optional-extras pins (`anthropic>=0.54`, `openai>=1.80`, `google-genai>=1.20`, `pdfplumber>=0.11`) all have Python 3.10-compatible wheels on PyPI. v0.5 deferred this to first failing CI run. Direct PyPI metadata query (2026-05-10) shows: anthropic latest 0.100.0 requires_python>=3.9 with 58 releases at-or-above floor carrying py3.10-compatible files; openai latest 2.36.0 requires_python>=3.9 with 103 such releases; google-genai latest 2.0.1 requires_python>=3.10 with 62 such releases; pdfplumber latest 0.11.9 requires_python>=3.8 with 10 such releases. All four resolve cleanly on 3.10.
- Disposition: Verified clean. No pyproject.toml change required.
- Cross-reference: V04-READY.txt item 5; PATCHES.md v0.5 "Deferred per cost analysis" note.

### Finding F-V05-RECON-004 [LOW] -- V04-READY item #3 (asyncio.run across 3.10-3.13) reasoned clean

- ID: F-V05-RECON-004
- Severity: LOW
- Locus: `tests/test_smoke.py` lines 11-15
- Substance: V04-READY item #3 asked whether `asyncio.run(mcp.list_tools())` inside a sync pytest function plays nicely across the CI matrix (3.10 / 3.11 / 3.12 / 3.13). `asyncio.run()` creates a fresh event loop, runs the coroutine, and closes the loop; it does not call `asyncio.get_event_loop()`, so the "no current event loop" DeprecationWarning that fires on 3.12+ when an unbound loop is requested does not apply here. Any 3.12+ deprecation noise would have to originate inside the MCP SDK's own `list_tools()` implementation, in which case the surface is an SDK issue, not a test pattern issue. The current pattern is matrix-safe.
- Disposition: Verified clean by static reasoning. CI matrix run will provide empirical confirmation; no code change recommended in the meantime.
- Cross-reference: V04-READY.txt item 3; `tests/test_smoke.py`; PATCHES.md v0.4 narrative on smoke-test rewrite.

## V04-READY checklist (post-v0.5)

| Item | V04-READY phrasing | Status |
|---|---|---|
| 1 | Stronger canary-string assertion in `test_cross_vendor_audit_missing_lane3_returns_unavailable_without_key_values` | Closed in v0.5 (plus two additional tests covering exception path and raw_result echo). |
| 2 | Focused test for `audit_artifact` empty-file warning | Closed in v0.5 (`test_audit_artifact_warns_when_path_resolves_to_empty_file` plus companion negative-case test). |
| 3 | Manual mental check on `asyncio.run` + `mcp.list_tools()` across CI matrix Pythons | Verified clean in this reconciliation (F-V05-RECON-004). |
| 4 | Split the three-assertion `check_attributions` test | Closed in v0.5 (three separate tests). |
| 5 | PyPI wheel availability for optional extras on 3.10 | Verified clean in this reconciliation (F-V05-RECON-003). |

V04-READY is fully addressed once F-V05-RECON-001 is closed and the two verification items are recorded. F-V05-RECON-001 is now closed.

## Recommended next action

Three viable paths, ranked by what would most extend the audit-chain rather than rework it:

1. **Cross-vendor independent verification of v0.5 (recommended).** Open a GPT-5 thread with v0.5's narrative plus this reconciliation; ask for an independent surface of any finding the producer instances missed. This is a clean cross-vendor pass under PMD v1.2 rotation discipline. The producer for v0.5 was a Claude instance, so ChatGPT is eligible as auditor. Output: REVIEW-V2.md.
2. **Move to v0.6 scope.** Treat v0.5 as published-ready and scope the next functional round (e.g., per-tool richer test fixtures, PyPI publishing dry run, MCP SDK 1.13 compatibility, real lane-#3 orchestrator integration test).
3. **No further action.** Mark v0.5 as ready-for-publication and pause the audit cycle.

If you pick option 1, the GPT-5 brief writes itself from this reconciliation plus the v0.5 PATCHES.md section. If you pick option 2 or 3, the ChatGPT session originally requested is closed without sending.

## Files touched in this reconciliation

- `pyproject.toml` (version bumped 0.4.0 → 0.5.0).
- `SUBSTRATE-RECONCILIATION-V05.md` (this file).

Tests rerun after the version bump: `pytest tests/` reports `14 passed in 3.54s` on Python 3.10.12.

---

Authorship: third Claude instance (Cowork, 2026-05-10), under BayyinahEnterprise audit methodology. Infrastructure substrate: Patrick Estes (Estes Strategy Insights, LLC).
