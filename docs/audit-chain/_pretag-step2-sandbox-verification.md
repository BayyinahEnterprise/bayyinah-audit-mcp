# Pre-tag step 2 sandbox verification: pip install -e '.[all]' on Python 3.10.12

Run by: third Claude (Cowork driver), 2026-05-11.
Scope: in-sandbox confirmation of the wheel-availability and editable-install path for v0.5.3. NOT a substitute for the fresh 3.10 sandbox owned by a human; that step still needs to run on Bilal/Fraz/Pat's side per the published sequence. This artifact is empirical evidence that step 2 of the v0.5.3 pre-tag sequence is not a discovery step.

Underscore-prefix filename signals transient context; delete after the human-owned step lands.

## Environment

- Python: 3.10.12 (matches the project's minimum supported version).
- pip resolver: PyPI live index (not a mirror).
- Install command per extra: `pip install --break-system-packages --quiet '<spec>'`.
- Editable install of the package itself: `pip install --break-system-packages --quiet -e .` from the workspace folder.

## Results

All four optional extras resolved and installed on PyPI 3.10. Versions installed are well above the declared floors in `pyproject.toml`:

| Extra | Floor in pyproject | Resolved version | Margin |
|---|---|---|---|
| anthropic | >=0.54.0 | 0.100.0 | substantial |
| openai | >=1.80.0 | 2.36.0 | substantial |
| google-genai | >=1.20.0 | 2.0.1 | substantial |
| pdfplumber | >=0.11.0 | 0.11.9 | minor |

Editable install of `bayyinah-audit-mcp` itself: succeeded. `pip show` reports version `0.5.3` and the package is importable from the install location. `python -c "import bayyinah_audit_mcp; print(bayyinah_audit_mcp.__version__)"` prints `0.5.3`.

Tests after install: `pytest tests/` reports `33 passed in 2.85s` on Python 3.10.12. No regression from the editable install.

## What this confirms

- F-V05-RECON-003 holds empirically, not just by PyPI metadata query. Anthropic, OpenAI, Google GenAI, and pdfplumber all have py3.10-compatible wheels at and above the declared floors.
- The `pip install -e '.[all]'` path produces a working install (the editable install of the local package + the four extras resolves cleanly and lets pytest run).
- The 0.5.3 version is reachable from the installed package, so the two-source-of-truth drift (F-V05-RECON-001 class) is provably closed in the install path.

## What this does NOT confirm

- The GitHub Actions matrix on 3.11/3.12/3.13. Only 3.10.12 was exercised here. The asyncio.run risk REVIEW-V2 Q3 anticipated on 3.13 remains untested in this run.
- A fully clean room. The sandbox has accumulated packages from earlier sessions. A real `python -m venv && pip install -e '.[all]'` on a fresh 3.10 sandbox could surface a missing transitive that my environment masks. Estimated risk: low (the four extras are popular packages with mature wheels), but the human-owned verification is still the canonical evidence.
- The PyPI README rendering. Separate concern; covered by step 3 of the published sequence.

## Recommended use of this evidence

Treat this artifact as "step 2 partial, sandbox-only" in the audit chain. The human-owned fresh-3.10 verification supersedes this and should be the disposition of record once it runs. Until then, this lowers the perceived risk of step 2 from "discovery, may surface unknowns" to "confirmation, expected to be clean."

The four-step sequence remaining for v0.5.3 tag:

1. GitHub Actions matrix (3.10/3.11/3.12/3.13) on a release-candidate branch -- still gated on push access.
2. Fresh 3.10 sandbox pip install -- partial-credit-passed in this artifact; human-owned full verification still recommended.
3. README rendering check on PyPI or via `readme_renderer` locally.
4. `python -m build && twine upload dist/*`.
