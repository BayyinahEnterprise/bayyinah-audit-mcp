# Skeptical-persona suffix: design rationale

Author: second Claude, 2026-05-11.
Companion to: `_skeptical-persona-suffix.py` in the same folder.
Inputs consumed: the current generic suffix at `tools/cross_model_audit/reviewers.py:71` (via `_skeptical-reviewer-context.py`), AGENT 3's calibration examples (F-V05-001 should-catch, F-V05-RECON-003 false-positive guardrail), and REVIEW-V1.md / REVIEW-V2.md / REVIEW-V3.md as voice corpus.

## What the current suffix gets right

Five pattern-names already in place are good (claim-vs-diff, wrong-reason tests, contract drift via test change, empty edge cases, doc-vs-code drift). The `reviewer_id` discipline is correct. The "treat consensus as suspect" framing is correct.

## What the current suffix is missing

The patterns are named but not actionable. A model reading them gets a vibe rather than a recipe. F-V05-001 (the LOGGER.exception(`%r`, exc) leak) is exactly the class of finding "tests that pass for the wrong reason" was meant to catch, and yet REVIEW-V3 and the producer reviewers both missed it - because the suffix told them to look for the pattern without telling them HOW to detect it. The replacement turns each pattern into a procedural check.

There is also no false-positive guard. The persona, told only to be skeptical, has no signal about when to stand down. AGENT 3 flagged F-V05-RECON-003 as the prototypical over-fire: optional-extras pinning was deferred with written cost analysis plus a loud CI detection mechanism, and a naive skeptical reviewer would raise it anyway. The replacement adds heuristic 3 to prevent this class of waste.

## Design choices, in order

### Heuristic 1: surface-mismatch (the F-V05-001 catch)

The actionable recipe: for each new test, NAME the contract, then ask where else the contract could be violated. Tests assert on one surface; the same data often flows through sibling surfaces. The persona should mechanically enumerate sibling surfaces (logs, traces, files, exception messages, stderr, subprocess output, audit cells) before clearing a test-backed claim.

I included the mechanism-string suggestions because the aggregator buckets by string equality across reviewers. If the skeptical persona produces `log_surface_unscrubbed` and an agreeable reviewer independently produces the same string, the aggregator can recognise consensus. Without a shared vocabulary, the same finding shows up under three different mechanism names and the aggregator misses the consensus.

### Heuristic 2: narrative-versus-code-state (the F-V05-RECON-001 class)

The third Claude's pyproject-versus-`__init__` drift catch is the canonical case. The procedure: read narrative claims, locate diff support, raise if absent. This pattern recurred at v0.5.1 (I closed the second instance manually). A persona that ran this check on the v0.5 → v0.5.1 diff would have caught it before I had to.

Note: the heuristic explicitly names `V0*-READY.txt` as a narrative source. The current ecosystem has multiple narrative artifact types and the persona should treat all of them as claims-to-verify.

### Heuristic 3: deferral guardrail (the F-V05-RECON-003 anti-pattern)

This is the highest-leverage addition. Without it, a skeptical persona over-fires on every deferred item and the team spends adjudication cycles re-adjudicating settled questions.

The two-part test (written rationale AND loud detection mechanism) maps directly onto AGENT 3's framing. I kept the exact phrasing because it's already in the team's vocabulary from the v0.5 reconciliation.

The "process finding versus substantive finding" distinction is the real value. If the persona detects a deferral lacking rationale, the correct fix is "write the rationale" - a process action, not a code change. Channeling it as a substantive finding produces a meeting; channeling it as a process finding produces a one-line note.

### Heuristic 4: no-restate rule

The persona has access to all artifact history. It must not surface items already in PATCHES.md or prior REVIEW/READY/RECON files as new findings. This is the second-highest-leverage addition because consensus inflation on settled items is the most common failure mode of multi-vendor review systems.

The aggregator's mechanism-bucketing also depends on this. If the skeptical persona restates an existing finding under a slightly different mechanism string, the aggregator may treat it as a new finding rather than as concurrence with the original.

### Tone / format constraints

