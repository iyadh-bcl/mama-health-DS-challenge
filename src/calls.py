import json
import logging
import time
from typing import TypeVar

import json_repair
import litellm
from litellm.caching.caching import Cache
from pydantic import BaseModel, ValidationError

from .prompts import call1, call2, call3
from .schema import Call1Output, Call2Output, Call3Output

litellm.cache = Cache(type="disk")

MODEL = "gemini/gemini-3.1-flash-lite"
MAX_RATE_LIMIT_RETRIES = 5
RETRY_BASE_WAIT = 30  # seconds
SEED = 42

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _call(
    messages: list[dict],
    response_format: type[T],
    temperature: float | None = None,
) -> str:
    kwargs: dict = {}
    if temperature is not None:
        kwargs["temperature"] = temperature

    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = litellm.completion(
                model=MODEL,
                messages=messages,
                response_format=response_format,
                extra_body={"generationConfig": {"seed": SEED}},
                **kwargs,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from model")
            return content
        except (litellm.exceptions.RateLimitError, litellm.exceptions.ServiceUnavailableError) as e:
            if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                logger.error(f"{type(e).__name__}: all retries exhausted")
                raise
            wait = RETRY_BASE_WAIT * (2**attempt)
            logger.warning(f"{type(e).__name__} (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES}), retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError("Unreachable")


def _call_with_repair(messages: list[dict], response_format: type[T]) -> T:
    content = _call(messages, response_format, temperature=0.0)

    try:
        data = json.loads(content)
        return response_format.model_validate(data)
    except json.JSONDecodeError as e:
        logger.warning(f"JSONDecodeError, attempting json_repair: {e}")
        repaired = json_repair.repair_json(content)
        try:
            data = json.loads(repaired)
            return response_format.model_validate(data)
        except Exception as e2:
            logger.warning(f"json_repair insufficient, retrying call: {e2}")
    except ValidationError as e:
        logger.warning(f"ValidationError, retrying call: {e}")

    content = _call(messages, response_format, temperature=0.0)
    data = json.loads(content)
    return response_format.model_validate(data)







def run_call1(transcript: str) -> Call1Output:
    messages = [{"role": "user", "content": call1.format(transcript=transcript)}]
    return _call_with_repair(messages, Call1Output)


def run_call2(transcript: str, call1_output: Call1Output) -> Call2Output:
    biologic_status = (
        f"{call1_output.biologic_status.on_biologic.value} "
        f"(reasoning: {call1_output.biologic_status.reasoning})" # "yes (reasoning: I've been on Humira for five years)
    )
    journey_completeness = call1_output.churn_detection.completeness.value
    messages = [
        {
            "role": "user",
            "content": call2.format(
                transcript=transcript,
                biologic_status=biologic_status,
                journey_completeness=journey_completeness,
            ),
        }
    ]
    return _call_with_repair(messages, Call2Output)


def run_call3(transcript: str, call1_output: Call1Output) -> Call3Output:
    biologic_status = (
        f"{call1_output.biologic_status.on_biologic.value} "
        f"(reasoning: {call1_output.biologic_status.reasoning})" #"yes (reasoning: I've been on Humira for five years)
    )
    journey_completeness = call1_output.churn_detection.completeness.value
    messages = [
        {
            "role": "user",
            "content": call3.format(
                transcript=transcript,
                biologic_status=biologic_status,
                journey_completeness=journey_completeness,
            ),
        }
    ]
    return _call_with_repair(messages, Call3Output)
