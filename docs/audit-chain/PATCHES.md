# Patches applied locally to ChatGPT's first draft

ChatGPT's first response (extracted from `https://chatgpt.com/c/6a014a3f-8a00-83ea-a20a-196587e109a9`) shipped 17 of the 17 requested files. After extraction, three classes of issue surfaced when running the smoke test. All were patched in this session; the patches are recorded here so a reviewer can decide whether to roll them back into ChatGPT for a clean v0.2 or merge them as-is.

## P1: `audit_artifact.py` was truncated mid f-string

ChatGPT used a literal ```` ```text ```` fence inside the f-string returned by `_build_audit_prompt`. The ChatGPT UI's code-block renderer interpreted that inner fence as the close of the outer Python fence, so the DOM lost everything after the inner fence open. The extracted file ended at `{artifact_block}` with no closing `"""` and no return statement.

**Fix:** asked ChatGPT in a follow-up to resend the file using `~~~text` for inner fences instead of ```` ```text ````. Second response was complete (6,455 chars) and compiled cleanly.

**Recommend:** add a code-style guideline for ChatGPT's future runs: never use triple-backtick fences inside string literals when the response will be rendered as a fenced block. Use tildes (`~~~`) or a sentinel + replace.

## P2: `NotRequired` used inside `TypedDict` broke MCP tool registration

Four tool modules (`check_attributions`, `lookup_section`, `furqan_lint`, `cross_vendor_audit`) used `NotRequired[X]` from `typing_extensions` inside `TypedDict` output types. The MCP SDK's `FastMCP.add_tool` walks the return-type annotation, calls `pydantic.create_model` against the `TypedDict`, and Pydantic 2.13 raises `PydanticForbiddenQualifier: The annotation 'NotRequired[str]' contains the 'typing.NotRequired' type qualifier, which is invalid in the context it is defined.`

**Fix applied locally:** rewrote each affected `TypedDict` to declare `total=False` on the class and stripped the `NotRequired[...]` wrappers from individual fields. Removed the now-unused `from typing_extensions import NotRequired` imports.

This is a slight contract loosening: `total=False` makes every field optional, where the original intent was to mark only some fields optional and keep others required. The MCP tool envelopes in this project never carry "must have field X" semantics on the output (the consumer always inspects `status` first), so the looseness is harmless.

**Recommend:** ask ChatGPT to use `Required[X]` from `typing_extensions` to mark the still-required fields when emitting `TypedDict(total=False)`, OR to replace the output types with Pydantic models (which support optional fields cleanly via `Optional[X] = None`). The second option is more idiomatic for an MCP project that already uses Pydantic for inputs.

## P3: `typing.TypedDict` not accepted by Pydantic 2.13 on Python <3.12

Even after the NotRequired fix, Pydantic raised `PydanticUserError: Please use 'typing_extensions.TypedDict' instead of 'typing.TypedDict' on Python < 3.12.`

**Fix applied locally:** replaced `from typing import TypedDict` with `from typing_extensions import TypedDict` across every `bayyinah_audit_mcp/**/*.py` file that declared one.

**Recommend:** add `typing_extensions>=4.7` as an explicit dependency in `pyproject.toml`. The project currently inherits it transitively from `pydantic`, but the import is now first-class.

## Verified after patches

Running `python -m pytest tests/test_smoke.py` from the project root:

```
tests/test_smoke.py::test_imports_and_registers_all_tools PASSED
============================== 1 passed in 3.77s ===============================
```

Per-tool functional smoke (manual, not in the test suite):

| Tool | Verified |
|---|---|
| `bayyinah_list_sections` | returns the 5 seeded sections with title + summary |
| `bayyinah_lookup_section` | resolves §9.1, 9.1, "Section 14.5"; returns `not_found` for 99.99 |
| `bayyinah_audit_artifact` | returns a complete audit prompt with section context |
| `bayyinah_check_attributions` | flags §99.99 as unresolved against the seeded index |
| `bayyinah_run_furqan_lint` | returns `unavailable` envelope when binary missing |
| `bayyinah_cross_vendor_audit` | returns `unavailable` envelope when lane #3 module not installed |
| `bayyinah_generate_round_report` | renders Round-1 markdown report; respects severity threshold (BLOCKED/PASSED) |

## Open code-quality items to send back to ChatGPT

These didn't break anything but are worth a v0.2:

- **Inconsistent sync vs async.** Six tools are sync functions, `bayyinah_cross_vendor_audit` is `async`. The MCP SDK accepts both, but consistency matters for testability. Pick one (sync is simpler since none of the tools actually need to await network I/O at the server boundary - lane #3 is its own subprocess).
- **`pyproject.toml` declares `requires-python = ">=3.11"`.** With the typing_extensions fix, the code now runs on 3.10 too. Either lower the floor (and test on 3.10) or keep the floor but add a clarifying comment.
- **`tools/__init__.py` was missing.** Created locally as a one-line stub. Add it to the next ChatGPT round's file list.

---

## v0.2 (round-trip back to ChatGPT)

After the local patches above, ChatGPT was asked to roll the same changes back into the codebase so future regenerations land clean. v0.2 ships:

- **Output types are now Pydantic BaseModels**, not TypedDicts. `Optional[X] = None` for optional fields. Wire shape unchanged.
- **`typing_extensions>=4.7`** added as a first-class runtime dependency in `pyproject.toml`.
- **All seven tools are sync.** `bayyinah_cross_vendor_audit` no longer uses `async def`; it still defensively checks `inspect.isawaitable` on lane #3's return so an async orchestrator surfaces a clean error envelope instead of crashing.
- **`bayyinah_audit_mcp/tools/__init__.py`** now ships in the package.
- **Version bumped to 0.2.0** in `bayyinah_audit_mcp/__init__.py`.

Verified after sync:
- `pytest tests/test_smoke.py` passes (1 test, all 7 tools register).
- Manual functional test on every tool returns the same key set as v0.1.
- No `NotRequired` remains in the codebase.

The reviewer should now read v0.2 source, not the v0.1 + patches.

---

## v0.3 (round-trip after independent review)

REVIEW-V1.md from the second Claude surfaced four bugs and one security hole. Two ChatGPT round-trips landed v0.3:

### Must-fix items closed

1. **server.py** - module-level `mcp = create_mcp()` deleted. The server is now constructible only by an explicit caller (`__main__`, tests, embedders), no side effects at import.
2. **config.py** - `BAYYINAH_PATH_STRICT` env var added. When set, `resolve_path()` enforces `resolved.is_relative_to(audit_root)`, blocking `/etc/passwd`-style escapes. Documented as required for any SSE/HTTP transport.
3. **cross_vendor_audit.py** - three secret-leak vectors closed:
   - Lane #3 payload now carries `api_keys_present: list[str]` (provider names only). No key VALUES leave the MCP server.
   - Exception envelope returns only `type(exc).__name__` plus a generic "see server logs" reason; full `repr(exc)` goes to the stdlib `logging` module server-side.
   - Verbatim `raw_result` echo replaced with `_normalize_result()`, an allowlist normaliser that copies only `consensus`, `solo_findings`, `validator_panel`, `status`, `reason` from lane #3's return.
4. **furqan_lint.py** - status mislabel fixed. When `returncode != 0` and `findings` is empty, status is now `"error"` (was incorrectly `"completed_with_findings"`).
5. **furqan_lint.py** - `max_output_chars` field on `FurqanLintInput` (default 65 536). Both `stdout` and `stderr` are truncated in the response envelope so lint output that echoes file contents cannot leak source through the MCP wire.

### Nice-to-have items folded in

- `sections.py` - `@lru_cache(maxsize=16)` on `load_section_index()`. A five-ref `audit_artifact` call now does one JSON read, not five.
- `check_attributions.py` - `AUTHOR_YEAR_RE` augmented with month/weekday stop-list to drop "December 2024" / "Monday 2025" false positives.
- `audit_artifact.py` - empty-file warning distinguishes "path read, file empty" from "no artifact_text or artifact_path supplied."

### Verified after sync

- `pytest tests/test_smoke.py` passes (1 test, all 7 tools register).
- Issue 1: no `^mcp = create_mcp` at module scope in server.py.
- Issue 2: `is_relative_to` enforcement present in config.py.
- Issue 3a: `api_keys_present=key_providers` (names) at all call sites in cross_vendor_audit.py.
- Issue 3b: exception handler uses `type(exc).__name__` and `LOGGER`.
- Issue 3c: `_normalize_result` allowlist function present.
- Issue 4: `elif completed.returncode != 0 and not findings: status = "error"` in furqan_lint.py.
- Issue 5: `_truncate_output(stdout, request.max_output_chars)` and same for stderr.

### Items deferred to a later round

REVIEW-V1.md called out three items that didn't land in v0.3:

- Per-tool functional tests (especially section-ref normalisation and threshold gating).
- `requires-python` floor decision (lower to 3.10 with CI matrix, or annotate why 3.11).
- Replace `tests/test_smoke.py` introspection of `_tool_manager._tools` with the SDK's public list-tools path once it stabilises.

These are testing/packaging items rather than runtime correctness or security, so they can ride a v0.4 round.

---

## v0.4 (testing + packaging)

All deferred items from REVIEW-V1.md are closed:

### Files added or changed

- `bayyinah_audit_mcp/__init__.py` - version bumped to 0.4.0.
- `pyproject.toml` - `requires-python = ">=3.10"` (was 3.11); `[tool.pytest.ini_options]` block with `testpaths = ["tests"]`.
- `tests/test_smoke.py` - rewritten to use `mcp.list_tools()` via the MCP SDK's public path; no more `_tool_manager._tools` introspection.
- `tests/test_tools.py` - **new**, one functional test per tool:
  - `lookup_section` - §9.1 / 9.1 / "Section 9.1" all normalize to the same record
  - `list_sections` - 5 seeded refs returned
  - `audit_artifact` - prompt envelope includes the §9.1 title
  - `check_attributions` - flags §99.99 unresolved; does NOT flag "December 2024" as a citation; surfaces missing corpus as a warning
  - `furqan_lint` - returns `unavailable` envelope when binary absent; `max_output_chars` defaults to 65536
  - `cross_vendor_audit` - returns `unavailable` envelope when lane #3 missing; `api_keys_present` carries provider names only, never values
  - `generate_round_report` - HIGH finding + MED threshold returns `blocked=True`; invalid threshold is handled
- `.github/workflows/ci.yml` - **new**, matrix across Python 3.10 / 3.11 / 3.12 / 3.13 on ubuntu-latest; installs `-e '.[all]'`, runs pytest.

### Verified

- `pytest tests/` runs 8 tests, all pass, on Python 3.10.12.
- CI yml parses as valid YAML.
- `requires-python = ">=3.10"` and `[tool.pytest.ini_options]` both present in pyproject.toml.
- `test_smoke.py` uses `mcp.list_tools()`, not `_tool_manager._tools`.

### State

The package now satisfies every must-fix and nice-to-have item from the second Claude's REVIEW-V1.md. v0.4 is ready for either a second review pass or publication (PyPI as `bayyinah-audit-mcp`, per the spec's open question 3).

---

## v0.4 (testing + packaging)

All deferred items from REVIEW-V1.md are closed:

### Files added or changed

- `bayyinah_audit_mcp/__init__.py` - version bumped to 0.4.0.
- `pyproject.toml` - `requires-python = ">=3.10"` (was 3.11); `[tool.pytest.ini_options]` block with `testpaths = ["tests"]`.
- `tests/test_smoke.py` - rewritten to use `mcp.list_tools()` via the MCP SDK's public path; no more `_tool_manager._tools` introspection.
- `tests/test_tools.py` - **new**, one functional test per tool:
  - `lookup_section` - §9.1 / 9.1 / "Section 9.1" all normalize to the same record
  - `list_sections` - 5 seeded refs returned
  - `audit_artifact` - prompt envelope includes the §9.1 title
  - `check_attributions` - flags §99.99 unresolved; does NOT flag "December 2024" as a citation; surfaces missing corpus as a warning
  - `furqan_lint` - returns `unavailable` envelope when binary absent; `max_output_chars` defaults to 65536
  - `cross_vendor_audit` - returns `unavailable` envelope when lane #3 missing; `api_keys_present` carries provider names only, never values
  - `generate_round_report` - HIGH finding + MED threshold returns `blocked=True`; invalid threshold is handled
- `.github/workflows/ci.yml` - **new**, matrix across Python 3.10 / 3.11 / 3.12 / 3.13 on ubuntu-latest; installs `-e '.[all]'`, runs pytest.

### Verified

- `pytest tests/` runs 8 tests, all pass, on Python 3.10.12.
- CI yml parses as valid YAML.
- `requires-python = ">=3.10"` and `[tool.pytest.ini_options]` both present in pyproject.toml.
- `test_smoke.py` uses `mcp.list_tools()`, not `_tool_manager._tools`.

### State

The package now satisfies every must-fix and nice-to-have item from the second Claude's REVIEW-V1.md. v0.4 is ready for either a second review pass or publication (PyPI as `bayyinah-audit-mcp`, per the spec's open question 3).

---

## v0.5 (REVIEW-V2 round)

### Real test gaps closed (must-fix before v1.0)

- `tests/test_tools.py::test_cross_vendor_audit_exception_path_does_not_leak_canary` - new. Monkeypatches a fake `bayyinah_audit_orchestrator` whose `run_cross_vendor_audit` raises `ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")`. Asserts the canary string is absent from the response and `str(exc)` is not echoed in `reason`. This actually exercises the v0.3 Issue 3b scrub.
- `tests/test_tools.py::test_cross_vendor_audit_does_not_leak_via_raw_result` - new. Monkeypatches a fake orchestrator returning `{"raw_log": "Authorization: Bearer " + canary, "status": "ok"}`. Asserts the canary is absent from `result.model_dump_json()`. Locks the v0.3 Issue 3c allowlist normaliser as contract.

### Coverage gaps closed

- `tests/test_tools.py::test_audit_artifact_warns_when_path_resolves_to_empty_file` - new. Locks the "path read, file empty" warning is distinct from the "no artifact supplied" warning.
- `tests/test_tools.py::test_audit_artifact_warns_when_neither_text_nor_path_is_given` - companion. Locks the inverse: generic warning fires, "empty" does not.
- The single combo test is now three: `test_check_attributions_flags_unknown_section_ref`, `test_check_attributions_ignores_month_and_weekday_words` (now exercises both halves of `DATE_WORD_STOPLIST` with a Monday case), `test_check_attributions_warns_on_missing_corpus` (also asserts `status == "ok_with_warnings"`).

### Quality items

- `tools/cross_vendor_audit.py` - TODO comment at the async-rejection branch documents the deliberate sync contract (revisit if lane #3 ever ships async-only).
- `README.md` - new short Security section noting `BAYYINAH_PATH_STRICT=1` is required for SSE/HTTP transport.
- Version bumped to `0.5.0` in `bayyinah_audit_mcp/__init__.py`.

### Deferred per cost analysis

- Optional-extras upper-bound pinning - left to first failing CI run (REVIEW-V2 cost analysis was sound).

### Verified

- `pytest tests/` - **14 passed in 4.42s** on Python 3.10.12.
- All four files written to the workspace; CI yml unchanged from v0.4.

---

## v0.5.1 (REVIEW-V3 fast-follows; test-only + one comment prefix)

REVIEW-V3 cleared v0.5 to ship and recommended four small items that
tighten the contract without changing runtime behaviour. All four
applied directly (no ChatGPT round-trip needed - they are test edits
plus a one-character comment prefix):

1. **`test_cross_vendor_audit_output_fields_are_stable`** - new test.
   Asserts `set(CrossVendorAuditOutput.model_fields.keys()) == {...}`.
   Locks the leak-prevention allowlist at the schema level. A future
   contributor adding `raw_log: str` to the output now has to update
   this test, which forces them to think about leak surface.

2. **Empty-file warning - structural assertions.** Replaced
   `"empty" in joined_warnings` (substring, brittle) with
   `len(result["warnings"]) == 1` plus `"empty.txt" in result["warnings"][0]`.
   The count assertion catches the "both warnings fire" regression
   structurally; the path string is what the test wrote and is
   unlikely to disappear from any reasonable rewording.

3. **Positive case in the date-words test.** Added
   `"Smith 2024 reports the relevant statistics"` to the artifact and
   asserted `"Smith 2024" in checked_citations`. Locks that the
   month/weekday stop-list does not over-match.

4. **`TODO:` prefix on the deliberate-sync comment** in
   `cross_vendor_audit.py:263`. The note is now visible to any linter
   or grep for `TODO`.

5. **Bonus micro-add** to `test_cross_vendor_audit_exception_path_does_not_leak_canary`:
   `assert canary not in (result.api_keys_present or [])`. Pins
   `api_keys_present` to provider names, never values.

### Verified

- `pytest tests/` - **15 passed in 5.83s** on Python 3.10.12 (was 14
  in v0.5; +1 for `test_cross_vendor_audit_output_fields_are_stable`).
- All four REVIEW-V3 fast-follow items closed.
- Version bumped to `0.5.1` in `bayyinah_audit_mcp/__init__.py`.

### State

REVIEW-V3 verdict: **shippable**. Three items remain for v0.6+ and are
contract-boundary work that does not belong in this wrapper:

- Tighten `consensus` schema OR push canary requirement into lane #3's
  own test suite.
- Structured warning codes (`code: Literal["empty_file", ...]`).
- Anything the live CI matrix surfaces on first push (asyncio + 3.13
  is the highest-likelihood failure mode; remediation is documented).

The MCP server thread is paused here pending Bilal's go/no-go on
publishing to PyPI as `bayyinah-audit-mcp`.

---

## v0.5.1 part 2 (REVIEW-V4 / CROSS-VENDOR-AUDIT-V05 must-fix hotfix; third Claude)

After v0.5.1 part 1 landed (REVIEW-V3 fast-follows above), a third
Claude instance drove a cross-vendor audit pass through GPT-5 against
v0.5 per PMD v1.2 rotation discipline. GPT-5 surfaced two HIGH
findings the intra-Claude chain missed plus uncontested must-fixes on
README rendering and path-strict default safety. The uncontested
hotfix items landed in v0.5.1 immediately; the contested F-V05-002
(wrapper-vs-orchestrator canary ownership) is deferred to a Tier 1
adjudicator pass and remains open.

Source audit chain: `CROSS-VENDOR-AUDIT-V05.md` (canonical), with
`REVIEW-V4.md` preserved as a duplicate-content historical cell from
the round-naming reconciliation between the driver instance and the
second Claude on 2026-05-11.

### Uncontested must-fixes closed in v0.5.1 part 2

1. **F-V05-001 [HIGH]** -- `bayyinah_audit_mcp/tools/cross_vendor_audit.py`
   exception handler. Was `LOGGER.exception("...: %r", exc)`. The `%r`
   format echoes the full exception repr, including any secret value
   that lane #3 embedded in the message string; `LOGGER.exception` also
   attaches the traceback, which can carry the same value in local
   variable reprs. Switched to `LOGGER.error("...: %s", type(exc).__name__)`
   with explicit comment documenting the deliberate omission of
   `exc_info`. The MCP response was already clean (asserted by the v0.5
   canary test); this closes the log-side leak that the response-side
   test did not cover.

2. **F-V05-003 [MEDIUM]** -- `README.md` SSE and streamable-HTTP run
   snippets. The Security section correctly documented
   `BAYYINAH_PATH_STRICT=1` as required for network transports, but the
   visible copy-paste run examples did not export it inline. A user
   following the visible examples could bring up the server over SSE or
   streamable HTTP with strict-mode off. Inlined the export in both
   network-transport snippets so the documented behaviour is the
   default copy-paste behaviour.

3. **F-V05-008 [MEDIUM]** -- `README.md` Markdown fences. Every fenced
   code block was missing its closing fence. PyPI and GitHub renderers
   were collapsing most of the README into one giant code block,
   obscuring install, run, security, and environment guidance. Closed
   all fences. Also added the `cross-vendor` extras note clarifying
   that the extra installs vendor SDKs only, not the lane #3
   orchestrator itself.

### New test (locks F-V05-001 against regression)

`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`
-- captures `caplog` at DEBUG level, monkeypatches a fake orchestrator
that raises `ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")`,
and asserts the canary string does not appear in any log record's
message, formatted message, traceback, or `exc_text`. This is the
test surface F-V05-004 called out as missing from v0.5; closing it
here as part of the F-V05-001 hotfix rather than leaving it for v0.6.

### Verified

- `pytest tests/` -- **16 passed in 6.92s** on Python 3.10.12 (was 15
  after v0.5.1 part 1; +1 for the new caplog test).
- `pyproject.toml` and `bayyinah_audit_mcp/__init__.py` both at
  `0.5.1` (second Claude closed an earlier two-source-of-truth drift
  at the 0.5.0 → 0.5.1 transition; substrate-reconciliation finding
  class F-V05-RECON-001 is now twice-closed).
- README renders correctly: every fence pairs, BAYYINAH_PATH_STRICT
  is visible in the network-transport copy-paste examples, and the
  cross-vendor extras note is present.

### Deferred from CROSS-VENDOR-AUDIT-V05.md to v0.6 (or to adjudication)

- **F-V05-002 [HIGH, contested]** -- wrapper-side sanitization of
  allowed fields (`reason`, `consensus`, `solo_findings`,
  `validator_panel`). REVIEW-V3 deferred this to v0.6 as contract-
  boundary work that belongs in lane #3. CROSS-VENDOR-AUDIT-V05
  calls it must-fix-before-publish with a wrapper-side
  `_redact_string` + `_sanitize_for_output` patch. Adjudication
  pending; Tier 1 non-producer non-auditor (Perplexity) is the
  cleanest fit. The proposed patch is preserved verbatim in
  CROSS-VENDOR-AUDIT-V05.md so it can be applied without
  re-derivation if the adjudicator endorses the wrapper-side
  approach.
- **F-V05-004 [MEDIUM]** -- additional caplog/log-surface coverage
  on the existing exception-path test (the v0.5.1 part 2 work above
  added a parallel new test rather than modifying the existing one;
  if the adjudicator wants both tests merged, that is a v0.6 cleanup).
- **F-V05-005 [MEDIUM]** -- raw-result test covering allowed fields
  (depends on F-V05-002 adjudication).
- **F-V05-006 [LOW]** -- CI packaging check (`python -m build` plus
  `twine check dist/*` or a Markdown fence linter).
- **F-V05-007 [LOW, accept-with-rationale]** -- README cross-vendor
  extras orchestrator note. Closed as part of v0.5.1 part 2 README
  rewrite even though disposition was accept-with-rationale; the
  prose is now explicit.
- **F-V05-009 [LOW]** -- close the awaitable on the rejection branch.
- REVIEW-V3 v0.6-class items (consensus schema tightening,
  structured warning codes, CI matrix first-push results).

### State

v0.5.1 is shippable on the uncontested findings. F-V05-002
adjudication is the gating question for whether v0.6 includes
wrapper-side canary scrubbing or pushes that requirement into lane
#3's own test suite.

---

## v0.5.2 (PyPI hardening)

Triggered by Bilal's PyPI go decision. F-V05-002 from REVIEW-V3 (the
canary-inside-allowlisted-fields surface) flips from "contract-boundary
issue belonging to lane #3" to "must fix before public release"
because PyPI consumers will bring their own lane #3 implementations
the wrapper has never seen.

### Structural changes

1. **`Consensus` Pydantic model.** `consensus: Optional[Any]` on
   `CrossVendorAuditOutput` is now `Optional[Consensus]`, where
   `Consensus` carries four typed fields: `verdict` (Literal),
   `reasoning` (str, scrubbed), `agreed_findings: list[Finding]`,
   `disagreement_count: int`. Both `Consensus` and `Finding` use
   `model_config = ConfigDict(extra="ignore")` so any extra keys lane
   #3 returns are silently dropped (defense in depth atop the
   explicit allowlist normaliser already shipped in v0.3).

2. **`_scrub` defense-in-depth string redaction.** Five regex
   patterns (`sk-...`, `sk-ant-...`, `Bearer ...`, `Authorization: ...`,
   `api[_-]?key=...`) replace matches with `<REDACTED>`. Applied to
   every string-typed output: `reason`, `Consensus.reasoning`, every
   `Finding.message` and `Finding.location`. The scrub is the
   wrapper-side answer to GPT-5's V05-002 finding (canary embedded
   inside a known field would otherwise pass the allowlist).

### Tests added

- `test_cross_vendor_audit_consensus_extra_fields_dropped` - asserts
  `Consensus` constructed with extra unknown keys silently drops them.
- `test_cross_vendor_audit_scrub_redacts_canary_inside_consensus_reasoning` -
  fake orchestrator returns `Consensus(reasoning="diagnostic: key was sk-test-CANARY-...")`,
  asserts canary absent from `result.model_dump_json()`.
- `test_cross_vendor_audit_scrub_redacts_canary_inside_finding_message` -
  same for a solo finding's message field.

The three v0.3 / v0.5 / v0.5.1 canary tests still pass unchanged.

### Tests passing

`pytest tests/` - **17 passed in 2.58s** on Python 3.10.12 (was 15 in
v0.5.1; +2 new tests, the third was folded into the existing
exception-path test's assertions).

### README

New `## For PyPI consumers` section near the top documenting:
- The lane #3 contract (callable shape, expected return types).
- `BAYYINAH_PATH_STRICT=1` is REQUIRED for SSE/HTTP transport.
- Bundled `section_index.json` ships with five entries; consumers
  should point `BAYYINAH_SECTION_INDEX` at their full index.

### State

v0.5.2 is the PyPI-publishable release. F-V05-002 is closed. The two
remaining pre-tag conditions are operational, not architectural:

1. Push to a release-candidate branch and verify the GitHub Actions
   matrix (Python 3.10/3.11/3.12/3.13) is green before tagging.
2. Run `pip install -e '.[all]'` in the actual sandbox to confirm
   `anthropic`, `openai`, `google-genai`, `pdfplumber` all have wheels
   on 3.10 (REVIEW-V2 Q5).

After that, `python -m build && twine upload dist/*`.

---

## v0.5.3 (PATCH-STRESS hardening + F-V05-001 re-application; third Claude)

Triggered by Pat's pre-emptive endorsement of GPT-5's adversarial
self-stress test (`CROSS-VENDOR-AUDIT-V05-PATCH-STRESS.md`) over the
v0.5.2 narrow five-pattern wrapper-side scrub. Endorsement was a flat
yes-yes-yes against the three adjudication questions: hardened patch
regex set acceptable as drafted, env-redaction floor at 4 chars
tolerable, six lane-#3 contract requirements clean enough for
Bilal/Fraz to absorb.

### Substrate-of-record finding (regression flagged)

The v0.5.2 round inadvertently reverted the F-V05-001 LOGGER.error fix
that landed in v0.5.1 part 2. As of v0.5.2 line 384, the exception
handler was back to `LOGGER.exception("...: %r", exc)`, which echoes
the full exception repr (including args, which can carry leaked secret
values) to server logs. The v0.5.1 caplog test
`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`
was also dropped from `tests/test_tools.py` between v0.5.1 part 2 and
v0.5.2, so no test surface existed to catch the regression.

This recurrence is class F-V05-RECON-001-style drift (single-source-of-
truth violation between successive instance hand-offs). v0.5.3 closes
it by re-applying the LOGGER fix AND restoring the caplog regression
test. The drift is also logged as a process finding for the next
substrate-reconciliation pass: parallel-instance edits on the same
file class need a hand-off discipline tighter than what the current
narrative chain provides.

### Code changes

1. **`bayyinah_audit_mcp/tools/cross_vendor_audit.py` rewritten with
   layered scrubbing.** Two layers replace the narrow v0.5.2 regex:

   - **Env-bound value substitution.** `SECRET_ENV_NAMES` widened to
     nine variables covering Anthropic admin keys, Google Application
     Credentials, and the three AWS credential env vars. Floor lowered
     to `MIN_ENV_SECRET_REDACT_CHARS = 4` with
     `ENV_VALUE_REDACTION_DENYLIST = {true, false, none, null, test,
     prod, dev, local}` to bound over-firing. Flexible-whitespace
     matching via `ENV_WRAP_SEPARATOR_RE` catches multi-line wrapped
     secrets where each character is separated by whitespace or
     zero-width separators (bypass class 12 from the stress test).

   - **`REDACTION_RULES` regex tuple.** 17 rules covering 15 of the 16
     bypass classes GPT-5 surfaced: PEM private-key blocks, expanded
     Authorization-header schemes (Bearer, Basic, Token, ApiKey,
     API-Key), Cookie and Set-Cookie headers, basic-auth URLs,
     quoted-or-unquoted credential-label key-value matching covering
     JSON / query params / env-style / header-style / vendor-specific
     labels, partial-fingerprint shapes (`sk-...last4`,
     `fingerprint=...`, `sha256:...`, `last_4=...`), and vendor-prefix
     bare-value shapes (`sk-`, `sk-ant-`, `xai-`, `AIza`, `ya29.`,
     `AKIA`/`ASIA`, GitHub `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`,
     `github_pat_`, Slack `xox[baprs]-`, bare three-segment JWTs).
     Redaction marker is `<REDACTED>` for consistency with v0.5.2 test
     expectations.

   - **`_scrub` is now layered.** Env-bound values get substituted
     first (catches multi-line wrapping at character resolution), then
     the REDACTION_RULES tuple runs in order. All existing call sites
     (`_scrub_optional`, `_normalize_finding`, `_normalize_consensus`,
     the exception-path `reason`, the ImportError-path `reason`)
     inherit the broader coverage without changing their call shape.

2. **F-V05-001 re-applied at the exception handler.**
   `LOGGER.exception("...: %r", exc)` swapped back to
   `LOGGER.error("...: %s", type(exc).__name__)` with comment
   documenting the deliberate omission of `exc_info` and the v0.5.2
   regression history.

3. **F-V05-009 closed (nice-to-have from CROSS-VENDOR-AUDIT-V05).**
   The awaitable rejection branch now calls `result.close()` if the
   coroutine exposes it, suppressing "coroutine was never awaited"
   runtime warnings.

### Tests added

1. **`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`**
   restored. Captures `caplog` at DEBUG and asserts the canary string
   is absent from every record's `message`, formatted message,
   traceback, and `exc_text`.

2. **`test_cross_vendor_audit_hardened_patch_closes_bypass_class`**
   parameterized across 15 bypass classes:

   - `custom_vendor_key_label` (xai-prefixed value in XAI_KEY label).
   - `anthropic_admin_key_label` (ANTHROPIC_ADMIN_KEY label).
   - `google_oauth_bare_token` (`ya29.` prefix).
   - `aws_access_key_id_label` (AWS_ACCESS_KEY_ID label + AKIA prefix).
   - `bare_jwt` (three-segment base64url).
   - `authorization_token_scheme` (Authorization: Token scheme).
   - `cookie_session` (Cookie: session= + csrftoken).
   - `oauth_code_state` (URL query with code= and state= params).
   - `url_query_key_param` (URL query with bare `key=` not `api_key=`).
   - `basic_auth_url` (`https://user:password@host` form).
   - `quoted_json_api_key` (quoted JSON key-value).
   - `truncated_fingerprint_echo` (`sk-...last4` fingerprint shape).
   - `pem_private_key_block` (full BEGIN/END PRIVATE KEY block).
   - `github_personal_access_token` (`ghp_` prefix).
   - `slack_bot_token` (`xoxb-` prefix).

   Each case asserts the substring `CANARY` is absent from the dumped
   output and that `<REDACTED>` is present. The 16th class (arbitrary
   unlabeled opaque values) is owned by lane #3 per the contract spec.

### Documentation added

- **`LANE-3-CONTRACT-V05.md`** -- new standalone document at the
  workspace root. Specifies the six contract requirements
  (LANE3-C1 through LANE3-C6) lane #3's own test suite must prove
  to compensate for the 16th bypass class plus structural
  responsibilities the wrapper cannot fulfill from its position.
  Framed as a deliverable for BayyinahEnterprise (Bilal, Fraz) and
  for third-party `bayyinah_audit_orchestrator` providers shipping
  via PyPI.

### Tests passing

`pytest tests/` -- **33 passed in 5.54s** on Python 3.10.12 (was 17 in
v0.5.2; +16 tests broken down as: +1 restored caplog test for
F-V05-001, +15 parameterized hardened-bypass-class coverage cases).

### Version

Bumped from `0.5.2` to `0.5.3` in both `pyproject.toml` and
`bayyinah_audit_mcp/__init__.py`. F-V05-RECON-001 drift check: both
files match at `0.5.3`.

### Deferred

- Adjudicator validation. Pat pre-emptively endorsed the three
  adjudication questions in chat ("Assume all yes for the time being,
  mate!"). The audit-chain entry that records this pre-emptive
  adjudication is the conversation transcript and this narrative
  section; if a formal cross-vendor adjudicator pass (Perplexity Tier
  1, Gemini/Grok Tier 2) is later run, that document supersedes the
  pre-emptive endorsement.
- Lane #3 adoption of LANE-3-CONTRACT-V05.md. Bilal and Fraz own this
  on the `bayyinah_audit_orchestrator` repo side.
- CI matrix and `pip install -e '.[all]'` verification on 3.10. The
  two operational pre-tag conditions from v0.5.2 still apply.

### State

v0.5.3 is publication-ready on the structural axis. Wrapper-side
coverage is at parity with GPT-5's hardened patch design plus the
F-V05-001 log-surface fix. Lane #3 has a concrete six-requirement
contract to integrate. Operational pre-tag conditions (CI matrix
green on 3.10-3.13, pip install verification) inherited from v0.5.2.

---

## v0.5.4 (post-REVIEW-V5 nice-to-haves)

Three items from REVIEW-V5's v0.5.4 punch list landed directly (no
ChatGPT round needed; the changes were small and self-contained).

### Changes

1. **`Consensus.metadata` forward-compat hatch.** New
   `metadata: dict[str, Any] = Field(default_factory=dict)` field on
   `Consensus`. Lane #3 implementations that surface fields beyond
   the four canonical ones can now pass them through without losing
   data. Paired with new `_scrub_dict` helper that recursively walks
   dict / list / tuple structures and applies `_scrub` to every string
   leaf - so a credential nested inside `metadata.diagnostics.headers_seen[1]`
   is still redacted on the way out.

2. **Four additional vendor prefixes** added to `REDACTION_RULES`:
   `pplx-` (Perplexity), `gsk_` (Groq), `r8_` (Replicate), `hf_`
   (HuggingFace). Closes the v0.6 candidate item from REVIEW-V5
   ahead of schedule. Lane #3 still owns the canonical non-leak
   guarantee for these vendors; the wrapper just catches the most
   common bare-value forms.

3. **`LANE-3-CONTRACT-V05.md` updated** with a closed-form list of
   vendor prefixes the wrapper does NOT catch (Cohere, Mistral,
   Together AI, Fireworks AI, DeepSeek, custom in-house orchestrators).
   Closes the third-party orchestrator author's awareness gap.

### Tests added

- `test_cross_vendor_audit_metadata_hatch_scrubs_nested_canary` -
  verifies `_scrub_dict` walks 3-level-deep metadata
  (`metadata.diagnostics.headers_seen[1]`) and redacts an embedded
  Bearer token. Asserts non-secret fields like `iteration_id` survive.
- 4 new entries in `HARDENED_BYPASS_CLASS_CASES` parametrize the
  existing `test_cross_vendor_audit_hardened_patch_closes_bypass_class`
  test over the new vendor prefixes.

### Tests passing

`pytest tests/` - **38 passed in 3.86s** on Python 3.10.12 (was 33 in
v0.5.3; +4 vendor-prefix bypass cases + 1 metadata-scrub test).

### Open / deferred to v0.6

- `BAYYINAH_EXTRA_SECRET_PATTERNS` env-var configurability for the
  REDACTION_RULES tuple.
- Integrate `_skeptical-persona-suffix.py` (the second Claude's
  draft) into `tools/cross_model_audit/reviewers.py` so the v0.5.2 ->
  v0.5.3 self-stress cycle becomes a tag-push CI workflow instead of
  a manual adversarial pass.


---

## v0.2 (round-trip back to ChatGPT)

After the local patches above, ChatGPT was asked to roll the same changes back into the codebase so future regenerations land clean. v0.2 ships:

- **Output types are now Pydantic BaseModels**, not TypedDicts. `Optional[X] = None` for optional fields. Wire shape unchanged.
- **`typing_extensions>=4.7`** added as a first-class runtime dependency in `pyproject.toml`.
- **All seven tools are sync.** `bayyinah_cross_vendor_audit` no longer uses `async def`; it still defensively checks `inspect.isawaitable` on lane #3's return so an async orchestrator surfaces a clean error envelope instead of crashing.
- **`bayyinah_audit_mcp/tools/__init__.py`** now ships in the package.
- **Version bumped to 0.2.0** in `bayyinah_audit_mcp/__init__.py`.

Verified after sync:
- `pytest tests/test_smoke.py` passes (1 test, all 7 tools register).
- Manual functional test on every tool returns the same key set as v0.1.
- No `NotRequired` remains in the codebase.

The reviewer should now read v0.2 source, not the v0.1 + patches.

---

## v0.3 (round-trip after independent review)

REVIEW-V1.md from the second Claude surfaced four bugs and one security hole. Two ChatGPT round-trips landed v0.3:

### Must-fix items closed

1. **server.py** - module-level `mcp = create_mcp()` deleted. The server is now constructible only by an explicit caller (`__main__`, tests, embedders), no side effects at import.
2. **config.py** - `BAYYINAH_PATH_STRICT` env var added. When set, `resolve_path()` enforces `resolved.is_relative_to(audit_root)`, blocking `/etc/passwd`-style escapes. Documented as required for any SSE/HTTP transport.
3. **cross_vendor_audit.py** - three secret-leak vectors closed:
   - Lane #3 payload now carries `api_keys_present: list[str]` (provider names only). No key VALUES leave the MCP server.
   - Exception envelope returns only `type(exc).__name__` plus a generic "see server logs" reason; full `repr(exc)` goes to the stdlib `logging` module server-side.
   - Verbatim `raw_result` echo replaced with `_normalize_result()`, an allowlist normaliser that copies only `consensus`, `solo_findings`, `validator_panel`, `status`, `reason` from lane #3's return.
4. **furqan_lint.py** - status mislabel fixed. When `returncode != 0` and `findings` is empty, status is now `"error"` (was incorrectly `"completed_with_findings"`).
5. **furqan_lint.py** - `max_output_chars` field on `FurqanLintInput` (default 65 536). Both `stdout` and `stderr` are truncated in the response envelope so lint output that echoes file contents cannot leak source through the MCP wire.

### Nice-to-have items folded in

- `sections.py` - `@lru_cache(maxsize=16)` on `load_section_index()`. A five-ref `audit_artifact` call now does one JSON read, not five.
- `check_attributions.py` - `AUTHOR_YEAR_RE` augmented with month/weekday stop-list to drop "December 2024" / "Monday 2025" false positives.
- `audit_artifact.py` - empty-file warning distinguishes "path read, file empty" from "no artifact_text or artifact_path supplied."

### Verified after sync

- `pytest tests/test_smoke.py` passes (1 test, all 7 tools register).
- Issue 1: no `^mcp = create_mcp` at module scope in server.py.
- Issue 2: `is_relative_to` enforcement present in config.py.
- Issue 3a: `api_keys_present=key_providers` (names) at all call sites in cross_vendor_audit.py.
- Issue 3b: exception handler uses `type(exc).__name__` and `LOGGER`.
- Issue 3c: `_normalize_result` allowlist function present.
- Issue 4: `elif completed.returncode != 0 and not findings: status = "error"` in furqan_lint.py.
- Issue 5: `_truncate_output(stdout, request.max_output_chars)` and same for stderr.

### Items deferred to a later round

REVIEW-V1.md called out three items that didn't land in v0.3:

- Per-tool functional tests (especially section-ref normalisation and threshold gating).
- `requires-python` floor decision (lower to 3.10 with CI matrix, or annotate why 3.11).
- Replace `tests/test_smoke.py` introspection of `_tool_manager._tools` with the SDK's public list-tools path once it stabilises.

These are testing/packaging items rather than runtime correctness or security, so they can ride a v0.4 round.

---

## v0.4 (testing + packaging)

All deferred items from REVIEW-V1.md are closed:

### Files added or changed

- `bayyinah_audit_mcp/__init__.py` - version bumped to 0.4.0.
- `pyproject.toml` - `requires-python = ">=3.10"` (was 3.11); `[tool.pytest.ini_options]` block with `testpaths = ["tests"]`.
- `tests/test_smoke.py` - rewritten to use `mcp.list_tools()` via the MCP SDK's public path; no more `_tool_manager._tools` introspection.
- `tests/test_tools.py` - **new**, one functional test per tool:
  - `lookup_section` - §9.1 / 9.1 / "Section 9.1" all normalize to the same record
  - `list_sections` - 5 seeded refs returned
  - `audit_artifact` - prompt envelope includes the §9.1 title
  - `check_attributions` - flags §99.99 unresolved; does NOT flag "December 2024" as a citation; surfaces missing corpus as a warning
  - `furqan_lint` - returns `unavailable` envelope when binary absent; `max_output_chars` defaults to 65536
  - `cross_vendor_audit` - returns `unavailable` envelope when lane #3 missing; `api_keys_present` carries provider names only, never values
  - `generate_round_report` - HIGH finding + MED threshold returns `blocked=True`; invalid threshold is handled
- `.github/workflows/ci.yml` - **new**, matrix across Python 3.10 / 3.11 / 3.12 / 3.13 on ubuntu-latest; installs `-e '.[all]'`, runs pytest.

### Verified

- `pytest tests/` runs 8 tests, all pass, on Python 3.10.12.
- CI yml parses as valid YAML.
- `requires-python = ">=3.10"` and `[tool.pytest.ini_options]` both present in pyproject.toml.
- `test_smoke.py` uses `mcp.list_tools()`, not `_tool_manager._tools`.

### State

The package now satisfies every must-fix and nice-to-have item from the second Claude's REVIEW-V1.md. v0.4 is ready for either a second review pass or publication (PyPI as `bayyinah-audit-mcp`, per the spec's open question 3).

---

## v0.4 (testing + packaging)

All deferred items from REVIEW-V1.md are closed:

### Files added or changed

- `bayyinah_audit_mcp/__init__.py` - version bumped to 0.4.0.
- `pyproject.toml` - `requires-python = ">=3.10"` (was 3.11); `[tool.pytest.ini_options]` block with `testpaths = ["tests"]`.
- `tests/test_smoke.py` - rewritten to use `mcp.list_tools()` via the MCP SDK's public path; no more `_tool_manager._tools` introspection.
- `tests/test_tools.py` - **new**, one functional test per tool:
  - `lookup_section` - §9.1 / 9.1 / "Section 9.1" all normalize to the same record
  - `list_sections` - 5 seeded refs returned
  - `audit_artifact` - prompt envelope includes the §9.1 title
  - `check_attributions` - flags §99.99 unresolved; does NOT flag "December 2024" as a citation; surfaces missing corpus as a warning
  - `furqan_lint` - returns `unavailable` envelope when binary absent; `max_output_chars` defaults to 65536
  - `cross_vendor_audit` - returns `unavailable` envelope when lane #3 missing; `api_keys_present` carries provider names only, never values
  - `generate_round_report` - HIGH finding + MED threshold returns `blocked=True`; invalid threshold is handled
- `.github/workflows/ci.yml` - **new**, matrix across Python 3.10 / 3.11 / 3.12 / 3.13 on ubuntu-latest; installs `-e '.[all]'`, runs pytest.

### Verified

- `pytest tests/` runs 8 tests, all pass, on Python 3.10.12.
- CI yml parses as valid YAML.
- `requires-python = ">=3.10"` and `[tool.pytest.ini_options]` both present in pyproject.toml.
- `test_smoke.py` uses `mcp.list_tools()`, not `_tool_manager._tools`.

### State

The package now satisfies every must-fix and nice-to-have item from the second Claude's REVIEW-V1.md. v0.4 is ready for either a second review pass or publication (PyPI as `bayyinah-audit-mcp`, per the spec's open question 3).

---

## v0.5 (REVIEW-V2 round)

### Real test gaps closed (must-fix before v1.0)

- `tests/test_tools.py::test_cross_vendor_audit_exception_path_does_not_leak_canary` - new. Monkeypatches a fake `bayyinah_audit_orchestrator` whose `run_cross_vendor_audit` raises `ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")`. Asserts the canary string is absent from the response and `str(exc)` is not echoed in `reason`. This actually exercises the v0.3 Issue 3b scrub.
- `tests/test_tools.py::test_cross_vendor_audit_does_not_leak_via_raw_result` - new. Monkeypatches a fake orchestrator returning `{"raw_log": "Authorization: Bearer " + canary, "status": "ok"}`. Asserts the canary is absent from `result.model_dump_json()`. Locks the v0.3 Issue 3c allowlist normaliser as contract.

### Coverage gaps closed

- `tests/test_tools.py::test_audit_artifact_warns_when_path_resolves_to_empty_file` - new. Locks the "path read, file empty" warning is distinct from the "no artifact supplied" warning.
- `tests/test_tools.py::test_audit_artifact_warns_when_neither_text_nor_path_is_given` - companion. Locks the inverse: generic warning fires, "empty" does not.
- The single combo test is now three: `test_check_attributions_flags_unknown_section_ref`, `test_check_attributions_ignores_month_and_weekday_words` (now exercises both halves of `DATE_WORD_STOPLIST` with a Monday case), `test_check_attributions_warns_on_missing_corpus` (also asserts `status == "ok_with_warnings"`).

### Quality items

- `tools/cross_vendor_audit.py` - TODO comment at the async-rejection branch documents the deliberate sync contract (revisit if lane #3 ever ships async-only).
- `README.md` - new short Security section noting `BAYYINAH_PATH_STRICT=1` is required for SSE/HTTP transport.
- Version bumped to `0.5.0` in `bayyinah_audit_mcp/__init__.py`.

### Deferred per cost analysis

- Optional-extras upper-bound pinning - left to first failing CI run (REVIEW-V2 cost analysis was sound).

### Verified

- `pytest tests/` - **14 passed in 4.42s** on Python 3.10.12.
- All four files written to the workspace; CI yml unchanged from v0.4.

---

## v0.5.1 (REVIEW-V3 fast-follows; test-only + one comment prefix)

REVIEW-V3 cleared v0.5 to ship and recommended four small items that
tighten the contract without changing runtime behaviour. All four
applied directly (no ChatGPT round-trip needed - they are test edits
plus a one-character comment prefix):

1. **`test_cross_vendor_audit_output_fields_are_stable`** - new test.
   Asserts `set(CrossVendorAuditOutput.model_fields.keys()) == {...}`.
   Locks the leak-prevention allowlist at the schema level. A future
   contributor adding `raw_log: str` to the output now has to update
   this test, which forces them to think about leak surface.

2. **Empty-file warning - structural assertions.** Replaced
   `"empty" in joined_warnings` (substring, brittle) with
   `len(result["warnings"]) == 1` plus `"empty.txt" in result["warnings"][0]`.
   The count assertion catches the "both warnings fire" regression
   structurally; the path string is what the test wrote and is
   unlikely to disappear from any reasonable rewording.

3. **Positive case in the date-words test.** Added
   `"Smith 2024 reports the relevant statistics"` to the artifact and
   asserted `"Smith 2024" in checked_citations`. Locks that the
   month/weekday stop-list does not over-match.

4. **`TODO:` prefix on the deliberate-sync comment** in
   `cross_vendor_audit.py:263`. The note is now visible to any linter
   or grep for `TODO`.

5. **Bonus micro-add** to `test_cross_vendor_audit_exception_path_does_not_leak_canary`:
   `assert canary not in (result.api_keys_present or [])`. Pins
   `api_keys_present` to provider names, never values.

### Verified

- `pytest tests/` - **15 passed in 5.83s** on Python 3.10.12 (was 14
  in v0.5; +1 for `test_cross_vendor_audit_output_fields_are_stable`).
- All four REVIEW-V3 fast-follow items closed.
- Version bumped to `0.5.1` in `bayyinah_audit_mcp/__init__.py`.

### State

REVIEW-V3 verdict: **shippable**. Three items remain for v0.6+ and are
contract-boundary work that does not belong in this wrapper:

- Tighten `consensus` schema OR push canary requirement into lane #3's
  own test suite.
- Structured warning codes (`code: Literal["empty_file", ...]`).
- Anything the live CI matrix surfaces on first push (asyncio + 3.13
  is the highest-likelihood failure mode; remediation is documented).

The MCP server thread is paused here pending Bilal's go/no-go on
publishing to PyPI as `bayyinah-audit-mcp`.

---

## v0.5.1 part 2 (REVIEW-V4 / CROSS-VENDOR-AUDIT-V05 must-fix hotfix; third Claude)

After v0.5.1 part 1 landed (REVIEW-V3 fast-follows above), a third
Claude instance drove a cross-vendor audit pass through GPT-5 against
v0.5 per PMD v1.2 rotation discipline. GPT-5 surfaced two HIGH
findings the intra-Claude chain missed plus uncontested must-fixes on
README rendering and path-strict default safety. The uncontested
hotfix items landed in v0.5.1 immediately; the contested F-V05-002
(wrapper-vs-orchestrator canary ownership) is deferred to a Tier 1
adjudicator pass and remains open.

Source audit chain: `CROSS-VENDOR-AUDIT-V05.md` (canonical), with
`REVIEW-V4.md` preserved as a duplicate-content historical cell from
the round-naming reconciliation between the driver instance and the
second Claude on 2026-05-11.

### Uncontested must-fixes closed in v0.5.1 part 2

1. **F-V05-001 [HIGH]** -- `bayyinah_audit_mcp/tools/cross_vendor_audit.py`
   exception handler. Was `LOGGER.exception("...: %r", exc)`. The `%r`
   format echoes the full exception repr, including any secret value
   that lane #3 embedded in the message string; `LOGGER.exception` also
   attaches the traceback, which can carry the same value in local
   variable reprs. Switched to `LOGGER.error("...: %s", type(exc).__name__)`
   with explicit comment documenting the deliberate omission of
   `exc_info`. The MCP response was already clean (asserted by the v0.5
   canary test); this closes the log-side leak that the response-side
   test did not cover.

2. **F-V05-003 [MEDIUM]** -- `README.md` SSE and streamable-HTTP run
   snippets. The Security section correctly documented
   `BAYYINAH_PATH_STRICT=1` as required for network transports, but the
   visible copy-paste run examples did not export it inline. A user
   following the visible examples could bring up the server over SSE or
   streamable HTTP with strict-mode off. Inlined the export in both
   network-transport snippets so the documented behaviour is the
   default copy-paste behaviour.

3. **F-V05-008 [MEDIUM]** -- `README.md` Markdown fences. Every fenced
   code block was missing its closing fence. PyPI and GitHub renderers
   were collapsing most of the README into one giant code block,
   obscuring install, run, security, and environment guidance. Closed
   all fences. Also added the `cross-vendor` extras note clarifying
   that the extra installs vendor SDKs only, not the lane #3
   orchestrator itself.

### New test (locks F-V05-001 against regression)

`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`
-- captures `caplog` at DEBUG level, monkeypatches a fake orchestrator
that raises `ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")`,
and asserts the canary string does not appear in any log record's
message, formatted message, traceback, or `exc_text`. This is the
test surface F-V05-004 called out as missing from v0.5; closing it
here as part of the F-V05-001 hotfix rather than leaving it for v0.6.

### Verified

- `pytest tests/` -- **16 passed in 6.92s** on Python 3.10.12 (was 15
  after v0.5.1 part 1; +1 for the new caplog test).
- `pyproject.toml` and `bayyinah_audit_mcp/__init__.py` both at
  `0.5.1` (second Claude closed an earlier two-source-of-truth drift
  at the 0.5.0 → 0.5.1 transition; substrate-reconciliation finding
  class F-V05-RECON-001 is now twice-closed).
- README renders correctly: every fence pairs, BAYYINAH_PATH_STRICT
  is visible in the network-transport copy-paste examples, and the
  cross-vendor extras note is present.

### Deferred from CROSS-VENDOR-AUDIT-V05.md to v0.6 (or to adjudication)

- **F-V05-002 [HIGH, contested]** -- wrapper-side sanitization of
  allowed fields (`reason`, `consensus`, `solo_findings`,
  `validator_panel`). REVIEW-V3 deferred this to v0.6 as contract-
  boundary work that belongs in lane #3. CROSS-VENDOR-AUDIT-V05
  calls it must-fix-before-publish with a wrapper-side
  `_redact_string` + `_sanitize_for_output` patch. Adjudication
  pending; Tier 1 non-producer non-auditor (Perplexity) is the
  cleanest fit. The proposed patch is preserved verbatim in
  CROSS-VENDOR-AUDIT-V05.md so it can be applied without
  re-derivation if the adjudicator endorses the wrapper-side
  approach.
- **F-V05-004 [MEDIUM]** -- additional caplog/log-surface coverage
  on the existing exception-path test (the v0.5.1 part 2 work above
  added a parallel new test rather than modifying the existing one;
  if the adjudicator wants both tests merged, that is a v0.6 cleanup).
- **F-V05-005 [MEDIUM]** -- raw-result test covering allowed fields
  (depends on F-V05-002 adjudication).
- **F-V05-006 [LOW]** -- CI packaging check (`python -m build` plus
  `twine check dist/*` or a Markdown fence linter).
- **F-V05-007 [LOW, accept-with-rationale]** -- README cross-vendor
  extras orchestrator note. Closed as part of v0.5.1 part 2 README
  rewrite even though disposition was accept-with-rationale; the
  prose is now explicit.
- **F-V05-009 [LOW]** -- close the awaitable on the rejection branch.
- REVIEW-V3 v0.6-class items (consensus schema tightening,
  structured warning codes, CI matrix first-push results).

### State

v0.5.1 is shippable on the uncontested findings. F-V05-002
adjudication is the gating question for whether v0.6 includes
wrapper-side canary scrubbing or pushes that requirement into lane
#3's own test suite.

---

## v0.5.2 (PyPI hardening)

Triggered by Bilal's PyPI go decision. F-V05-002 from REVIEW-V3 (the
canary-inside-allowlisted-fields surface) flips from "contract-boundary
issue belonging to lane #3" to "must fix before public release"
because PyPI consumers will bring their own lane #3 implementations
the wrapper has never seen.

### Structural changes

1. **`Consensus` Pydantic model.** `consensus: Optional[Any]` on
   `CrossVendorAuditOutput` is now `Optional[Consensus]`, where
   `Consensus` carries four typed fields: `verdict` (Literal),
   `reasoning` (str, scrubbed), `agreed_findings: list[Finding]`,
   `disagreement_count: int`. Both `Consensus` and `Finding` use
   `model_config = ConfigDict(extra="ignore")` so any extra keys lane
   #3 returns are silently dropped (defense in depth atop the
   explicit allowlist normaliser already shipped in v0.3).

2. **`_scrub` defense-in-depth string redaction.** Five regex
   patterns (`sk-...`, `sk-ant-...`, `Bearer ...`, `Authorization: ...`,
   `api[_-]?key=...`) replace matches with `<REDACTED>`. Applied to
   every string-typed output: `reason`, `Consensus.reasoning`, every
   `Finding.message` and `Finding.location`. The scrub is the
   wrapper-side answer to GPT-5's V05-002 finding (canary embedded
   inside a known field would otherwise pass the allowlist).

### Tests added

- `test_cross_vendor_audit_consensus_extra_fields_dropped` - asserts
  `Consensus` constructed with extra unknown keys silently drops them.
- `test_cross_vendor_audit_scrub_redacts_canary_inside_consensus_reasoning` -
  fake orchestrator returns `Consensus(reasoning="diagnostic: key was sk-test-CANARY-...")`,
  asserts canary absent from `result.model_dump_json()`.
- `test_cross_vendor_audit_scrub_redacts_canary_inside_finding_message` -
  same for a solo finding's message field.

The three v0.3 / v0.5 / v0.5.1 canary tests still pass unchanged.

### Tests passing

`pytest tests/` - **17 passed in 2.58s** on Python 3.10.12 (was 15 in
v0.5.1; +2 new tests, the third was folded into the existing
exception-path test's assertions).

### README

New `## For PyPI consumers` section near the top documenting:
- The lane #3 contract (callable shape, expected return types).
- `BAYYINAH_PATH_STRICT=1` is REQUIRED for SSE/HTTP transport.
- Bundled `section_index.json` ships with five entries; consumers
  should point `BAYYINAH_SECTION_INDEX` at their full index.

### State

v0.5.2 is the PyPI-publishable release. F-V05-002 is closed. The two
remaining pre-tag conditions are operational, not architectural:

1. Push to a release-candidate branch and verify the GitHub Actions
   matrix (Python 3.10/3.11/3.12/3.13) is green before tagging.
2. Run `pip install -e '.[all]'` in the actual sandbox to confirm
   `anthropic`, `openai`, `google-genai`, `pdfplumber` all have wheels
   on 3.10 (REVIEW-V2 Q5).

After that, `python -m build && twine upload dist/*`.

---

## v0.5.3 (PATCH-STRESS hardening + F-V05-001 re-application; third Claude)

Triggered by Pat's pre-emptive endorsement of GPT-5's adversarial
self-stress test (`CROSS-VENDOR-AUDIT-V05-PATCH-STRESS.md`) over the
v0.5.2 narrow five-pattern wrapper-side scrub. Endorsement was a flat
yes-yes-yes against the three adjudication questions: hardened patch
regex set acceptable as drafted, env-redaction floor at 4 chars
tolerable, six lane-#3 contract requirements clean enough for
Bilal/Fraz to absorb.

### Substrate-of-record finding (regression flagged)

The v0.5.2 round inadvertently reverted the F-V05-001 LOGGER.error fix
that landed in v0.5.1 part 2. As of v0.5.2 line 384, the exception
handler was back to `LOGGER.exception("...: %r", exc)`, which echoes
the full exception repr (including args, which can carry leaked secret
values) to server logs. The v0.5.1 caplog test
`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`
was also dropped from `tests/test_tools.py` between v0.5.1 part 2 and
v0.5.2, so no test surface existed to catch the regression.

This recurrence is class F-V05-RECON-001-style drift (single-source-of-
truth violation between successive instance hand-offs). v0.5.3 closes
it by re-applying the LOGGER fix AND restoring the caplog regression
test. The drift is also logged as a process finding for the next
substrate-reconciliation pass: parallel-instance edits on the same
file class need a hand-off discipline tighter than what the current
narrative chain provides.

### Code changes

1. **`bayyinah_audit_mcp/tools/cross_vendor_audit.py` rewritten with
   layered scrubbing.** Two layers replace the narrow v0.5.2 regex:

   - **Env-bound value substitution.** `SECRET_ENV_NAMES` widened to
     nine variables covering Anthropic admin keys, Google Application
     Credentials, and the three AWS credential env vars. Floor lowered
     to `MIN_ENV_SECRET_REDACT_CHARS = 4` with
     `ENV_VALUE_REDACTION_DENYLIST = {true, false, none, null, test,
     prod, dev, local}` to bound over-firing. Flexible-whitespace
     matching via `ENV_WRAP_SEPARATOR_RE` catches multi-line wrapped
     secrets where each character is separated by whitespace or
     zero-width separators (bypass class 12 from the stress test).

   - **`REDACTION_RULES` regex tuple.** 17 rules covering 15 of the 16
     bypass classes GPT-5 surfaced: PEM private-key blocks, expanded
     Authorization-header schemes (Bearer, Basic, Token, ApiKey,
     API-Key), Cookie and Set-Cookie headers, basic-auth URLs,
     quoted-or-unquoted credential-label key-value matching covering
     JSON / query params / env-style / header-style / vendor-specific
     labels, partial-fingerprint shapes (`sk-...last4`,
     `fingerprint=...`, `sha256:...`, `last_4=...`), and vendor-prefix
     bare-value shapes (`sk-`, `sk-ant-`, `xai-`, `AIza`, `ya29.`,
     `AKIA`/`ASIA`, GitHub `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`,
     `github_pat_`, Slack `xox[baprs]-`, bare three-segment JWTs).
     Redaction marker is `<REDACTED>` for consistency with v0.5.2 test
     expectations.

   - **`_scrub` is now layered.** Env-bound values get substituted
     first (catches multi-line wrapping at character resolution), then
     the REDACTION_RULES tuple runs in order. All existing call sites
     (`_scrub_optional`, `_normalize_finding`, `_normalize_consensus`,
     the exception-path `reason`, the ImportError-path `reason`)
     inherit the broader coverage without changing their call shape.

2. **F-V05-001 re-applied at the exception handler.**
   `LOGGER.exception("...: %r", exc)` swapped back to
   `LOGGER.error("...: %s", type(exc).__name__)` with comment
   documenting the deliberate omission of `exc_info` and the v0.5.2
   regression history.

3. **F-V05-009 closed (nice-to-have from CROSS-VENDOR-AUDIT-V05).**
   The awaitable rejection branch now calls `result.close()` if the
   coroutine exposes it, suppressing "coroutine was never awaited"
   runtime warnings.

### Tests added

1. **`test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs`**
   restored. Captures `caplog` at DEBUG and asserts the canary string
   is absent from every record's `message`, formatted message,
   traceback, and `exc_text`.

2. **`test_cross_vendor_audit_hardened_patch_closes_bypass_class`**
   parameterized across 15 bypass classes:

   - `custom_vendor_key_label` (xai-prefixed value in XAI_KEY label).
   - `anthropic_admin_key_label` (ANTHROPIC_ADMIN_KEY label).
   - `google_oauth_bare_token` (`ya29.` prefix).
   - `aws_access_key_id_label` (AWS_ACCESS_KEY_ID label + AKIA prefix).
   - `bare_jwt` (three-segment base64url).
   - `authorization_token_scheme` (Authorization: Token scheme).
   - `cookie_session` (Cookie: session= + csrftoken).
   - `oauth_code_state` (URL query with code= and state= params).
   - `url_query_key_param` (URL query with bare `key=` not `api_key=`).
   - `basic_auth_url` (`https://user:password@host` form).
   - `quoted_json_api_key` (quoted JSON key-value).
   - `truncated_fingerprint_echo` (`sk-...last4` fingerprint shape).
   - `pem_private_key_block` (full BEGIN/END PRIVATE KEY block).
   - `github_personal_access_token` (`ghp_` prefix).
   - `slack_bot_token` (`xoxb-` prefix).

   Each case asserts the substring `CANARY` is absent from the dumped
   output and that `<REDACTED>` is present. The 16th class (arbitrary
   unlabeled opaque values) is owned by lane #3 per the contract spec.

### Documentation added

- **`LANE-3-CONTRACT-V05.md`** -- new standalone document at the
  workspace root. Specifies the six contract requirements
  (LANE3-C1 through LANE3-C6) lane #3's own test suite must prove
  to compensate for the 16th bypass class plus structural
  responsibilities the wrapper cannot fulfill from its position.
  Framed as a deliverable for BayyinahEnterprise (Bilal, Fraz) and
  for third-party `bayyinah_audit_orchestrator` providers shipping
  via PyPI.

### Tests passing

`pytest tests/` -- **33 passed in 5.54s** on Python 3.10.12 (was 17 in
v0.5.2; +16 tests broken down as: +1 restored caplog test for
F-V05-001, +15 parameterized hardened-bypass-class coverage cases).

### Version

Bumped from `0.5.2` to `0.5.3` in both `pyproject.toml` and
`bayyinah_audit_mcp/__init__.py`. F-V05-RECON-001 drift check: both
files match at `0.5.3`.

### Deferred

- Adjudicator validation. Pat pre-emptively endorsed the three
  adjudication questions in chat ("Assume all yes for the time being,
  mate!"). The audit-chain entry that records this pre-emptive
  adjudication is the conversation transcript and this narrative
  section; if a formal cross-vendor adjudicator pass (Perplexity Tier
  1, Gemini/Grok Tier 2) is later run, that document supersedes the
  pre-emptive endorsement.
- Lane #3 adoption of LANE-3-CONTRACT-V05.md. Bilal and Fraz own this
  on the `bayyinah_audit_orchestrator` repo side.
- CI matrix and `pip install -e '.[all]'` verification on 3.10. The
  two operational pre-tag conditions from v0.5.2 still apply.

### State

v0.5.3 is publication-ready on the structural axis. Wrapper-side
coverage is at parity with GPT-5's hardened patch design plus the
F-V05-001 log-surface fix. Lane #3 has a concrete six-requirement
contract to integrate. Operational pre-tag conditions (CI matrix
green on 3.10-3.13, pip install verification) inherited from v0.5.2.

---

## v0.5.4 (post-REVIEW-V5 nice-to-haves)

Three items from REVIEW-V5's v0.5.4 punch list landed directly (no
ChatGPT round needed; the changes were small and self-contained).

### Changes

1. **`Consensus.metadata` forward-compat hatch.** New
   `metadata: dict[str, Any] = Field(default_factory=dict)` field on
   `Consensus`. Lane #3 implementations that surface fields beyond
   the four canonical ones can now pass them through without losing
   data. Paired with new `_scrub_dict` helper that recursively walks
   dict / list / tuple structures and applies `_scrub` to every string
   leaf - so a credential nested inside `metadata.diagnostics.headers_seen[1]`
   is still redacted on the way out.

2. **Four additional vendor prefixes** added to `REDACTION_RULES`:
   `pplx-` (Perplexity), `gsk_` (Groq), `r8_` (Replicate), `hf_`
   (HuggingFace). Closes the v0.6 candidate item from REVIEW-V5
   ahead of schedule. Lane #3 still owns the canonical non-leak
   guarantee for these vendors; the wrapper just catches the most
   common bare-value forms.

3. **`LANE-3-CONTRACT-V05.md` updated** with a closed-form list of
   vendor prefixes the wrapper does NOT catch (Cohere, Mistral,
   Together AI, Fireworks AI, DeepSeek, custom in-house orchestrators).
   Closes the third-party orchestrator author's awareness gap.

### Tests added

- `test_cross_vendor_audit_metadata_hatch_scrubs_nested_canary` -
  verifies `_scrub_dict` walks 3-level-deep metadata
  (`metadata.diagnostics.headers_seen[1]`) and redacts an embedded
  Bearer token. Asserts non-secret fields like `iteration_id` survive.
- 4 new entries in `HARDENED_BYPASS_CLASS_CASES` parametrize the
  existing `test_cross_vendor_audit_hardened_patch_closes_bypass_class`
  test over the new vendor prefixes.

### Tests passing

`pytest tests/` - **38 passed in 3.86s** on Python 3.10.12 (was 33 in
v0.5.3; +4 vendor-prefix bypass cases + 1 metadata-scrub test).

### Open / deferred to v0.6

- `BAYYINAH_EXTRA_SECRET_PATTERNS` env-var configurability for the
  REDACTION_RULES tuple.
- Integrate `_skeptical-persona-suffix.py` (the second Claude's
  draft) into `tools/cross_model_audit/reviewers.py` so the v0.5.2 ->
  v0.5.3 self-stress cycle becomes a tag-push CI workflow instead of
  a manual adversarial pass.

## v0.5.5: F-V05-DICT-CYCLE-LOOP defense-in-depth cycle guard

Closes the single REVIEW-V6 finding tagged "Required for v0.5.4 ship"
that did not actually land in v0.5.4. The Round 38 third-instance
audit (Cowork Claude, 2026-05-11) caught REVIEW-V6's verdict ambiguity
on substrate read: REVIEW-V6 said "SHIP at v0.5.4 once CI matrix passes"
AND "Required for v0.5.4 ship: F-V05-DICT-CYCLE-LOOP", but the cycle
guard was absent from `_scrub_dict` in v0.5.4 substrate. v0.5.5 closes
the loop.

### Changes

1. **`_scrub_dict` cycle guard.** `bayyinah_audit_mcp/tools/cross_vendor_audit.py`
   `_scrub_dict` now accepts an optional `_seen: set[int] | None = None`
   parameter. On entry to a dict / list / tuple container, the function
   checks `id(value)` against `_seen`; on a hit, returns the literal
   sentinel string `"<cycle>"` rather than recursing. The seen-set is
   propagated via the union operator (`_seen | {container_id}`) per
   recursion frame, so sibling containers sharing the same memory
   address do not poison each other - only true cycles on the SAME
   ancestor path fire the sentinel. Per-call default of `None` plus
   fresh set construction on first entry keeps the API surface
   backward-compatible at the call-site level.

2. **Test count: 38 -> 43.** Five new tests covering: self-referential
   dict, self-referential list, indirect cycle through nested dicts,
   sibling reuse is NOT a cycle (negative test), and acyclic input
   still redacts leaves (regression guard for v0.5.4 behaviour).

### Audit-chain provenance

Substrate-of-record: Round 38 audit recorded in this session's
`BUILD-PLAN-v1.0-to-v1.1-RECONCILIATION.md`. The finding's MEDIUM
severity is calibrated to the contract-bound nature of the lane #3
interface (JSON-serialisable output, no cycles by construction); the
guard is defense-in-depth against a misbehaving or adversarial
lane-#3 impl, not a load-bearing fix against a real attack surface.

### Tests passing

`pytest tests/` - **43 passed in 0.37s** on Python 3.10.12 (was 38 in
v0.5.4; +5 cycle-guard tests).

### Version

`pyproject.toml` and `bayyinah_audit_mcp/__init__.py` both bumped to
`0.5.5`.

### Sentinel-string choice rationale

`"<cycle>"` rather than `None` because:
- `None` is a valid JSON null that lane #3 might legitimately return
  for an empty metadata field; an audit-log reader inspecting the
  redacted output should not have to disambiguate "real null" from
  "cycle short-circuit."
- `"<cycle>"` is visually distinct from `"<REDACTED>"` so a reviewer
  reading the redacted dump immediately sees "this dict had a self-
  reference" rather than "this dict had a secret here."
- A string sentinel preserves the type signature (the redacted result
  is still walkable / serialisable / dumpable through `model_dump_json`
  without further branching).

### Open / deferred to v0.6

(unchanged from v0.5.4 list)