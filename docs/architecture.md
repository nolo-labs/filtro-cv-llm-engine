# Arquitectura

Motor de screening de CVs compuesto por dos deploys en Cloud Run que comparten un bucket GCS.

## Componentes

```
Servicio interno (backend de la plataforma)
      │
      │ POST /jobs  {job_id, job_description, model_tier?}
      ▼
Cloud Run Service  cv-filter-api   (src/app/main.py)
   ├── POST /jobs     valida + escribe job.json + dispara Job execution → 202
   ├── GET  /jobs/{id} status: lista cvs/, results/, errors/ y suma cost_usd
   └── GET  /healthz
        │
        │ jobs_dispatch.run_job_execution(job_id)
        │   → run_v2.JobsClient().run_job(overrides={env: JOB_ID=<id>})
        ▼
Cloud Run Job  cv-filter-batch   (src/app/worker.py)
   │ asyncio.gather + Semaphore(MAX_CONCURRENT_LLM) sobre process_one_cv
   │ retry automático del execution (max-retries=3, configurable en Makefile)
   │
   └──► GCS  gs://$GCS_BUCKET/jobs/{job_id}/
```

## Layout del bucket

```
gs://$GCS_BUCKET/jobs/{job_id}/
├── cvs/{filename}              ← subido por upstream ANTES de POST /jobs
├── job.json                    ← {job_description, model_tier, total_cvs, created_at}
├── results/{filename}.json     ← presencia = éxito
└── errors/{filename}.json      ← presencia = fallo
```

El estado del job se deriva **listando prefijos** — no hay DB. GCS listing es fuertemente consistente.

## Flujo de un CV

```
process_one_cv(job_id, cv_name)
  1. storage.exists(result_uri)  → skip si ya procesado (idempotencia)
  2. Clasificar cv_name: texto (.pdf/.docx/.txt/.md) o imagen (.png/.jpg/...)
  3. Extraer contenido:
       texto  → text_extraction.cargar_contenido_texto (PyMuPDF / python-docx)
       imagen → bytes crudos (el LLM hace el OCR)
  4. call_llm([system_msg, user_msg], Outputllm, tier)
  5. Evaluar output:
       es_cv=False        → errors/{cv}.json  {"error": "not_a_cv", ...}
       intento_injection  → errors/{cv}.json  {"error": "prompt_injection", ...}
       OK                 → results/{cv}.json {"output_llm": {...}, "telemetry": {...}}
  6. Cualquier excepción → errors/{cv}.json  {"error": "...", "traceback": "..."}
                           raise (el worker absorbe y continúa con el siguiente CV)
```

## Idempotencia

`process_one_cv` chequea `storage.exists(result_uri)` al inicio y retorna inmediatamente si el resultado ya existe. Esto cubre:
- **Retry automático** del Cloud Run Job execution cuando crashea.
- **Re-disparo manual** para retomar un job parcialmente procesado.

El invariante es: si `results/{cv}.json` existe, ese CV está terminado. Nunca se sobreescribe.

## Auth e IAM

| Actor | Identidad | Permisos necesarios |
|---|---|---|
| Servicio upstream | SA propia | `roles/run.invoker` sobre `cv-filter-api` |
| Service `cv-filter-api` | SA `$SERVICE_NAME-worker` | `roles/run.developer` (para disparar el Job) + `roles/storage.objectAdmin` sobre el bucket |
| Job `cv-filter-batch` | SA `$SERVICE_NAME-worker` | `roles/storage.objectAdmin` sobre el bucket |

Cloud Run corre con `--no-allow-unauthenticated`. Los callers son SAs internas, nunca clientes externos.

## LOCAL_MODE

Con `LOCAL_MODE=1`:
- `storage` lee/escribe en `./.local_bucket/` (filesystem).
- `jobs_dispatch.run_job_execution` invoca `worker.run_job` en el mismo proceso (sin llamar a Cloud Run Jobs API).
- Permite correr `make dev` + `make test` sin credenciales GCP.
