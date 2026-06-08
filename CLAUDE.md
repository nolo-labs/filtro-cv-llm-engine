# CLAUDE.md

Motor de screening de CVs. Dos deploys en Cloud Run que comparten un bucket GCS: un **Service** FastAPI que recibe jobs y un **Job** que procesa los CVs en paralelo con LiteLLM.

## Arquitectura rápida

```
backend-interno → POST /jobs → Cloud Run Service (main.py)
                                     │ dispara
                                     ▼
                               Cloud Run Job (worker.py)
                                     │ asyncio + Semaphore
                                     ▼
                               GCS  jobs/{job_id}/{cvs,results,errors}/
```

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/app/main.py` | Endpoints FastAPI — Service |
| `src/app/worker.py` | Entrypoint del Job: `run_job(job_id)` |
| `src/app/cv_processor.py` | `process_one_cv` — orquesta extracción + LLM + escritura |
| `src/app/llm.py` | `call_llm` con LiteLLM + fallbacks |
| `src/app/prompt.py` | Builders de mensajes (system + user texto/imagen) |
| `src/app/text_extraction.py` | Extrae texto de PDF/DOCX/TXT/MD |
| `src/app/storage.py` | Wrapper GCS (filesystem en LOCAL_MODE) |
| `src/app/jobs_dispatch.py` | Dispara Cloud Run Job execution |
| `src/app/guardrails.py` | Valida la JD contra prompt injection |
| `src/app/pydantic_models.py` | `Outputllm`, `Contacto`, `JDValidation` |
| `src/app/config.py` | Env vars, MODEL_TIERS, formatos soportados |

## Inicio rápido

```bash
export GEMINI_API_KEY=...
make dev        # API local en http://localhost:8000
make test       # end-to-end (otra terminal)
```

## Documentación detallada

- [`docs/architecture.md`](docs/architecture.md) — Cloud Run wiring, bucket layout, flujo por CV, idempotencia, auth
- [`docs/llm.md`](docs/llm.md) — LiteLLM, model tiers, fallback chains, prompt caching, vision
- [`docs/config.md`](docs/config.md) — env vars, constantes, cómo agregar campos/formatos/tiers
- [`docs/dev.md`](docs/dev.md) — dev local, Makefile, deploy
- [`docs/integration.md`](docs/integration.md) — contrato de API para el servicio consumidor
- [`docs/infra.md`](docs/infra.md) — providers, ventajas de GCP, Vertex AI, caché Gemini, cálculo de costos

## No hacer

- **No LangChain.** Stack es LiteLLM + Pydantic.
- **No Pub/Sub per-CV.** El modelo es 1 job = 1 Cloud Run Job execution.
- **No Firestore.** Estado en GCS, se reconstruye listando.
- **No Tesseract.** Imágenes van al LLM multimodal.
- **No leer/escribir el bucket fuera de `storage.py`.**
- **No procesar lotes en `process_one_cv`.** Unidad = CV individual.
- **No abrir el endpoint públicamente.** `--no-allow-unauthenticated` siempre.
- **No fallar el Job por errores de un CV.** Los errores se persisten como `errors/*.json` y se absorben.
