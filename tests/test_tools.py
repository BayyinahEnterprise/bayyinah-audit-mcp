"""Functional tests for Bayyinah Audit MCP tools."""

from __future__ import annotations

import builtins
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from bayyinah_audit_mcp.tools.audit_artifact import (
    AuditArtifactInput,
    bayyinah_audit_artifact,
)
from bayyinah_audit_mcp.tools.check_attributions import (
    CheckAttributionsInput,
    bayyinah_check_attributions,
)
from bayyinah_audit_mcp.tools.cross_vendor_audit import (
    CrossVendorAuditInput,
    _scrub_dict,
    bayyinah_cross_vendor_audit,
)
from bayyinah_audit_mcp.tools.furqan_lint import (
    FurqanLintInput,
    bayyinah_run_furqan_lint,
)
from bayyinah_audit_mcp.tools.generate_round_report import (
    GenerateRoundReportInput,
    bayyinah_generate_round_report,
)
from bayyinah_audit_mcp.tools.list_sections import (
    ListSectionsInput,
    bayyinah_list_sections,
)
from bayyinah_audit_mcp.tools.lookup_section import (
    LookupSectionInput,
    bayyinah_lookup_section,
)


def _configure_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BAYYINAH_AUDIT_ROOT", str(tmp_path))
    monkeypatch.setenv("BAYYINAH_PATH_STRICT", "1")


def test_lookup_section_normalizes_common_reference_forms() -> None:
    direct = bayyinah_lookup_section(LookupSectionInput(section_ref="9.1"))
    sigil = bayyinah_lookup_section(LookupSectionInput(section_ref="§9.1"))
    labeled = bayyinah_lookup_section(LookupSectionInput(section_ref="Section 9.1"))
    unknown = bayyinah_lookup_section(LookupSectionInput(section_ref="99.99"))

    assert direct.status == "ok"
    assert direct.section_ref == "9.1"
    assert sigil.section_ref == "9.1"
    assert labeled.section_ref == "9.1"
    assert unknown.status == "not_found"


def test_list_sections_returns_five_seeded_refs() -> None:
    result = bayyinah_list_sections(ListSectionsInput())

    assert result["status"] == "ok"
    assert result["count"] == 5
    assert {section["section_ref"] for section in result["sections"]} == {
        "5.2",
        "9.1",
        "14.5",
        "18.10",
        "23.3",
    }


