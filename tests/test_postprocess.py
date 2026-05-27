import json
import pytest
from pathlib import Path

from src.postprocess import get_drug_info, get_canonical_provider, enrich_record, load_mappings

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def mappings():
    return load_mappings()


@pytest.fixture(scope="module")
def drug_map(mappings):
    return mappings[0]


@pytest.fixture(scope="module")
def provider_map(mappings):
    return mappings[1]


# ── Drug lookup ───────────────────────────────────────────────────────────────

def test_known_biologic_returns_correct_class(drug_map):
    info = get_drug_info("humira", drug_map)
    assert info is not None
    assert info["drug_class"] == "Biologic"


def test_known_immunomodulator_returns_correct_class(drug_map):
    info = get_drug_info("azathioprine", drug_map)
    assert info is not None
    assert info["drug_class"] == "Immunomodulator"


def test_unknown_drug_returns_none(drug_map):
    assert get_drug_info("unknown_drug_xyz", drug_map) is None


def test_drug_lookup_is_case_insensitive(drug_map):
    assert get_drug_info("Humira", drug_map) == get_drug_info("humira", drug_map)


# ── Provider lookup ───────────────────────────────────────────────────────────

def test_known_provider_returns_canonical(provider_map):
    assert get_canonical_provider("gi doctor", provider_map) == "Gastroenterologist"


def test_gp_variants_resolve_correctly(provider_map):
    assert get_canonical_provider("family doctor", provider_map) == "GP"
    assert get_canonical_provider("general practitioner", provider_map) == "GP"


def test_unknown_provider_returns_none(provider_map):
    assert get_canonical_provider("unknown_clinic_xyz", provider_map) is None


# ── enrich_record ─────────────────────────────────────────────────────────────

def test_enrich_record_adds_drug_class_and_canonical_name(drug_map, provider_map):
    record = {
        "call1": {
            "treatment_journey": [
                {"name": "humira", "status": "currently_on", "evidence": "on Humira", "certainty": "high"}
            ]
        },
        "call3": {
            "referral_pathway": [
                {"name": "gi doctor", "evidence": "saw a GI", "certainty": "high", "canonical_provider": "Gastroenterologist"}
            ]
        },
    }
    enriched = enrich_record(record, drug_map, provider_map)
    treatment = enriched["call1"]["treatment_journey"][0]
    assert treatment["drug_class"] == "Biologic"
    assert treatment["canonical_name"] == "adalimumab (Humira)"


def test_enrich_record_does_not_mutate_original(drug_map, provider_map):
    record = {
        "call1": {"treatment_journey": [
            {"name": "humira", "status": "currently_on", "evidence": "on Humira", "certainty": "high"}
        ]},
        "call3": {"referral_pathway": []},
    }
    original_treatment = record["call1"]["treatment_journey"][0].copy()
    enrich_record(record, drug_map, provider_map)
    assert record["call1"]["treatment_journey"][0] == original_treatment
