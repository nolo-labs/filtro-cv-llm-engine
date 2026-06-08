# Configuración y extensión

## Variables de entorno

Solo lo que cambia por entorno o es secreto vive como env var. El resto vive en `src/app/config.py`.

| Var | Dónde se setea | Para qué |
|---|---|---|
| `GCS_BUCKET` | Service + Job | Bucket donde viven los jobs |
| `GCP_PROJECT` | Service | Project id para construir el job path al disparar el Cloud Run Job |
| `JOB_ID` | Job (inyectado por el Service) | job_id que el worker debe procesar |
| `OPENAI_API_KEY` | Service + Job | Provider OpenAI (tiers que lo incluyan) |
| `GEMINI_API_KEY` | Service + Job | Provider Google Gemini (default) |
| `LOCAL_MODE=1` | Solo dev | Stubea GCS y dispatch — ver `docs/architecture.md` |

## Constantes en `src/app/config.py`

| Constante | Default | Para qué |
|---|---|---|
| `MODELS` | `[gemini-2.5-flash-lite, gpt-4.1-nano]` | Lista de modelos: primary + fallback (ambos soportan texto e imágenes) |
| `MODEL_TIERS` | `{"default": MODELS}` | Fallback chains por tier — ver `docs/llm.md` |
| `DEFAULT_MODEL_TIER` | `"default"` | Tier si no viene `model_tier` en el POST |
| `MAX_CONCURRENT_LLM` | `5` | Semaphore en el worker — cuántas llamadas LLM en paralelo |
| `MAX_CV_CHARS` | `30000` | Truncamiento de texto antes del LLM |
| `TEXT_FORMATS` | `{.pdf, .docx, .txt, .md}` | Extensiones procesadas como texto |
| `IMAGE_FORMATS` | `{.png, .jpg, .jpeg, .bmp, .tiff, .webp}` | Extensiones enviadas al LLM multimodal |
| `JOB_NAME` | `cv-filter-batch` | Nombre del Cloud Run Job |
| `JOB_REGION` | `us-central1` | Región del Cloud Run Job |
| `LOCAL_BUCKET_DIR` | `.local_bucket` | Directorio filesystem en LOCAL_MODE |

## Cómo extender

### Agregar un campo al output del LLM

Tocar **un solo archivo**: `src/app/pydantic_models.py`. Agregar el campo a `Outputllm` con `Field(description=...)`. LiteLLM convierte el modelo a JSON Schema y el LLM lo pobla siguiendo la descripción.

### Agregar un formato de archivo

1. `src/app/config.py`: agregar la extensión a `TEXT_FORMATS` o `IMAGE_FORMATS`.
2. Si es texto: extender `_extract_text` en `src/app/text_extraction.py`.
3. Si es imagen: no hay nada que tocar — `process_one_cv` ya levanta los bytes y los pasa al LLM.

### Agregar un model tier

1. Agregar entrada en `MODEL_TIERS` en `src/app/config.py`.
2. Asegurarse de que las API keys del nuevo provider estén en el env de Cloud Run (Service y Job).
3. Todos los modelos de un tier deben soportar structured output (JSON Schema via LiteLLM).
