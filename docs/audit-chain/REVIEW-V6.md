# REVIEW-V6: v0.5.4 verification against the v0.5.4 prompt spec

Reviewer: second Claude. Picked up `V05_4-READY.txt`, ran `pytest tests/` locally (38/38 pass on Python 3.10.12, 5.20s), then walked each item in the v0.5.4 prompt I drafted on 2026-05-11 against the implementation AGENT 1 produced via direct-edit.

**Verdict: SHIP at v0.5.4 once CI matrix passes.** No regressions, no functional gaps, no security drift. Five drift points from the spec, three substantive and two cosmetic, listed below in order of materiality. None block publication. Two are worth folding into a v0.5.5 hygiene patch.

## Per-spec-item verification

### 1. `Consensus.metadata` forward-compat hatch

Spec: Add `metadata: dict[str, Any] = Field(default_factory=dict)` as the last field of `Consensus`.

Status: **landed correctly**. `cross_vendor_audit.py` line 287. Default-factory wired right. `_normalize_consensus` handles both branches (line 547 for `Consensus` input, line 568-569 for dict input). Confirmed.

### 2. Dispatching `_scrub`

Spec: Rename `_scrub(text: str) -> str` to `_scrub_text`; add public `_scrub(value: Any) -> Any` that dispatches on type.

Status: **divergence (acceptable)**. AGENT 1 kept `_scrub(text: str)` as-is and added a separate `_scrub_dict(value: Any) -> Any` at line 376 that recursively walks dict/list/tuple and delegates strings to `_scrub`. Functionally equivalent. AGENT 1's choice is arguably cleaner: the function names declare the type they handle, and call sites read explicitly (`_scrub_dict(value.metadata)`). I would not ask for a rewrite.

One bonus: AGENT 1 added `tuple` handling at line 392-393 that my spec did not require. Sensible defensive coding since Python orchestrators might return tuples even though JSON has no tuple type.

### 3. Vendor-prefix additions to `REDACTION_RULES`

Spec: Four new patterns: `pplx-`, `gsk_`, `r8_`, `hf_`.

Status: **landed correctly**. Lines 204-216. Each pattern uses `\b...\b` word boundaries and a `{20,}` length floor. Cross-checked against my spec:

| Pattern | My spec | Actual | Match |
|---|---|---|---|
| Perplexity | `\bpplx-[A-Za-z0-9_\-]{20,}\b` | `\bpplx-[A-Za-z0-9_\-]{20,}\b` | exact |
| Groq | `\bgsk_[A-Za-z0-9]{20,}\b` | `\bgsk_[A-Za-z0-9_\-]{20,}\b` | wider |
| Replicate | `\br8_[A-Za-z0-9]{30,}\b` | `\br8_[A-Za-z0-9_\-]{20,}\b` | wider character class, looser length floor |
| HuggingFace | `\bhf_[A-Za-z0-9]{20,}\b` | `\bhf_[A-Za-z0-9_\-]{20,}\b` | wider |

AGENT 1 normalised all four to the same `[A-Za-z0-9_\-]{20,}` body. Wider character classes catch more legitimate key shapes; the {20,} length floor is conservative on Replicate (real keys are 40+ chars) but errs toward false-positive-on-short-strings, not false-negative-on-real-keys. Better than the spec.

### 4. Metadata-scrub test coverage

Spec: Five new tests at the end of the cross_vendor_audit block:

- `test_..._consensus_metadata_passes_through_scrub_clean`
- `test_..._consensus_metadata_scrubs_canary_in_string_value`
- `test_..._consensus_metadata_scrubs_canary_in_nested_dict`
- `test_..._consensus_metadata_scrubs_canary_in_list`
- Parametrize add: 4 new bypass-class cases

Status: **divergence (substantive)**. AGENT 1 consolidated four metadata tests into one (`test_cross_vendor_audit_metadata_hatch_scrubs_nested_canary`, line 620). The single test exercises:

- Nested dict surface (`metadata.diagnostics.audit_log[1].note`, three levels deep, sk-canary).
- List-in-metadata surface (`metadata.diagnostics.audit_log` is a list of dicts).
- Authorization header surface (`headers_seen[1]` = `f"Authorization: Bearer {canary}"`).
- Positive assertion (`iteration_id` preserved through scrub).

What is missing:

a. **Pure-passthrough baseline.** No test where `metadata` contains a clean payload and the assertion is "structure preserved, nothing redacted." Without it, a regression that accidentally over-scrubs (e.g., redacts every value) would still let the consolidated test pass because the consolidated test only checks the canary path. Five-minute fix.

b. **Vendor-prefix bare value inside metadata.** The new `pplx-`, `gsk_`, `r8_`, `hf_` patterns are exercised by the parametrize test (which routes through `consensus.reasoning` and `finding.message`), but NOT through `metadata`. A test that puts `metadata = {"trace": "key=pplx-CANARY...20chars"}` and asserts the canary is absent would lock the metadata path against vendor-prefix regression. Five-minute fix.

Parametrize add for the 4 new bypass classes: **landed** at lines 537-555. Cases named `perplexity_api_key`, `groq_api_key`, `replicate_api_key`, `huggingface_api_key`. Confirmed all four pass.

### 5. `LANE-3-CONTRACT-V05.md` vendor-prefix gap section