def test_audit_artifact_prompt_contains_lookup_section_title(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    result = bayyinah_audit_artifact(
        AuditArtifactInput(
            artifact_text="Synthetic test artifact.",
            section_refs=["9.1"],
            include_framework_prompt=False,
        )
    )

    assert result["status"] == "ok"
    assert "Section Reference Normalization and Resolution" in result["audit_prompt"]


def test_audit_artifact_warns_when_path_resolves_to_empty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    artifact = tmp_path / "empty.txt"
    artifact.write_text("", encoding="utf-8")

    result = bayyinah_audit_artifact(
        AuditArtifactInput(
            artifact_path="empty.txt",
            include_framework_prompt=False,
        )
    )

    joined_warnings = " ".join(result["warnings"]).lower()

    assert "empty" in joined_warnings
    assert "no artifact_text or artifact_path was provided" not in joined_warnings


def test_audit_artifact_warns_when_neither_text_nor_path_is_given(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    result = bayyinah_audit_artifact(
        AuditArtifactInput(include_framework_prompt=False)
    )

    joined_warnings = " ".join(result["warnings"]).lower()

    assert "no artifact_text or artifact_path was provided" in joined_warnings
    assert "empty" not in joined_warnings


def test_check_attributions_flags_unknown_section_ref(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    artifact = tmp_path / "unknown-section.txt"
    artifact.write_text("This document references §99.99.", encoding="utf-8")

    result = bayyinah_check_attributions(
        CheckAttributionsInput(path="unknown-section.txt")
    )

    assert result.status == "completed_with_findings"
    assert "99.99" in result.unresolved_section_refs


def test_check_attributions_ignores_month_and_weekday_words(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    artifact = tmp_path / "date-words.txt"
    artifact.write_text(
        "The review happened in December 2024 and continued Monday 2025.",
        encoding="utf-8",
    )

    result = bayyinah_check_attributions(
        CheckAttributionsInput(path="date-words.txt")
    )

    checked_citations = " ".join(result.checked_citations)

    assert "December" not in checked_citations
    assert "Monday" not in checked_citations
    assert result.unresolved_section_refs == []


def test_check_attributions_warns_on_missing_corpus(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    artifact = tmp_path / "missing-corpus-artifact.txt"
    artifact.write_text("This document cites Smith 2024.", encoding="utf-8")

    result = bayyinah_check_attributions(
        CheckAttributionsInput(
            path="missing-corpus-artifact.txt",
            corpus_path="missing-corpus.json",
        )
    )

    warning_text = " ".join(result.warnings)
    reason_text = result.reason or ""

    assert result.status == "ok_with_warnings"
    assert "missing-corpus.json" in warning_text or "missing-corpus.json" in reason_text


def test_furqan_lint_missing_binary_returns_unavailable_and_default_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "BAYYINAH_FURQAN_LINT_CMD",
        "bayyinah-furqan-lint-definitely-not-installed",
    )

    artifact = tmp_path / "artifact.furqan"
    artifact.write_text("rule test {}", encoding="utf-8")

    request = FurqanLintInput(path="artifact.furqan")
    result = bayyinah_run_furqan_lint(request)

    assert request.max_output_chars == 65536
    assert result.status == "unavailable"
    assert result.findings == []


def test_cross_vendor_audit_missing_lane3_returns_unavailable_without_key_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    secret_value = "sk-test-secret-value-that-must-not-leak"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)
    monkeypatch.delitem(sys.modules, "bayyinah_audit_orchestrator", raising=False)

    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "bayyinah_audit_orchestrator":
            raise ImportError("forced missing lane 3 for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    assert result.status == "unavailable"
    assert isinstance(result.api_keys_present, list)
    assert all(isinstance(provider, str) for provider in result.api_keys_present)
    assert secret_value not in result.model_dump_json()


def test_cross_vendor_audit_exception_path_does_not_leak_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-must-never-appear-anywhere"
    monkeypatch.setenv("ANTHROPIC_API_KEY", canary)

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        raise ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    assert result.status == "error"
    assert "ValueError" in (result.reason or "")
    assert canary not in result.model_dump_json()
    assert "boom" not in (result.reason or "")


def test_cross_vendor_audit_does_not_leak_via_raw_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-raw-result-must-not-leak"
    monkeypatch.setenv("ANTHROPIC_API_KEY", canary)

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "raw_log": "Authorization: Bearer " + canary,
            "status": "ok",
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    assert result.status == "ok"
    assert canary not in result.model_dump_json()


def test_cross_vendor_audit_consensus_extra_fields_dropped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "consensus": {
                "verdict": "ship",
                "reasoning": "Consensus is clean.",
                "agreed_findings": [],
                "disagreement_count": 0,
                "secret_extra": "must be dropped",
            },
            "raw_log": "must also be dropped",
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    dumped = result.model_dump_json()

    assert result.status == "ok"
    assert result.consensus is not None
    assert result.consensus.verdict == "ship"
    assert "secret_extra" not in dumped
    assert "raw_log" not in dumped
    assert "must be dropped" not in dumped


def test_cross_vendor_audit_scrub_redacts_canary_inside_consensus_reasoning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-consensus-reasoning-must-not-leak"
    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "consensus": {
                "verdict": "ship_with_caveats",
                "reasoning": "Model leaked api_key=" + canary,
                "agreed_findings": [],
                "disagreement_count": 1,
            },
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    assert result.consensus is not None
    assert canary not in result.model_dump_json()
    assert "<REDACTED>" in result.consensus.reasoning


def test_cross_vendor_audit_scrub_redacts_canary_inside_finding_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-finding-message-must-not-leak"
    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "consensus": {
                "verdict": "hold",
                "reasoning": "Consensus has one blocking finding.",
                "agreed_findings": [
                    {
                        "severity": "HIGH",
                        "section_ref": "18.10",
                        "message": "Authorization: Bearer " + canary,
                        "location": "metadata api_key=" + canary,
                        "extra": "drop me",
                    }
                ],
                "disagreement_count": 0,
            },
            "solo_findings": {
                "anthropic": [
                    {
                        "severity": "HIGH",
                        "section_ref": "18.10",
                        "message": "sk-ant-" + "A" * 24,
                        "location": "global",
                    }
                ]
            },
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    dumped = result.model_dump_json()

    assert result.consensus is not None
    assert result.consensus.agreed_findings
    assert canary not in dumped
    assert "sk-ant-" + "A" * 24 not in dumped
    assert "<REDACTED>" in dumped


def test_cross_vendor_audit_exception_path_does_not_leak_canary_to_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """v0.5.3 (F-V05-001 RE-APPLIED): the exception handler must not log
    the exception repr or message. The v0.5.1 part 2 fix swapped
    LOGGER.exception("...: %r", exc) for LOGGER.error("...: %s",
    type(exc).__name__); v0.5.2 inadvertently reverted that. v0.5.3
    restores the fix. This test locks the log-surface scrub against
    future regression.
    """
    import logging

    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-must-never-appear-in-logs"
    monkeypatch.setenv("ANTHROPIC_API_KEY", canary)

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        raise ValueError(f"boom; key was {os.environ['ANTHROPIC_API_KEY']}")

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    with caplog.at_level(logging.DEBUG):
        result = bayyinah_cross_vendor_audit(
            CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
        )

    assert result.status == "error"

    surfaces: list[str] = []
    for record in caplog.records:
        surfaces.append(record.getMessage())
        surfaces.append(str(record.msg))
        if record.exc_info:
            import traceback

            surfaces.append("".join(traceback.format_exception(*record.exc_info)))
        if record.exc_text:
            surfaces.append(record.exc_text)

    joined = "\n".join(surfaces)

    assert canary not in joined
    assert "boom" not in joined


HARDENED_BYPASS_CLASS_CASES: list[tuple[str, str]] = [
    (
        "custom_vendor_key_label",
        "XAI_KEY=xai-CANARY1234567890abcdef",
    ),
    (
        "anthropic_admin_key_label",
        "ANTHROPIC_ADMIN_KEY=admin-CANARY1234567890abcdef",
    ),
    (
        "google_oauth_bare_token",
        "ya29.CANARY1234567890abcdefghijklmnopqrstuvwxyz",
    ),
    (
        "aws_access_key_id_label",
        "AWS_ACCESS_KEY_ID=AKIACANARY12345678",
    ),
    (
        "bare_jwt",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.CANARY1234567890abcdef.signature1234567890",
    ),
    (
        "authorization_token_scheme",
        "Authorization: Token CANARY1234567890abcdef",
    ),
    (
        "cookie_session",
        "Cookie: session=CANARY1234567890abcdef; csrftoken=CANARYcsrf1234567890",
    ),
    (
        "oauth_code_state",
        "https://example.test/callback?code=CANARYcode1234567890abcdef&state=CANARYstate1234567890",
    ),
    (
        "url_query_key_param",
        "https://api.example.test/v1/models?key=CANARY1234567890abcdef",
    ),
    (
        "basic_auth_url",
        "https://user:CANARY1234567890abcdef@api.example.test/v1",
    ),
    (
        "quoted_json_api_key",
        '{"api_key":"xai-CANARY1234567890abcdef"}',
    ),
    (
        "truncated_fingerprint_echo",
        "Provider rejected key sk-CANARY...9f3a-trailingbits",
    ),
    (
        "pem_private_key_block",
        "-----BEGIN PRIVATE KEY-----\nCANARYprivatekey1234567890abcdef\n-----END PRIVATE KEY-----",
    ),
    (
        "github_personal_access_token",
        "ghp_CANARY1234567890abcdef0123456789xyz",
    ),
    (
        "slack_bot_token",
        "xoxb-1234567890-CANARY1234567890",
    ),
    # v0.5.4 additions: Perplexity, Groq, Replicate, HuggingFace prefixes.
    # The lane #3 contract still owns the canonical non-leak guarantee for
    # these vendors; the wrapper just catches the most common bare-value forms.
    (
        "perplexity_api_key",
        "pplx-CANARY1234567890abcdef0123456789xyz",
    ),
    (
        "groq_api_key",
        "gsk_CANARY1234567890abcdef0123456789xyz",
    ),
    (
        "replicate_api_key",
        "r8_CANARY1234567890abcdef0123456789xyz",
    ),
    (
        "huggingface_api_key",
        "hf_CANARY1234567890abcdef0123456789xyz",
    ),
]


@pytest.mark.parametrize(
    "bypass_class,payload_substring",
    HARDENED_BYPASS_CLASS_CASES,
    ids=[case[0] for case in HARDENED_BYPASS_CLASS_CASES],
)
def test_cross_vendor_audit_hardened_patch_closes_bypass_class(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bypass_class: str,
    payload_substring: str,
) -> None:
    """v0.5.3 (CROSS-VENDOR-AUDIT-V05-PATCH-STRESS coverage): each of the
    15 wrapper-side bypass classes GPT-5 surfaced in its adversarial
    self-stress test should be redacted by the hardened _scrub. Lane #3
    contractually owns the 16th class (arbitrary unlabeled opaque values);
    see LANE-3-CONTRACT-V05.md.

    Treat any test failure here as a regression in REDACTION_RULES or
    the env-value redaction layer.
    """
    _configure_root(monkeypatch, tmp_path)

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "consensus": {
                "verdict": "ship_with_caveats",
                "reasoning": f"diagnostic surface: {payload_substring}",
                "agreed_findings": [
                    {
                        "severity": "LOW",
                        "section_ref": "5.2",
                        "message": f"surface: {payload_substring}",
                        "location": "diagnostic",
                    }
                ],
                "disagreement_count": 0,
            },
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    dumped = result.model_dump_json()

    # The CANARY token is the discriminating value in each payload; it must
    # never appear in the output regardless of which surface (key label,
    # URL parameter, header scheme, JWT segment, PEM body, vendor prefix)
    # was used to express the leak.
    assert "CANARY" not in dumped, (
        f"bypass class {bypass_class!r} survived the hardened scrub: {dumped}"
    )
    assert "<REDACTED>" in dumped


def test_cross_vendor_audit_metadata_hatch_scrubs_nested_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """v0.5.4: Consensus.metadata is a forward-compat hatch for lane #3 fields
    beyond the four canonical ones. _scrub_dict must walk the nested structure
    and redact any string leaf that matches a SECRET_PATTERNS entry, no matter
    how deeply nested.
    """
    _configure_root(monkeypatch, tmp_path)

    canary = "sk-test-CANARY-must-never-appear-anywhere"

    fake_module = types.ModuleType("bayyinah_audit_orchestrator")

    def run_cross_vendor_audit(**_: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "consensus": {
                "verdict": "ship",
                "reasoning": "all clear",
                "agreed_findings": [],
                "disagreement_count": 0,
                "metadata": {
                    "iteration_id": "v05-04-test",
                    "diagnostics": {
                        "audit_log": [
                            {"step": 1, "note": "ok"},
                            {"step": 2, "note": f"key was {canary}"},
                        ],
                        "headers_seen": [
                            "Content-Type: application/json",
                            f"Authorization: Bearer {canary}",
                        ],
                    },
                },
            },
        }

    fake_module.run_cross_vendor_audit = run_cross_vendor_audit  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bayyinah_audit_orchestrator", fake_module)

    result = bayyinah_cross_vendor_audit(
        CrossVendorAuditInput(artifact_text="Synthetic test artifact.")
    )

    dumped = result.model_dump_json()
    assert canary not in dumped, (
        f"canary survived metadata scrub at any nesting depth: {dumped}"
    )
    # The non-secret structure is preserved (we expect 'iteration_id' to pass).
    assert "iteration_id" in dumped
    assert "<REDACTED>" in dumped


# ---------------------------------------------------------------------------
# v0.5.5: F-V05-DICT-CYCLE-LOOP defense-in-depth cycle guard
# ---------------------------------------------------------------------------


def test_scrub_dict_handles_self_referential_dict_without_hanging() -> None:
    """v0.5.5 F-V05-DICT-CYCLE-LOOP: a self-referential dict from a
    misbehaving lane #3 must not hang the walker. The cycle yields the
    literal sentinel '<cycle>' rather than recursing forever.
    """
    cyclic: dict[str, Any] = {"label": "outer"}
    cyclic["self"] = cyclic

    result = _scrub_dict(cyclic)

    assert isinstance(result, dict)
    assert result["label"] == "outer"
    assert result["self"] == "<cycle>"


def test_scrub_dict_handles_self_referential_list_without_hanging() -> None:
    """List self-cycle: the inner reference resolves to '<cycle>'."""
    cyclic: list[Any] = ["leading"]
    cyclic.append(cyclic)

    result = _scrub_dict(cyclic)

    assert isinstance(result, list)
    assert result[0] == "leading"
    assert result[1] == "<cycle>"


def test_scrub_dict_handles_indirect_cycle_through_nested_dict() -> None:
    """Cycle via a -> b -> a (indirect). Either side hitting the second
    visit yields '<cycle>'.
    """
    a: dict[str, Any] = {"name": "a"}
    b: dict[str, Any] = {"name": "b", "back": a}
    a["forward"] = b

    result = _scrub_dict(a)

    assert result["name"] == "a"
    assert result["forward"]["name"] == "b"
    assert result["forward"]["back"] == "<cycle>"


def test_scrub_dict_sibling_reuse_is_not_a_cycle() -> None:
    """Two siblings pointing at the same dict object are not a cycle;
    each must scrub independently. Per-call seen-set is constructed at
    the top entry and propagated via the |-union per recursion frame,
    so the sentinel only fires when the SAME container appears on the
    SAME ancestor path.
    """
    shared: dict[str, Any] = {"creds": "sk-test-CANARY-shared-shape"}
    parent: dict[str, Any] = {"left": shared, "right": shared}

    result = _scrub_dict(parent)

    # Both copies were walked; neither was sentinel'd.
    assert isinstance(result["left"], dict)
    assert isinstance(result["right"], dict)
    # The canary inside shared was scrubbed in both branches.
    assert result["left"]["creds"] != "sk-test-CANARY-shared-shape"
    assert result["right"]["creds"] != "sk-test-CANARY-shared-shape"


def test_scrub_dict_still_scrubs_leaves_in_acyclic_input() -> None:
    """v0.5.5 must not regress the v0.5.4 nested-redaction behaviour
    when the input is acyclic. Canary at the leaf is redacted; the
    cycle guard is invisible on this path.
    """
    canary = "sk-test-CANARY-acyclic-path"
    payload = {
        "outer": {
            "inner": [
                {"deep": canary},
            ],
        },
    }

    result = _scrub_dict(payload)
    dumped = repr(result)

    assert canary not in dumped


def test_generate_round_report_blocks_at_threshold_and_handles_invalid_threshold() -> None:
    high_finding = {
        "severity": "HIGH",
        "section_ref": "23.3",
        "message": "Blocking test finding.",
        "location": "global",
    }

    blocked = bayyinah_generate_round_report(
        GenerateRoundReportInput(
            findings=[high_finding],
            severity_threshold="MED",
        )
    )

    assert blocked["blocked"] is True
    assert blocked["status"] == "blocked"

    with pytest.raises(ValidationError):
        GenerateRoundReportInput(
            findings=[high_finding],
            severity_threshold="CRITICAL",
        )

    empty = bayyinah_generate_round_report(
        GenerateRoundReportInput(
            findings=[],
            severity_threshold="MED",
        )
    )

    assert empty["blocked"] is False
    assert empty["status"] == "ok"
