# REVIEW-V2: v0.4 delta review of Bayyinah Audit MCP Server

Reviewer: second Claude. Picked up `V04-READY.txt`. Confirmed `pytest tests/` is 8/8 green locally on Python 3.10.12 against the installed `mcp==1.27.1` + `pydantic==2.13.4` + `typing_extensions>=4.7` stack.

State summary: v0.3 closed all five REVIEW-V1 must-fixes (verified by code, not just the cover note: `server.py` is import-side-effect-free, `BAYYINAH_PATH_STRICT` is wired into `config.resolve_path` with `is_relative_to`, `cross_vendor_audit` is now Pydantic-output + scrubbed exception text, `furqan_lint` has the `error` branch at lines 248-249, `max_output_chars` truncation is on every return path). v0.4 added `tests/test_tools.py` (200 lines, 7 functional tests), bumped to `requires-python = ">=3.10"`, declared `typing_extensions>=4.7` explicitly, and replaced the test-smoke private-API introspection with `asyncio.run(mcp.list_tools())`. Nice unsolicited bonus: every tool output is now a Pydantic model, so the P2 `total=False` contract loosening from PATCHES.md is gone.

This review is structured around your `V04-READY.txt` priorities.

## Priority 1: stronger canary assertion on `cross_vendor_audit`

You are right that the existing test does not actually exercise the leak path you fixed in v0.3. Reading `tests/test_tools.py::test_cross_vendor_audit_missing_lane3_returns_unavailable_without_key_values`:

The test forces `__import__("bayyinah_audit_orchestrator")` to raise `ImportError`. The function then returns `status="unavailable"` at line 217 of `cross_vendor_audit.py` BEFORE `_api_key_providers_present()` is ever called. The secret never enters the function's body. The line-165 assertion `secret_value not in result.model_dump_json()` is satisfied trivially, not because the scrubbing works.

The path you actually want to test is the v0.3 Issue 3b fix: orchestrator IS importable, it raises an exception, the exception handler must not surface the original `str(exc)`. Concrete test:

```python
def test_cross_vendor_audit_exception_path_does_not_leak_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import sys, types
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-must-never-appear-anywhere"
    monkeypatch.setenv("ANTHROPIC_API_KEY", canary)

    fake = types.ModuleType("bayyinah_audit_orchestrator")
    def run_cross_vendor_audit(**kwargs):
        # Worst case: orchestrator echoes its env or kwargs into the exception.
        import os
        raise ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")
    fake.run_cross_vendor_audit = run_cross_vendor_audit
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    assert result.status == "error"
    assert "ValueError" in (result.reason or "")
    # The canary must not appear anywhere in the structured response.
    assert canary not in result.model_dump_json()
    # And the reason must not echo str(exc).
    assert "boom" not in (result.reason or "")
```

Add a parallel `_does_not_leak_via_raw_result` test for the result-echo path: have the fake orchestrator RETURN a dict containing `{"raw_log": "Authorization: Bearer " + canary, "status": "ok"}` and assert the canary is absent from `result.model_dump_json()`. This exercises the v0.3 allowlist-based `_normalize_result` (Issue 3c). The current code only pulls `status`, `reason`, `consensus`, `solo_findings`, and `validator_panel` from the result, so the `raw_log` key should be dropped, but a test makes that contract a guarantee.

One incidental note while reading this code: `_select_callable` instantiates `BayyinahAuditOrchestrator()` with no args inside the function body. If the real lane #3 class needs constructor args, this silently fails over to "no compatible callable." A pinned-version test against the actual lane #3 module would catch that; not blocking for v0.4.

## Priority 2: empty-file warning test on `audit_artifact`

The v0.3 code has the distinction at `audit_artifact.py` line 138-139 ("...read but the file was empty.") and the separate "no artifact_path was provided" branch at 142-150. No test covers either. Recipe:

```python
def test_audit_artifact_warns_when_path_resolves_to_empty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")

    result = bayyinah_audit_artifact(
        AuditArtifactInput(
            artifact_path="empty.txt",
            include_framework_prompt=False,
        )
    )

    assert result["status"] == "ok"
    warning_text = " ".join(result["warnings"]).lower()
    assert "empty" in warning_text
    # And the generic "no artifact" warning should NOT also fire.
    assert "no artifact_text or artifact_path was provided" not in " ".join(result["warnings"])


def test_audit_artifact_warns_when_neither_text_nor_path_is_given() -> None:
    result = bayyinah_audit_artifact(
        AuditArtifactInput(include_framework_prompt=False)
    )

    warning_text = " ".join(result["warnings"]).lower()
    assert "no artifact_text or artifact_path was provided" in " ".join(result["warnings"])
    assert "empty" not in warning_text
```

The pair locks the two warnings as distinguishable.

## Priority 3: asyncio + `mcp.list_tools()` across 3.10-3.13

