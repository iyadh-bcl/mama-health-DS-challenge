import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .calls import MODEL, run_call1, run_call2, run_call3
from .schema import (
    BioligicStatusEnum,
    Call2Output,
    ExtractionMetadata,
    PatientRecord,
)

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).parent.parent / "data" / "interviews.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "results.json"


def load_interviews(path: Path = DATA_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(data).__name__}")
    return data


def _check_transcript_quality(patient_id: str, transcript: str) -> bool:
    stripped = transcript.strip()
    if len(stripped) < 50:
        logger.error(f"[{patient_id}] Transcript too short ({len(stripped)} chars)")
        return False
    alpha_ratio = sum(c.isalpha() for c in stripped) / len(stripped)
    if alpha_ratio < 0.7:
        logger.error(f"[{patient_id}] Transcript low alpha ratio ({alpha_ratio:.2f})")
        return False
    return True


def _check_evidence_verbatim(record: PatientRecord, transcript: str, patient_id: str) -> None:
    lower_transcript = transcript.lower()

    def warn(path: str, text: str) -> None:
        if text and text.lower() not in lower_transcript:
            logger.warning(f"[{patient_id}] Evidence not verbatim [{path}]: {text!r}")

    c1 = record.call1
    warn("call1.sociodemographics.age.evidence", c1.sociodemographics.age.evidence)
    warn("call1.sociodemographics.sex.evidence", c1.sociodemographics.sex.evidence)
    warn("call1.sociodemographics.years_with_crohns.evidence", c1.sociodemographics.years_with_crohns.evidence)
    for i, step in enumerate(c1.treatment_journey):
        warn(f"call1.treatment_journey[{i}].evidence", step.evidence)

    if record.call2 is not None and record.call2.reasons is not None:
        for i, reason in enumerate(record.call2.reasons):
            warn(f"call2.reasons[{i}].evidence", reason.evidence)

    for i, step in enumerate(record.call3.referral_pathway):
        warn(f"call3.referral_pathway[{i}].evidence", step.evidence)


def process_patient(patient: dict) -> tuple[PatientRecord | None, dict]:
    patient_id = patient["patient_id"]
    transcript = patient["interview_transcript"]

    ledger: dict = {
        "patient_id": patient_id,
        "call1_status": None,
        "call2_status": None,
        "call3_status": None,
        "success": False,
        "error": None,
    }

    # Transcript quality check
    if not _check_transcript_quality(patient_id, transcript):
        ledger["call1_status"] = "failed: transcript quality check"
        ledger["error"] = "transcript quality check failed"
        return None, ledger

    # Call 1 — always runs
    logger.info(f"[{patient_id}] Running call 1")
    try:
        call1_output = run_call1(transcript)
        ledger["call1_status"] = "success"
        logger.info(f"[{patient_id}] Call 1 succeeded")
    except Exception as e:
        ledger["call1_status"] = f"failed: {e}"
        ledger["error"] = str(e)
        logger.error(f"[{patient_id}] Call 1 failed: {e}")
        return None, ledger

    # Call 2 — conditional
    call2_output: Call2Output | None = None
    if call1_output.biologic_status.on_biologic != BioligicStatusEnum.yes:
        logger.info(f"[{patient_id}] Running call 2 (biologic status: {call1_output.biologic_status.on_biologic.value})")
        try:
            call2_output = run_call2(transcript, call1_output)
            ledger["call2_status"] = "success"
            logger.info(f"[{patient_id}] Call 2 succeeded")
        except Exception as e:
            ledger["call2_status"] = f"failed: {e}"
            ledger["error"] = str(e)
            logger.error(f"[{patient_id}] Call 2 failed: {e}")
            return None, ledger
    else:
        ledger["call2_status"] = "skipped"
        logger.info(f"[{patient_id}] Call 2 skipped (confirmed on biologic)")

    # Call 3 — always runs
    logger.info(f"[{patient_id}] Running call 3")
    try:
        call3_output = run_call3(transcript, call1_output)
        ledger["call3_status"] = "success"
        logger.info(f"[{patient_id}] Call 3 succeeded")
    except Exception as e:
        ledger["call3_status"] = f"failed: {e}"
        ledger["error"] = str(e)
        logger.error(f"[{patient_id}] Call 3 failed: {e}")
        return None, ledger

    record = PatientRecord(
        metadata=ExtractionMetadata(
            patient_id=patient_id,
            model_used=MODEL,
            timestamp=datetime.now(timezone.utc),
        ),
        call1=call1_output,
        call2=call2_output,
        call3=call3_output,
    )

    _check_evidence_verbatim(record, transcript, patient_id)

    ledger["success"] = True
    return record, ledger


PATIENTS_DIR = Path(__file__).parent.parent / "data" / "processed_patients"


def _patient_path(patients_dir: Path, patient_id: str) -> Path:
    return patients_dir / f"{patient_id}.json"


def _write_patient(patients_dir: Path, ledger: dict, record: PatientRecord | None) -> None:
    patients_dir.mkdir(parents=True, exist_ok=True)
    path = _patient_path(patients_dir, ledger["patient_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "ledger": ledger,
            "record": record.model_dump(mode="json") if record is not None else None,
        }, f, indent=2, default=str)


def compile_results(
    patients_dir: Path = PATIENTS_DIR,
    output_path: Path = OUTPUT_PATH,
) -> None:
    """Compile all per-patient files into a single results.json for analysis."""
    ledgers, records = [], []
    for path in sorted(patients_dir.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        ledgers.append(entry["ledger"])
        if entry["record"] is not None:
            records.append(entry["record"])

    successes = sum(1 for l in ledgers if l["success"])
    output = {
        "pipeline_run_metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "total_patients": len(ledgers),
            "total_successes": successes,
            "total_failures": len(ledgers) - successes,
        },
        "ledger": ledgers,
        "records": records,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Compiled {len(records)} records into {output_path}")


def run_pipeline(
    data_path: Path = DATA_PATH,
    patients_dir: Path = PATIENTS_DIR,
    output_path: Path = OUTPUT_PATH,
) -> list[PatientRecord]:
    interviews = load_interviews(data_path)
    total = len(interviews)
    logger.info(f"Starting pipeline: {total} patients, model={MODEL}")

    records: list[PatientRecord] = []

    for i, patient in enumerate(interviews):
        patient_id = patient.get("patient_id", f"unknown_{i}")
        patient_file = _patient_path(patients_dir, patient_id)

        if patient_file.exists():
            existing = json.loads(patient_file.read_text(encoding="utf-8"))
            if existing.get("ledger", {}).get("success"):
                logger.info(f"[{patient_id}] Skipping (already succeeded)")
                continue
            logger.info(f"[{patient_id}] Retrying (previous attempt failed)")

        logger.info(f"Processing patient {i + 1}/{total}: {patient_id}")
        record, ledger = process_patient(patient)

        _write_patient(patients_dir, ledger, record)
        if record is not None:
            records.append(record)
        logger.info(f"[{patient_id}] Saved to {patient_file.name} (success={ledger['success']})")

    successful = sum(1 for p in patients_dir.glob("*.json") if json.loads(p.read_text()).get("ledger", {}).get("success"))
    logger.info(f"Pipeline complete: {successful}/{total} succeeded")

    compile_results(patients_dir, output_path)
    return records


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    run_pipeline()
