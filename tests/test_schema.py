import json
import pytest
import json_repair
from pydantic import ValidationError

from src.schema import (
    Call1Output,
    Call2Output,
    Call3Output,
    PatientRecord,
    ExtractionMetadata,
    BioligicStatusEnum,
    CertaintyEnum,
    CompletenessEnum,
)
from datetime import datetime, timezone


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_CALL1 = {
    "churn_detection": {
        "completeness": "complete",
        "reasoning": "Patient describes a full journey ending with Humira.",
        "certainty": "high",
    },
    "biologic_status": {
        "on_biologic": "yes",
        "name": "Humira",
        "reasoning": "I've been on Humira for five years now.",
        "certainty": "high",
    },
    "sociodemographics": {
        "age":              {"value": 34,       "evidence": "I'm 34 years old",                     "certainty": "high"},
        "sex":              {"value": "female", "evidence": "I'm Sarah",                             "certainty": "medium"},
        "years_with_crohns": {"value": 8.0,    "evidence": "dealing with Crohn's for about 8 years", "certainty": "high"},
    },
    "treatment_journey": [
        {"name": "mesalamine", "status": "stopped",     "evidence": "We started with mesalamine", "certainty": "high"},
        {"name": "Humira",     "status": "currently_on","evidence": "I've been on Humira",         "certainty": "high"},
    ],
}

VALID_CALL3 = {
    "pathway_endpoint": {
        "status": "on_biologic",
        "reasoning": "Patient confirmed on Humira.",
        "certainty": "high",
    },
    "referral_pathway": [
        {"name": "GP",               "evidence": "My primary care doctor", "certainty": "high"},
        {"name": "Gastroenterologist","evidence": "referred me to a GI",  "certainty": "high"},
    ],
}


# ── Schema validation ─────────────────────────────────────────────────────────

def test_valid_call1_parses():
    result = Call1Output.model_validate(VALID_CALL1)
    assert result.biologic_status.on_biologic == BioligicStatusEnum.yes
    assert result.biologic_status.name == "Humira"
    assert result.churn_detection.completeness == CompletenessEnum.complete
    assert len(result.treatment_journey) == 2


def test_missing_required_field_raises():
    bad = {k: v for k, v in VALID_CALL1.items() if k != "churn_detection"}
    with pytest.raises(ValidationError):
        Call1Output.model_validate(bad)


def test_invalid_enum_raises():
    bad = {**VALID_CALL1, "biologic_status": {**VALID_CALL1["biologic_status"], "on_biologic": "maybe"}}
    with pytest.raises(ValidationError):
        Call1Output.model_validate(bad)


def test_wrong_type_for_age_raises():
    bad = json.loads(json.dumps(VALID_CALL1))
    bad["sociodemographics"]["age"]["value"] = "thirty-four"
    with pytest.raises(ValidationError):
        Call1Output.model_validate(bad)


def test_null_biologic_name_accepted():
    data = json.loads(json.dumps(VALID_CALL1))
    data["biologic_status"]["name"] = None
    result = Call1Output.model_validate(data)
    assert result.biologic_status.name is None


def test_null_call2_accepted_in_patient_record():
    record = PatientRecord(
        metadata=ExtractionMetadata(
            patient_id="TEST",
            model_used="gemini/test",
            timestamp=datetime.now(timezone.utc),
        ),
        call1=Call1Output.model_validate(VALID_CALL1),
        call2=None,
        call3=Call3Output.model_validate(VALID_CALL3),
    )
    assert record.call2 is None


# ── JSON repair ───────────────────────────────────────────────────────────────

def test_json_repair_fixes_missing_closing_brace():
    valid_json = json.dumps(VALID_CALL1)
    broken_json = valid_json[:-1]  # strip last closing brace

    repaired = json_repair.repair_json(broken_json)
    result = Call1Output.model_validate(json.loads(repaired))
    assert result.biologic_status.on_biologic == BioligicStatusEnum.yes


def test_json_repair_fixes_missing_comma():
    # Simulate LLM omitting a comma between two keys
    broken_json = """{
        "churn_detection": {"completeness": "complete" "reasoning": "ok", "certainty": "high"},
        "biologic_status": {"on_biologic": "yes", "name": null, "reasoning": "ok", "certainty": "high"},
        "sociodemographics": {
            "age":               {"value": null, "evidence": "not mentioned", "certainty": "low"},
            "sex":               {"value": null, "evidence": "not mentioned", "certainty": "low"},
            "years_with_crohns": {"value": null, "evidence": "not mentioned", "certainty": "low"}
        },
        "treatment_journey": []
    }"""
    repaired = json_repair.repair_json(broken_json)
    result = Call1Output.model_validate(json.loads(repaired))
    assert result.churn_detection.completeness == CompletenessEnum.complete


def test_bad_enum_after_repair_still_raises():
    broken_json = json.dumps(VALID_CALL1).replace('"on_biologic": "yes"', '"on_biologic": "invalid_value"')
    repaired = json_repair.repair_json(broken_json)
    with pytest.raises(ValidationError):
        Call1Output.model_validate(json.loads(repaired))