Verdict: low risk to ship to the matrix as-is.

`asyncio.run()` creates a fresh event loop, runs the coroutine, closes the loop. It is the supported pattern on every Python in your matrix and has not changed in 3.13. The 3.12+ "no current event loop" deprecation only triggers on `asyncio.get_event_loop()`, which neither the test nor (per a quick search of the MCP SDK 1.27 source) `FastMCP.list_tools()` calls in a sync context. The SDK uses `asyncio.get_running_loop()` for any internal loop reference, which is correct inside a coroutine.

Two things to watch for if the matrix surprises you:

- A `DeprecationWarning` (not error) about coroutine cleanup if the test exits before all sub-tasks finalise. Cosmetic. Filter via `filterwarnings` in `pyproject.toml` if it gets noisy.
- If MCP SDK 1.x changes `list_tools` to require a running server context in a future minor, the test will fail with `RuntimeError: not connected`. Cheap defence: have `_registered_tool_names` (the v0.1 introspection helper) live on as a fallback, marked deprecated.

If you want a belt-and-braces version, install `pytest-asyncio` and convert to `@pytest_asyncio.fixture` + `async def test_...`. Not necessary for v0.4 since the matrix CI will tell us if anything breaks.

## Priority 4: split the check-attributions combo test

`test_check_attributions_flags_unknown_section_ignores_month_year_and_warns_on_missing_corpus` is three properties at once. When it fails, the failure message will not tell you which property broke. Recommend splitting into:

- `test_check_attributions_flags_unknown_section_ref` - artifact contains `§99.99`, no corpus, assert `"99.99" in unresolved_section_refs`.
- `test_check_attributions_ignores_month_and_weekday_words` - artifact mentions "December 2024" and "Monday 2025", assert neither appears in `checked_citations`. (Add a weekday case to actually exercise the second half of `DATE_WORD_STOPLIST`; right now only months are tested.)
- `test_check_attributions_warns_on_missing_corpus` - artifact has any citation-shaped string, corpus_path points at a non-existent file, assert the warning text mentions the path.

Each one writes its own `artifact.txt` under `tmp_path` so failures localise.

## Priority 5: optional-extras PyPI sanity on 3.10

CI matrix at `.github/workflows/ci.yml` already runs `pip install -e '.[all]'` on all four Python versions, so any wheel-availability regression for `anthropic>=0.54`, `openai>=1.80`, `google-genai>=1.20`, or `pdfplumber>=0.11` on 3.10 will turn the matrix red on first push. Acceptable; no upfront pinning needed. If you want to be conservative, add an upper bound (e.g. `anthropic>=0.54,<1`) on each, but that creates maintenance work to keep the bounds fresh.

I did not retry the install in sandbox (pip timed out earlier on the wider install). Defer to CI.

## Other observations on v0.4

- `tests/test_smoke.py` shrank from 64 lines to 24. Good. The drop of `_registered_tool_names` is clean.
- `pyproject.toml` now declares `typing_extensions>=4.7` and `requires-python = ">=3.10"`. Consistent with the matrix.
- `CrossVendorAuditOutput`, `FurqanLintOutput`, `AttributionCheckOutput` are all Pydantic now. P2 from `PATCHES.md` is resolved as a side effect.
- `check_attributions._load_corpus_text` returns `(text, warnings)` and the tool now emits an `"ok_with_warnings"` status. Worth a one-line test asserting that exact status.
- `cross_vendor_audit` is now `def`, not `async def`. The async-result branch returns `status="error"` with the message "lane #3 orchestrator returned an awaitable...". If lane #3 ever ships async-first, this becomes a contract problem; reasonable as v0.4 but worth a TODO comment.

No regressions spotted vs v0.3.

## Punch list

### Must fix before v1.0

1. Add the `cross_vendor_audit` exception-path canary test (Priority 1 above). The current test does not actually verify the leak fix.
2. Add the `cross_vendor_audit` raw-result allowlist test (the parallel test in Priority 1). Locks in the Issue 3c contract.

### Should fix before publishing v0.4 tag

3. Add the two empty-file warning tests in `audit_artifact` (Priority 2).
4. Add a weekday case to the month-year stop-list test (Priority 4) - `DATE_WORD_STOPLIST` covers weekdays but no test exercises that half.

### Nice to have

5. Split the `check_attributions` combo test into three (Priority 4).
6. Add a one-liner asserting `status == "ok_with_warnings"` when the corpus warns.
7. TODO comment on the `cross_vendor_audit` async-rejection branch explaining the deliberate sync contract.
8. Document in `README.md` that `BAYYINAH_PATH_STRICT=1` is required when running the SSE/HTTP transport (the code is there; the README is silent on it).
9. Optional: pin upper bounds on the four optional extras to insulate against breaking releases.

Carry on. Drop a follow-up `V05-READY.txt` when ChatGPT comes back with the tests, and I will do another delta pass.
