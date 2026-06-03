"""Llamada al LLM via LiteLLM, provider-agnóstica con fallbacks y telemetría de costo."""
import logging
import time
from dataclasses import dataclass
from typing import Optional, Type, TypeVar

import litellm
from pydantic import BaseModel

from .config import DEFAULT_MODEL_TIER, MODEL_TIERS

logger = logging.getLogger(__name__)

# Drop the default JSON-schema validator y deja que Pydantic valide en client-side.
litellm.drop_params = True

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMUsage:
    model: str  # modelo que efectivamente respondió (puede ser un fallback)
    provider: Optional[str]  # custom_llm_provider: "gemini" / "openai" / ...
    request_id: Optional[str]  # id del provider, útil para soporte y debugging
    finish_reason: Optional[str]  # "stop" (normal), "length" (truncado), "content_filter", ...
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int  # subset de input_tokens servido desde prompt cache (0 si no aplica)
    remaining_requests: Optional[int]  # rate-limit budget restante (None si el provider no lo expone)
    remaining_tokens: Optional[int]
    cost_usd: float
    latency_s: float


def _resolve_model_chain(model_tier: str) -> tuple[str, list[str]]:
    """Devuelve (primary_model, fallbacks) para el tier. Acepta tanto str como list[str] en MODEL_TIERS."""
    if model_tier not in MODEL_TIERS:
        raise ValueError(
            f"model_tier desconocido: {model_tier}. Disponibles: {list(MODEL_TIERS)}"
        )
    chain = MODEL_TIERS[model_tier]
    if isinstance(chain, str):
        return chain, []
    if not chain:
        raise ValueError(f"MODEL_TIERS['{model_tier}'] está vacío")
    return chain[0], list(chain[1:])


def call_llm(
    messages: list[dict],
    response_model: Type[T],
    model_tier: str = DEFAULT_MODEL_TIER,
) -> tuple[T, LLMUsage]:
    """Invoca al LLM y devuelve la respuesta parseada como Pydantic + telemetría.

    Si el primary_model del tier tira RateLimitError u otro error transitorio, LiteLLM
    salta automáticamente al siguiente modelo de la cadena (vía `fallbacks=`).
    `LLMUsage.model` refleja el modelo que efectivamente respondió.
    """
    primary_model, fallbacks = _resolve_model_chain(model_tier)

    t0 = time.perf_counter()
    response = litellm.completion(
        model=primary_model,
        messages=messages,
        response_format=response_model,
        temperature=0,
        fallbacks=fallbacks,
        num_retries=2,
    )
    latency = time.perf_counter() - t0

    raw = response.choices[0].message.content
    parsed = response_model.model_validate_json(raw)

    usage = response.usage
    hidden = getattr(response, "_hidden_params", {}) or {}
    cost = float(hidden.get("response_cost") or 0.0)
    actual_model = getattr(response, "model", None) or primary_model
    provider = hidden.get("custom_llm_provider")
    request_id = getattr(response, "id", None)
    finish_reason = getattr(response.choices[0], "finish_reason", None)

    # LiteLLM normaliza el conteo de prompt-cache de los tres providers a
    # `usage.prompt_tokens_details.cached_tokens` (formato OpenAI).
    details = getattr(usage, "prompt_tokens_details", None)
    cached_tokens = int(getattr(details, "cached_tokens", 0) or 0) if details else 0

    # Rate-limit headers: cada provider usa nombres distintos. Buscamos los más comunes.
    remaining_requests, remaining_tokens = _extract_rate_limit(hidden.get("additional_headers") or {})

    telemetry = LLMUsage(
        model=actual_model,
        provider=provider,
        request_id=request_id,
        finish_reason=finish_reason,
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        cached_tokens=cached_tokens,
        remaining_requests=remaining_requests,
        remaining_tokens=remaining_tokens,
        cost_usd=cost,
        latency_s=round(latency, 3),
    )
    if actual_model != primary_model:
        logger.warning(
            "LLM fallback model=%s primary_model=%s tier=%s",
            actual_model, primary_model, model_tier,
        )
    if finish_reason and finish_reason != "stop":
        logger.warning(
            "LLM finish_reason=%s model=%s request_id=%s — respuesta posiblemente incompleta",
            finish_reason, actual_model, request_id,
        )
    logger.info(
        "LLM ok model=%s in=%d cached=%d out=%d total=%d cost=$%.6f latency=%.2fs finish=%s id=%s rl_req=%s rl_tok=%s",
        telemetry.model,
        telemetry.input_tokens,
        telemetry.cached_tokens,
        telemetry.output_tokens,
        telemetry.total_tokens,
        telemetry.cost_usd,
        telemetry.latency_s,
        telemetry.finish_reason,
        telemetry.request_id,
        telemetry.remaining_requests,
        telemetry.remaining_tokens,
    )
    return parsed, telemetry


def _extract_rate_limit(headers: dict) -> tuple[Optional[int], Optional[int]]:
    """Devuelve (remaining_requests, remaining_tokens) buscando los nombres usados por cada provider.

    OpenAI/Azure:   x-ratelimit-remaining-{requests,tokens}
    Gemini:         no expone rate-limit en headers HTTP (se gestiona vía quotas del proyecto)
    """
    if not headers:
        return None, None
    # Normalizar keys a lowercase para evitar problemas de case-sensitivity
    h = {k.lower(): v for k, v in headers.items()}
    candidates_req = ("x-ratelimit-remaining-requests",)
    candidates_tok = ("x-ratelimit-remaining-tokens",)
    req = _first_int(h, candidates_req)
    tok = _first_int(h, candidates_tok)
    return req, tok


def _first_int(headers: dict, keys: tuple[str, ...]) -> Optional[int]:
    for k in keys:
        if k in headers:
            try:
                return int(headers[k])
            except (TypeError, ValueError):
                return None
    return None
