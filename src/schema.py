from pydantic import BaseModel, Field
from enum import StrEnum
from datetime import datetime

class ExtractionMetadata(BaseModel):
    patient_id: str
    model_used: str
    timestamp: datetime

class CertaintyEnum(StrEnum):
    high = "high"      # explicitly stated
    medium = "medium"  # reasonably inferred
    low = "low"        # speculative, minimal evidence
    

class CompletenessEnum(StrEnum):
    complete = "complete"                        # Patient describes a full treatment journey with a clear endpoint
    likely_truncated = "likely_truncated"        # Patient's journey appears incomplete, key stages missing or vague
    heavily_truncated = "heavily_truncated"      # Patient disengaged early, very little journey information available
    
class BioligicStatusEnum(StrEnum):
    yes = "yes"    
    no = "no" 
    unknown = "unknown" 


class ChurnDetection(BaseModel):
    completeness: CompletenessEnum = Field(
        description=(
            "How complete the patient's treatment journey appears. "
            "complete: Patient describes a full treatment journey with a clear endpoint. "
            "likely_truncated: Patient's journey appears incomplete, key stages missing or vague. "
            "heavily_truncated: Patient disengaged early, very little journey information available. "
        )
    )
    reasoning: str = Field(
        description="One sentence explaining why you classified the completeness this way."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are about the completeness classification."
    )


class BioligicStatus(BaseModel):
    on_biologic: BioligicStatusEnum = Field(
        description="Whether the patient is currently on a biologic or not. Use unknown if the transcript is ambiguous or truncated before this is clear."
    )
    name: str | None = Field(
        description="Brand or generic name of the biologic as mentioned by the patient. Null if not on a biologic or not mentioned."
    )
    reasoning: str = Field(
        description="If explicitly stated, provide a verbatim quote from the transcript. If ambiguous or unknown, explain in one sentence why the status is unclear."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are based on the available evidence."
    )

class SexEnum(StrEnum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"
    
class AgeField(BaseModel):
    value: int | None = Field(description="Patient age in years. Null if not mentioned.")
    evidence: str = Field(description="Verbatim quote from the transcript supporting this value.")
    certainty: CertaintyEnum = Field(description="How certain you are based on the available evidence.")

class SexField(BaseModel):
    value: SexEnum | None = Field(description="Patient sex. Null if not mentioned or unclear.")
    evidence: str = Field(description="Verbatim quote from the transcript supporting this value.")
    certainty: CertaintyEnum = Field(description="How certain you are based on the available evidence.")

class YearsWithCrohnsField(BaseModel):
    value: float | None = Field(description="Number of years the patient has had Crohn's disease. Null if not mentioned.")
    evidence: str = Field(description="Verbatim quote from the transcript supporting this value.")
    certainty: CertaintyEnum = Field(description="How certain you are based on the available evidence.")

class Sociodemographics(BaseModel):
    age: AgeField
    sex: SexField
    years_with_crohns: YearsWithCrohnsField


class TreatmentStatusEnum(StrEnum):
    discussed = "discussed" 
    rejected = "rejected" 
    currently_on = "currently_on" 
    stopped = "stopped" 

class Treatment(BaseModel):
    name: str = Field(
        description="Drug name as mentioned by the patient."
    )
    status: TreatmentStatusEnum = Field(
        description="discussed: mentioned but never started. currently_on: actively taking it. stopped: tried and discontinued. rejected: explicitly refused or ruled out before starting."
    )
    evidence: str = Field(
        description="Verbatim quote from the transcript supporting this treatment entry."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are based on the available evidence."
    )

class Call1Output(BaseModel):
    churn_detection: ChurnDetection
    biologic_status: BioligicStatus
    sociodemographics: Sociodemographics
    treatment_journey: list[Treatment]



class BiologicStatusDetailEnum(StrEnum):
    not_mentioned = "not_mentioned"                  # Biologic topic never came up
    not_reached = "not_reached"                      # Journey hasn't progressed to biologic consideration yet
    churned = "churned"                              # Transcript cut off before we could find out
    discussed_no_decision = "discussed_no_decision"  # Discussed but no firm outcome reached
    explicitly_rejected = "explicitly_rejected"      # Actively decided against by patient or doctor


class BiologicStatusDetail(BaseModel):
    status: BiologicStatusDetailEnum = Field(
        description="not_mentioned: biologic never came up. not_reached: journey hasn't progressed to biologic consideration. churned: transcript cut off before we could find out. discussed_no_decision: discussed but no firm decision reached (e.g., patient or doctor expressed hesitations). explicitly_rejected: actively decided against by patient or doctor."
    )
    reasoning: str = Field(
        description="One sentence explaining why you classified the status this way, or a verbatim quote from the transcript if a biologic was discussed or explicitly rejected."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are about this classification."
    )

class BarrierCategoryEnum(StrEnum):
    cost_insurance = "cost_insurance"    
    patient_fear = "patient_fear" 
    doctor_choice = "doctor_choice" 
    access = "access" 
    other = "other" 


class BarrierReason(BaseModel):
    category: BarrierCategoryEnum = Field(
        description="cost_insurance: financial barriers or insurance issues. patient_fear: fear of side effects, injections, or the medication itself. doctor_choice: doctor has not recommended it yet or is taking a watchful waiting approach. access: difficulty accessing specialist or treatment. other: any other reason."
    )
    evidence: str | None = Field(
        description="Verbatim quote from the transcript supporting this category."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are based on the available evidence."
    )


class Call2Output(BaseModel):
    biologic_status_detail: BiologicStatusDetail
    reasons: list[BarrierReason] | None 


class PathwayEndpointEnum(StrEnum):
    not_mentioned = "not_mentioned"                  # Biologic topic never came up
    not_reached = "not_reached"                      # Journey hasn't progressed to biologic consideration yet
    churned = "churned"                              # Transcript cut off before we could find out
    discussed_no_decision = "discussed_no_decision"  # Discussed but no firm outcome reached
    explicitly_rejected = "explicitly_rejected"      # Actively decided against by patient or doctor
    on_biologic = "on_biologic"                      # Patient is currently on a biologic

class PathwayEndpoint(BaseModel):
    status: PathwayEndpointEnum = Field(
        description="not_mentioned: biologic never came up. not_reached: journey hasn't progressed to biologic consideration. churned: transcript cut off before we could find out. discussed_no_decision: discussed but no firm decision reached. explicitly_rejected: actively decided against by patient or doctor. on_biologic: patient is currently on a biologic."
    )
    reasoning: str = Field(
        description="One sentence explaining why you classified the endpoint this way, or a verbatim quote from the transcript if a biologic was discussed, explicitly rejected, or is currently in use."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are about this classification."
    )


class PathwayStep(BaseModel):
    name: str = Field(
        description="Name of the healthcare provider or care setting visited, as mentioned by the patient."
    )
    evidence: str = Field(
        description="Verbatim quote from the transcript supporting this step."
    )
    certainty: CertaintyEnum = Field(
        description="How certain you are that this step occurred and belongs in the pathway."
    )

class Call3Output(BaseModel):
    pathway_endpoint: PathwayEndpoint
    referral_pathway: list[PathwayStep]


class PatientRecord(BaseModel):
    metadata: ExtractionMetadata
    call1: Call1Output
    call2: Call2Output | None
    call3: Call3Output

