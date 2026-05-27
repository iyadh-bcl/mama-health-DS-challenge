import pytest
from unittest.mock import patch, MagicMock

from src.schema import (
    Call1Output, Call2Output, Call3Output,
    BioligicStatusEnum, CompletenessEnum, CertaintyEnum,
)
from src.pipeline import process_patient, _check_transcript_quality, _check_evidence_verbatim


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_call1(on_biologic: str) -> Call1Output:
    return Call1Output.model_validate({
        "churn_detection": {"completeness": "complete", "reasoning": "ok", "certainty": "high"},
        "biologic_status": {"on_biologic": on_biologic, "name": None, "reasoning": "ok", "certainty": "high"},
        "sociodemographics": {
            "age":               {"value": None, "evidence": "not mentioned", "certainty": "low"},
            "sex":               {"value": None, "evidence": "not mentioned", "certainty": "low"},
            "years_with_crohns": {"value": None, "evidence": "not mentioned", "certainty": "low"},
        },
        "treatment_journey": [],
    })


MOCK_CALL3 = Call3Output.model_validate({
    "pathway_endpoint": {"status": "on_biologic", "reasoning": "ok", "certainty": "high"},
    "referral_pathway": [],
})

MOCK_CALL2 = Call2Output.model_validate({
    "biologic_status_detail": {"status": "not_reached", "reasoning": "ok", "certainty": "medium"},
    "reasons": None,
})

PATIENT = {"patient_id": "TEST001", "interview_transcript": "I have been dealing with Crohns disease for many years and my doctor referred me to a specialist."}


# ── Call 2 conditional logic ──────────────────────────────────────────────────

def test_call2_skipped_when_biologic_is_yes():
    with patch("src.pipeline.run_call1", return_value=_make_call1("yes")), \
         patch("src.pipeline.run_call2") as mock_call2, \
         patch("src.pipeline.run_call3", return_value=MOCK_CALL3):

        record, ledger = process_patient(PATIENT)

    mock_call2.assert_not_called()
    assert ledger["call2_status"] == "skipped"
    assert record.call2 is None


def test_call2_runs_when_biologic_is_no():
    with patch("src.pipeline.run_call1", return_value=_make_call1("no")), \
         patch("src.pipeline.run_call2", return_value=MOCK_CALL2) as mock_call2, \
         patch("src.pipeline.run_call3", return_value=MOCK_CALL3):

        record, ledger = process_patient(PATIENT)

    mock_call2.assert_called_once()
    assert ledger["call2_status"] == "success"
    assert record.call2 is not None


def test_call2_runs_when_biologic_is_unknown():
    with patch("src.pipeline.run_call1", return_value=_make_call1("unknown")), \
         patch("src.pipeline.run_call2", return_value=MOCK_CALL2) as mock_call2, \
         patch("src.pipeline.run_call3", return_value=MOCK_CALL3):

        record, ledger = process_patient(PATIENT)

    mock_call2.assert_called_once()
    assert ledger["call2_status"] == "success"


# ── Error handling ────────────────────────────────────────────────────────────

def test_call1_failure_returns_none_record():
    with patch("src.pipeline.run_call1", side_effect=ValueError("LLM error")):
        record, ledger = process_patient(PATIENT)

    assert record is None
    assert ledger["success"] is False
    assert "LLM error" in ledger["error"]


def test_call2_failure_returns_none_record():
    with patch("src.pipeline.run_call1", return_value=_make_call1("no")), \
         patch("src.pipeline.run_call2", side_effect=ValueError("call2 error")), \
         patch("src.pipeline.run_call3", return_value=MOCK_CALL3):

        record, ledger = process_patient(PATIENT)

    assert record is None
    assert ledger["success"] is False
    assert "call2 error" in ledger["error"]
    assert "failed" in ledger["call2_status"]


def test_call3_failure_returns_none_record():
    with patch("src.pipeline.run_call1", return_value=_make_call1("yes")), \
         patch("src.pipeline.run_call3", side_effect=ValueError("call3 error")):

        record, ledger = process_patient(PATIENT)

    assert record is None
    assert ledger["success"] is False


# ── Transcript quality check ──────────────────────────────────────────────────

def test_short_transcript_fails_quality_check():
    assert _check_transcript_quality("P001", "too short") is False


def test_low_alpha_ratio_fails_quality_check():
    # 50+ chars but mostly non-alpha (digits/symbols)
    assert _check_transcript_quality("P001", "1234567890 " * 10) is False


def test_valid_transcript_passes_quality_check():
    transcript = "This is a valid patient interview transcript with enough content." * 2
    assert _check_transcript_quality("P001", transcript) is True


def test_bad_transcript_causes_process_patient_to_return_none():
    bad_patient = {"patient_id": "P_BAD", "interview_transcript": "short"}
    record, ledger = process_patient(bad_patient)
    assert record is None
    assert ledger["success"] is False
    assert "transcript quality check" in ledger["error"]


# ── Evidence verbatim check ───────────────────────────────────────────────────

def test_evidence_verbatim_warns_on_mismatch(caplog):
    import logging
    from src.schema import PatientRecord, ExtractionMetadata, Call3Output
    from datetime import datetime, timezone

    call1 = _make_call1("yes")
    # inject a non-verbatim evidence string
    call1.sociodemographics.age.evidence = "fabricated evidence not in transcript"

    call3 = Call3Output.model_validate({
        "pathway_endpoint": {"status": "on_biologic", "reasoning": "ok", "certainty": "high"},
        "referral_pathway": [],
    })
    record = PatientRecord(
        metadata=ExtractionMetadata(
            patient_id="P001", model_used="test", timestamp=datetime.now(timezone.utc)
        ),
        call1=call1,
        call2=None,
        call3=call3,
    )
    transcript = "This is the actual transcript content with no fabricated evidence."

    with caplog.at_level(logging.WARNING, logger="src.pipeline"):
        _check_evidence_verbatim(record, transcript, "P001")

    assert any("fabricated evidence not in transcript" in m for m in caplog.messages)


def test_evidence_verbatim_no_warn_when_all_match(caplog):
    import logging
    from src.schema import PatientRecord, ExtractionMetadata, Call3Output
    from datetime import datetime, timezone

    transcript = "not mentioned is the actual content here for testing purposes only."
    call1 = _make_call1("yes")  # evidence fields are "not mentioned"
    call3 = Call3Output.model_validate({
        "pathway_endpoint": {"status": "on_biologic", "reasoning": "ok", "certainty": "high"},
        "referral_pathway": [],
    })
    record = PatientRecord(
        metadata=ExtractionMetadata(
            patient_id="P001", model_used="test", timestamp=datetime.now(timezone.utc)
        ),
        call1=call1,
        call2=None,
        call3=call3,
    )

    with caplog.at_level(logging.WARNING, logger="src.pipeline"):
        _check_evidence_verbatim(record, transcript, "P001")

    assert not any("not verbatim" in m for m in caplog.messages)
