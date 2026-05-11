# Lane #3 contract: canary non-leak requirements

Authored by: third Claude (Cowork driver), 2026-05-11, against
`CROSS-VENDOR-AUDIT-V05-PATCH-STRESS.md` GPT-5 stress test plus pre-emptive
adjudication endorsement by the project lead (Pat Estes, Estes Strategy
Insights LLC).

Audience: BayyinahEnterprise lane #3 implementers (Bilal Syed Arfeen, Fraz
Ashraf), or any third-party `bayyinah_audit_orchestrator` provider who
ships a module that the MCP server's `bayyinah_cross_vendor_audit` will
import and delegate to.

Scope: the bayyinah-audit-mcp wrapper (v0.5.3) covers 15 of 16 credential-leak
bypass classes that GPT-5 surfaced during adversarial self-stress against
the wrapper-side sanitization patch. The wrapper closes labeled-credential
shapes, header tokens, vendor-prefix bare values, partial fingerprints,
JWTs, PEM blocks, cookies, OAuth artifacts, URL query parameters, and
basic-auth URLs. Wrapper-side coverage is enumerated in
`bayyinah_audit_mcp/tools/cross_vendor_audit.py::REDACTION_RULES` and
locked by `tests/test_tools.py::test_cross_vendor_audit_hardened_patch_closes_bypass_class`.

The 16th class -- arbitrary unlabeled opaque values -- is structurally
irreducible at the wrapper layer without unacceptable false-positive rates
on normal output. The wrapper cannot safely distinguish "this 22-character
alphanumeric string is a credential" from "this 22-character alphanumeric
string is a section reference, a hash, a UUID, or a non-secret identifier."
The MCP wrapper therefore delegates that responsibility to lane #3 by
contract.

## What lane #3 owns

If `bayyinah_audit_orchestrator.run_cross_vendor_audit(**payload)` returns
any of the following surfaces, none of them may carry raw, encoded,
base64-wrapped, compressed, hashed, or otherwise transformed API keys or
other credential material that the wrapper's REDACTION_RULES cannot
recognize structurally:

- `status` (str)
- `reason` (str)
- `consensus.reasoning` (str inside the Consensus envelope)
- `consensus.agreed_findings[].message` (str)
- `consensus.agreed_findings[].location` (str)
- `solo_findings[provider][].message` (str)
- `solo_findings[provider][].location` (str)
- Any other field that crosses the lane-#3-to-wrapper boundary, including
  fields the wrapper allowlist will silently drop on the way back to the
  MCP client (`raw_log`, telemetry payloads, debug traces, etc.).

## Six contract requirements lane #3's own test suite must prove

These are the exact requirements GPT-5 enumerated during the stress test
and which the wrapper layer cannot satisfy from its position in the call
chain. Each one is a discrete test commitment lane #3 owns. None of them
overlap with the wrapper's 15 REDACTION_RULES classes; together with the
wrapper, they cover the full leak surface.

### LANE3-C1: no raw, encoded, or transformed credential emission

Lane #3's own test suite must prove no raw, encoded, base64-wrapped,
compressed, hashed, or otherwise transformed API keys are emitted through
`status`, `reason`, `consensus`, `solo_findings`, raw logs, exceptions,
telemetry, or callback traces.

Recommended test pattern: stress-test lane #3 with an artifact whose
content includes the canary `sk-test-CANARY-must-never-appear-anywhere`.
For each output surface, assert the canary is absent from a normalized
JSON dump of the return envelope, the raw provider response, and any
debug-mode telemetry the orchestrator writes to disk or to stderr.

### LANE3-C2: no opaque non-env unlabeled credentials

Lane #3's own test suite must prove arbitrary opaque non-env credentials
without labels or known prefixes are not included in any returned field or
log surface.

Recommended test pattern: configure a provider that returns a value of the
shape `CANARY1234567890abcdef` (no label, no prefix, not in any env var)
and assert it is absent from the orchestrator's return value. The wrapper
cannot redact this class because there is no syntactic signal that the
string is sensitive.

### LANE3-C3: no short-credential emission below the 4-char wrapper floor

Lane #3's own test suite must prove secrets shorter than 4 characters, if
supported by any provider or test harness, are never emitted in
wrapper-visible output.

Recommended test pattern: if lane #3 supports any provider whose key
format is shorter than 4 characters (rare but possible in test
harnesses), assert that those values do not appear in the return envelope.
The wrapper's `MIN_ENV_SECRET_REDACT_CHARS = 4` floor excludes shorter
values to avoid over-firing on numeric IDs and short tokens.

### LANE3-C4: no useful entropy via partial-fingerprint disclosure

Lane #3's own test suite must prove partially redacted fingerprints do not
disclose useful entropy such as first 6 plus last 4, last 8, token hash
prefixes, account-scoped credential IDs, or request-correlated signing
material.

Recommended test pattern: assert that if the orchestrator deliberately
truncates a credential for debugging, the truncated form does not preserve
enough bits to enable rainbow-table or rate-limited brute-force attacks
against the upstream provider's API. The wrapper redacts known fingerprint
shapes (`sk-...last4`, `fingerprint=...`, `sha256:...`, `last_4=...`), but
custom truncation formats cannot be enumerated at the wrapper layer.

### LANE3-C5: no credential carryover via attached artifacts

Lane #3's own test suite must prove screenshots, PDFs, attachments, tool
traces, request dumps, response dumps, and provider SDK debug objects
cannot carry credentials into wrapper-normalized fields.

