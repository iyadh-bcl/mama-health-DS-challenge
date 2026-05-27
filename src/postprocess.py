import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DRUG_MAP_PATH = DATA_DIR / "crohns_drug_mapping.json"
PROVIDER_MAP_PATH = DATA_DIR / "crohns_provider_mapping.json"
INPUT_PATH = DATA_DIR / "results.json"
OUTPUT_PATH = DATA_DIR / "results_postprocessed.json"


def load_mappings(
    drug_map_path: Path = DRUG_MAP_PATH,
    provider_map_path: Path = PROVIDER_MAP_PATH,
) -> tuple[dict, dict]:
    drug_map = json.loads(drug_map_path.read_text(encoding="utf-8"))
    provider_map = json.loads(provider_map_path.read_text(encoding="utf-8"))
    return drug_map, provider_map


def get_drug_info(name: str, drug_map: dict) -> dict | None:
    info = drug_map.get(name.strip().lower())
    if info is None:
        logger.warning(f"No drug mapping found for: {name!r}")
    return info


def get_canonical_provider(name: str, provider_map: dict) -> str | None:
    canonical = provider_map.get(name.strip().lower())
    if canonical is None:
        logger.warning(f"No provider mapping found for: {name!r}")
    return canonical


def enrich_record(record: dict, drug_map: dict, provider_map: dict) -> dict:
    enriched = json.loads(json.dumps(record))  # deep copy

    for treatment in enriched["call1"]["treatment_journey"]:
        info = get_drug_info(treatment["name"], drug_map)
        treatment["canonical_name"] = info["canonical_name"] if info else None
        treatment["drug_class"] = info["drug_class"] if info else None

    for step in enriched["call3"]["referral_pathway"]:
        step["canonical_provider"] = get_canonical_provider(step["name"], provider_map)

    return enriched


def run_postprocess(
    input_path: Path = INPUT_PATH,
    output_path: Path = OUTPUT_PATH,
) -> None:
    drug_map, provider_map = load_mappings()
    records = json.loads(input_path.read_text(encoding="utf-8"))["records"]
    logger.info(f"Enriching {len(records)} records")

    enriched_records = [enrich_record(r, drug_map, provider_map) for r in records]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched_records, f, indent=2)

    logger.info(f"Written to {output_path}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    run_postprocess()