- ASCII hyphen only. The project's standing instruction (Pat's rule) is no em or en dashes; the suffix must propagate this to the persona's output so the aggregator's findings file is publish-ready without postprocessing.
- JSON only, no prose. Already in the base prompt; the suffix repeats it because some models drift on prose-output behaviour when given a persona prompt.
- Mechanism strings as gap-nouns, not symptom-phrases. This is the aggregator-cooperation discipline.
- Confidence calibration with the five-minute-failing-test test. This anchors HIGH-confidence findings to a verifiable criterion and prevents the persona from inflating confidence as a side effect of "be skeptical" framing.

### Verdict policy

The base prompt allows `ship | ship_with_caveats | hold` without guidance on when to use which. A skeptical persona without verdict guidance will default to `hold` when uncertain, which produces unnecessary release friction.

The policy I added: `ship` requires no HIGH-severity findings AND no MED-severity findings on the secret-leak or contract-violation surface. `ship_with_caveats` is the default for everything else. `hold` is reserved for findings you would refuse to publish over personally.

This makes `ship_with_caveats` the safe expression of skepticism (raise the findings, let the team decide whether they block) and reserves `hold` for genuine line-in-the-sand calls. The line-in-the-sand framing mirrors what a senior human reviewer would do.

## What I deliberately did NOT include

- **Specific finding examples in the prompt.** Putting F-V05-001 verbatim into the suffix would anchor every future skeptical run on that specific shape, which is a worse generalisation than the heuristic. The examples live in the rationale doc and in the historical artifact set; the prompt encodes the pattern.

- **Vendor-specific instructions.** The wiring routes the skeptical persona through Claude, OpenAI, or Gemini depending on which key is present. The suffix is vendor-agnostic by construction; injecting Claude-specific or GPT-specific phrasing would tilt findings toward whichever vendor ran the persona that day.

- **Token budget guidance.** The base prompt's output contract (JSON object, single response) already constrains output length. Adding a token budget invites the persona to either pad to fill it or truncate findings to fit.

- **Eval set bootstrapping.** AGENT 3 mentioned that REVIEW-V2, REVIEW-V3, CROSS-VENDOR-AUDIT-V05, and PATCHES.md could be pulled into the persona's eval set wholesale. This is the right move for evaluating the persona's quality post-deployment, but it does not belong in the suffix itself. The eval is a separate workflow.

## Integration

One-line change in `tools/cross_model_audit/reviewers.py`: replace the existing `_SKEPTICAL_SYSTEM_SUFFIX = "..."` block (lines 46-56) with the constant from `_skeptical-persona-suffix.py`. No other changes needed; the wiring in `_skeptical_review` (lines 59-78) continues to work.

After integration, recommended evaluation:

1. Run the new persona against the v0.5 release as a regression check. The persona should surface F-V05-001 (the `%r` leak) at HIGH severity with `log_surface_unscrubbed` or close cognate mechanism string. If it does, the heuristic 1 wiring is calibrated. If it does not, the suffix needs another pass.
2. Run the new persona against the v0.5.1 release. The persona should NOT raise the optional-extras pinning question (heuristic 3 should suppress it). If it does, heuristic 3 needs strengthening.
3. The aggregator should bucket the persona's `log_surface_unscrubbed` finding alongside GPT-5's F-V05-001 if both runs produce the same mechanism string. This is the cross-vendor consensus signal the pipeline is designed to surface.

## Open questions for the team

- **Should the persona's verdict outweigh the agreeable reviewers' verdict in the aggregator?** Currently the aggregator takes "most cautious" verdict per AGENT 1's notes. A `hold` from the skeptical persona therefore propagates. Whether this is the right policy depends on operator tolerance for false-positive holds.
- **Should the persona run on every release, or only on releases tagged for public publication?** The cost is ~$0.50 per run per AGENT 1's accounting. For internal-only releases the value-add may be marginal.

Both deferrable; neither blocks integration.

## Files dropped

- `_skeptical-persona-suffix.py` - the drop-in suffix.
- `_skeptical-persona-rationale.md` - this file.

Both prefixed with underscore to mark them as transient context files. Delete after integration if desired.
