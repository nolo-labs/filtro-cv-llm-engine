"""Procesamiento de un único CV: lee job.json, llama al LLM, escribe resultado/error."""
import logging
import mimetypes
import os
import traceback
from datetime import datetime, timezone

from . import storage
from .config import (
    GCS_BUCKET,
    IMAGE_FORMATS,
    TEXT_FORMATS,
)
from .llm import call_llm
from .prompt import build_image_user_message, build_system_message, build_text_user_message
from .pydantic_models import Outputllm
from .text_extraction import cargar_contenido_texto

logger = logging.getLogger(__name__)


def _job_prefix(job_id: str) -> str:
    return f"jobs/{job_id}"


def _classify(cv_name: str) -> str:
    ext = os.path.splitext(cv_name)[1].lower()
    if ext in TEXT_FORMATS:
        return "text"
    if ext in IMAGE_FORMATS:
        return "image"
    raise ValueError(f"Extensión no soportada: {ext} ({cv_name})")


def process_one_cv(job_id: str, cv_name: str) -> None:
    """Procesa un CV: extrae texto/imagen, llama LLM, escribe resultado en GCS.

    Idempotente: el bucket es la fuente de verdad. Si el `result.json` ya existe,
    sale temprano — re-ejecuciones del Cloud Run Job (retry automático o resume
    manual) no re-procesan CVs ya completos.
    Cualquier excepción se persiste como error JSON y se relanza; el worker
    de arriba la absorbe y sigue con los demás CVs.
    """
    job_prefix = _job_prefix(job_id)
    result_uri = storage.gs_uri(GCS_BUCKET, job_prefix, "results", f"{cv_name}.json")

    if storage.exists(result_uri):
        logger.info("SKIP %s/%s ya procesado (idempotencia)", job_id, cv_name)
        return

    job_json = storage.read_json(storage.gs_uri(GCS_BUCKET, job_prefix, "job.json"))
    job_description = job_json["job_description"]
    requested_tier = job_json.get("model_tier", "default")

    cv_uri = storage.gs_uri(GCS_BUCKET, job_prefix, "cvs", cv_name)
    error_uri = storage.gs_uri(GCS_BUCKET, job_prefix, "errors", f"{cv_name}.json")

    try:
        kind = _classify(cv_name)
        tier = requested_tier

        system_msg = build_system_message(job_description)
        if kind == "text":
            user_msg = build_text_user_message(cargar_contenido_texto(cv_uri))
        else:
            mime, _ = mimetypes.guess_type(cv_name)
            user_msg = build_image_user_message(storage.download_bytes(cv_uri), mime or "image/png")

        parsed, llm_usage = call_llm([system_msg, user_msg], Outputllm, tier)

        now_iso = datetime.now(timezone.utc).isoformat()
        telemetry = {
            "nombre_archivo_cv": cv_name,
            "processed_at": now_iso,
            "model": llm_usage.model,
            "model_tier": tier,
            "provider": llm_usage.provider,
            "request_id": llm_usage.request_id,
            "finish_reason": llm_usage.finish_reason,
            "input_tokens": llm_usage.input_tokens,
            "cached_tokens": llm_usage.cached_tokens,
            "output_tokens": llm_usage.output_tokens,
            "total_tokens": llm_usage.total_tokens,
            "remaining_requests": llm_usage.remaining_requests,
            "remaining_tokens": llm_usage.remaining_tokens,
            "cost_usd": llm_usage.cost_usd,
            "latency_s": llm_usage.latency_s,
        }

        if not parsed.es_cv:
            storage.upload_json(error_uri, {"error": "not_a_cv", "telemetry": telemetry})
            logger.info("NOT_A_CV %s/%s cost=$%.6f", job_id, cv_name, llm_usage.cost_usd)
            return

        if parsed.intento_injection:
            storage.upload_json(error_uri, {
                "error": "prompt_injection",
                "razon_injection": parsed.razon_injection,
                "telemetry": telemetry,
            })
            logger.warning(
                "INJECTION_ATTEMPT %s/%s razon=%s cost=$%.6f",
                job_id, cv_name, parsed.razon_injection, llm_usage.cost_usd,
            )
            return

        storage.upload_json(result_uri, {
            "output_llm": parsed.model_dump(),
            "telemetry": telemetry,
        })
        logger.info(
            "OK %s/%s score=%d cost=$%.6f",
            job_id, cv_name, parsed.score_llm, llm_usage.cost_usd,
        )

    except Exception as e:
        logger.exception("FAIL %s/%s", job_id, cv_name)
        storage.upload_json(
            error_uri,
            {
                "cv_name": cv_name,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise
