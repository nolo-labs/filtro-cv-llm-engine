# LLM: modelos, tiers y configuración

## Stack

**LiteLLM** como capa de abstracción sobre providers (OpenAI, Google Gemini). No LangChain.

`call_llm(messages, response_model, model_tier)` en `src/app/llm.py`:
- Recibe los mensajes ya construidos y el modelo Pydantic de salida (`Outputllm`).
- LiteLLM convierte `Outputllm` a JSON Schema y lo envía como `response_format` al provider.
- Devuelve `(Outputllm, LLMUsage)` donde `LLMUsage` incluye tokens, cost_usd, latency_s, modelo efectivo.

## Model tiers

Definidos en `src/app/config.py::MODEL_TIERS`. Cada tier es una **lista** `[primary, *fallbacks]` en formato LiteLLM.

Estado actual: un único tier `default` con dos modelos:

```python
MODELS = [
    "gemini/gemini-2.5-flash-lite",   # primary (más barato)
    "openai/gpt-4.1-nano",            # fallback
]
MODEL_TIERS = {"default": MODELS}
```

El `model_tier` llega en el POST /jobs. Default: `default`.

> Los tiers se van a redesignar por funcionalidades de cliente, no por calidad de modelo.

## Fallback chain

Si el primary lanza `RateLimitError` u otro error transitorio, LiteLLM salta automáticamente al siguiente modelo de la cadena (vía `fallbacks=` + `num_retries=2`). `LLMUsage.model` refleja el modelo que **efectivamente respondió**.

## Prompt caching

El system message lleva `cache_control: {"type": "ephemeral"}` (`prompt.py:73`).

**Estado actual:**
- **OpenAI/GPT-4.1-nano**: caching automático de prefijos >1024 tokens — **funciona**. Confirmado: `cached_tokens: 1792` en las llamadas de fallback.
- **Gemini**: `cache_control: ephemeral` es sintaxis de Anthropic/Claude; LiteLLM **no la traduce a Gemini**. `cached_tokens: 0` en todas las llamadas Gemini. Para activar caching en Gemini se necesita Vertex AI con prompts >32k tokens — ver `docs/infra.md`.

## Vision (CVs como imagen)

Si `cv_name` tiene extensión de imagen (`.png`, `.jpg`, etc.), `process_one_cv` descarga los bytes y los pasa directo al LLM multimodal. **Sin Tesseract** — el LLM hace el OCR directamente. Más barato, más exacto, imagen Docker ~200 MB más liviana.

Ambos modelos del tier `default` (Gemini 2.5 Flash Lite y GPT-4.1-nano) soportan imágenes — no hay fallback especial para CVs imagen.

## Guardrails

Antes de procesar la JD, `src/app/guardrails.py` la valida contra `JDValidation` para detectar intentos de prompt injection en la descripción del puesto. Si `es_injection=True`, el job es rechazado en el POST /jobs con 400.

A nivel de CV individual, `Outputllm.intento_injection` detecta si el CV contiene instrucciones para manipular el evaluador.

## Agregar un tier nuevo

1. Agregar entrada en `MODEL_TIERS` en `src/app/config.py` como lista `[primary, *fallbacks]`.
2. Asegurarse de que las API keys del nuevo provider estén en el env de Cloud Run (Service y Job).
3. Todos los modelos de la lista deben soportar structured output y, si van a recibir CVs imagen, también multimodal.