Recommended test pattern: if lane #3 ever attaches binary artifacts or
embeds provider SDK debug objects in its return envelope, assert that
those attachments do not contain credential material before they cross
the wrapper boundary. The wrapper sees these as opaque payloads and
cannot inspect them without parsing arbitrary file formats.

### LANE3-C6: structured exception conversion before crossing the boundary

Lane #3's own test suite must prove exception objects, nested causes,
`repr()`, SDK response objects, and validation errors are converted to
safe structured summaries before crossing into the MCP wrapper.

Recommended test pattern: assert that when lane #3 catches an SDK
exception whose message embeds a credential (e.g.
`anthropic.APIError("invalid_api_key", body={"key": "sk-..."})`), the
re-raised exception or returned error envelope carries only the
exception class name and a sanitized one-sentence summary -- never
`repr(exc)`, never `str(exc)` if `str(exc)` could include args, and
never the SDK's raw response body. The wrapper layer scrubs known
credential shapes from `str(exc)` via the same REDACTION_RULES (see
F-V05-001 in `CROSS-VENDOR-AUDIT-V05.md` and the v0.5.3 re-application),
but defense in depth at the lane #3 layer prevents non-recognizable
leak shapes from reaching the wrapper at all.

## How to integrate this contract

For BayyinahEnterprise lane #3 (`bayyinah_audit_orchestrator`):

1. Add a `tests/test_canary_non_leak.py` (or equivalent) to the lane #3
   repository covering all six LANE3-C1 through LANE3-C6 requirements.
2. Wire those tests into the lane #3 CI matrix.
3. When tagging a lane #3 release, include in the release notes:
   "Validated against MCP wrapper LANE-3-CONTRACT-V05.md, all six
   canary non-leak requirements green."
4. If a new credential surface emerges in a future MCP wrapper round
   (e.g. v0.6 surfaces a 17th class), update this contract document
   and re-run the lane #3 canary tests against the expanded contract.

For third-party `bayyinah_audit_orchestrator` providers (PyPI consumers
who bring their own lane #3):

1. Read this contract before integration. The MCP wrapper assumes you
   have satisfied LANE3-C1 through LANE3-C6 on your side.
2. If you cannot satisfy these requirements, document the residual leak
   surface in your README and recommend that downstream MCP clients
   apply additional scrubbing in their own consumer code before
   logging or persisting wrapper output.

## Vendor prefixes the wrapper does NOT catch (lane #3 ownership)

The wrapper's vendor-prefix patterns (REDACTION_RULES) cover Anthropic
(`sk-ant-`), OpenAI (`sk-`), xAI (`xai-`), Google (`AIza`, `ya29.`),
AWS (`AKIA`, `ASIA`), GitHub (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`,
`github_pat_`), Slack (`xox[baprs]-`), and as of v0.5.4 also Perplexity
(`pplx-`), Groq (`gsk_`), Replicate (`r8_`), and HuggingFace (`hf_`).

Vendors lane #3 might plug in whose bare-value forms the wrapper does
NOT recognise structurally:

- **Cohere** - opaque keys, no canonical prefix. Caught only when
  surfaced behind a label (`cohere_api_key=...`). Lane #3 owns the
  unlabeled-bare-value case.
- **Mistral** - opaque, label-only at the wrapper.
- **Together AI** - opaque hex strings, label-only at the wrapper.
- **Fireworks AI** - opaque, label-only at the wrapper.
- **DeepSeek** - opaque, label-only at the wrapper.
- **Any custom in-house orchestrator** - by definition unknown to the
  wrapper. Lane #3 implementers MUST scrub their own custom credential
  shapes before any value reaches a wrapper-allowlisted field.

The failure mode the wrapper cannot prevent: lane #3 returns a Cohere
key as the bare value `4xK9...` (no label, no recognised prefix) inside
`Consensus.reasoning` or `metadata`. The wrapper's structural patterns
do not match. The label-based regex does not fire. The credential is
forwarded verbatim. Closure of this class is lane #3's responsibility
per the contract above.

## Provenance and audit-chain references

- `CROSS-VENDOR-AUDIT-V05.md` -- original GPT-5 cross-vendor pass that
  surfaced F-V05-002 (canary in allowed fields).
- `CROSS-VENDOR-AUDIT-V05-PATCH-STRESS.md` -- GPT-5 adversarial
  self-stress test that enumerated the 16 bypass classes and the six
  residual contract requirements reproduced above.
- `PATCHES.md` v0.5.2 -- wrapper-side close on F-V05-002 with the
  narrow five-pattern scrub.
- `PATCHES.md` v0.5.3 -- wrapper-side expansion to 15 bypass classes
  plus F-V05-001 re-application and this contract spec handoff.
- `PATCHES.md` v0.5.4 -- adds Perplexity / Groq / Replicate / HuggingFace
  vendor-prefix patterns and the `Consensus.metadata` forward-compat
  hatch with `_scrub_dict` recursive walker. Also adds the closed-form
  vendor-prefix gap list above.
- `REVIEW-V3.md` -- the intra-Claude review that originally deferred
  this surface to lane #3 as contract-boundary work.
- `bayyinah_audit_mcp/tools/cross_vendor_audit.py::REDACTION_RULES` --
  the canonical wrapper-side coverage list.
- `tests/test_tools.py::test_cross_vendor_audit_hardened_patch_closes_bypass_class`
  -- the wrapper-side regression lock for the 15 bypass classes.

Brand canonical: BayyinahEnterprise. License inheritance: this contract
spec is part of the bayyinah-audit-mcp repository and inherits its
Apache-2.0 license.