Spec: New "## Vendor prefixes the wrapper does NOT recognize structurally" section listing Cohere, Mistral, DeepSeek (covered by `sk-`), Perplexity/Groq/Replicate/HuggingFace (added in v0.5.4), plus orchestrator-author note.

Status: **landed with one factual error**. Section at line 162 ("Vendor prefixes the wrapper does NOT catch (lane #3 ownership)"). Lists Cohere, Mistral, Together AI, Fireworks AI, DeepSeek, custom in-house orchestrators.

The error: **DeepSeek uses `sk-...` keys**. The existing `\bsk-[A-Za-z0-9_\-.]{8,}\b` pattern at line 168 of `cross_vendor_audit.py` catches DeepSeek bare values structurally. The contract doc says DeepSeek is "opaque, label-only at the wrapper" - that is factually wrong; DeepSeek bare values get caught wrapper-side.

One-line doc fix: move DeepSeek to the "already covered" list with a note "covered by the OpenAI-shape `sk-...` prefix rule."

### 6. Version + marker

Spec: `__version__ = "0.5.4"` in `__init__.py`; `version = "0.5.4"` in `pyproject.toml`; `V05_4-READY.txt` with status `38 passed`.

Status: **all three landed**. Version-string consistency holds. V05_4-READY.txt also includes a rationale paragraph for the direct-edit decision, which is the right discipline.

## Two new findings I noticed while reading the code

### F-V05-DICT-KEY-PASSTHROUGH (LOW)

`_scrub_dict` at line 389: `return {k: _scrub_dict(v) for k, v in value.items()}`. The dict keys (`k`) are NOT passed through `_scrub`. If lane #3 returns `metadata = {"sk-CANARY-must-not-leak": "decoy-value"}`, the canary leaks via the key name.

This is a theoretical attack surface (lane #3 would have to put a secret in a key name, which is unusual), but defensible to close. Fix: scrub keys too if they are strings. Five-line patch. Worth a v0.5.5 hygiene round.

### F-V05-DICT-CYCLE-LOOP (LOW)

`_scrub_dict` has no cycle detection. AGENT 1's docstring at line 383 acknowledges this: "Cycles in the input would loop forever; lane #3 is expected to return JSON-serialisable structures (no cycles by construction)."

The contract guard is correct but not enforced. If lane #3 ever returns a cyclic structure (a debug snapshot of an object graph, for instance), the wrapper hangs the MCP server. A one-line `seen: set[int]` recursion guard with `id()` membership check would close this. Lower priority than F-V05-DICT-KEY-PASSTHROUGH since lane #3 is contractually-bound to JSON-serialisable output.

## Process note

The direct-edit decision diverged from Pat's "Put chatgpt to work!" instruction. AGENT 1 surfaced it explicitly in V05_4-READY.txt lines 21-24 with the rationale "small and self-contained enough that round-tripping ChatGPT would have added latency." Defensible engineering call but a divergence from instruction that you (Pat) should be aware of for future rounds.

If the audit chain is meant to function as a provenance document with strict producer-vendor rotation (per the third Claude's PMD v1.2 framing), v0.5.4 broke the rotation. v0.5.2-v0.5.3 alternated (Claude produced v0.5.2, GPT-5 stress-tested it, Claude produced v0.5.3). v0.5.4 is pure Claude. The next round (v0.5.5 hygiene patch with the two LOW findings above, plus the pure-passthrough metadata test, plus the DeepSeek doc fix) is a natural place to put ChatGPT back in the loop.

## Punch list

### Required for v0.5.4 ship

Nothing.

### Recommended for v0.5.5 (small hygiene round, good ChatGPT candidate)

1. Add the `test_..._consensus_metadata_passes_through_scrub_clean` baseline test (~5 lines).
2. Add the `test_..._consensus_metadata_scrubs_vendor_prefix_in_value` test for the new `pplx-`/`gsk_`/`r8_`/`hf_` prefixes inside metadata.
3. Fix DeepSeek's classification in `LANE-3-CONTRACT-V05.md` (move to covered list, one-line note).
4. F-V05-DICT-KEY-PASSTHROUGH: scrub dict keys in `_scrub_dict` if they are strings.
5. F-V05-DICT-CYCLE-LOOP: add `seen: set[int]` recursion guard with `id()` membership check.

### v0.6 candidates (still open from REVIEW-V5)

6. `BAYYINAH_EXTRA_SECRET_PATTERNS` env-var for runtime regex extensibility.
7. Integration of `_skeptical-persona-suffix.py` into `tools/cross_model_audit/reviewers.py`.

## Closing

v0.5.4 is a clean implementation. AGENT 1 made one architectural choice that diverges from my spec (`_scrub_dict` as a separate function rather than `_scrub` dispatching on type) and one test-coverage choice (consolidate four metadata tests into one). Both are defensible. The two new findings I surfaced are LOW-severity hygiene, not blockers.

The audit chain now goes V1 (intra-Claude) → V2 (intra-Claude) → V3 (intra-Claude) → V4 (GPT-5 cross-vendor) → V5 (intra-Claude) → V6 (intra-Claude verification). v0.5.5 is the natural place to put ChatGPT back in the producer rotation.

Carry on. Reply via Pat.
