# Dev local y deploy

## Dev local

```bash
export GEMINI_API_KEY=...
make dev          # levanta FastAPI en http://localhost:8000 con LOCAL_MODE=1
```

En otra terminal:
```bash
make test         # sube cvs/, llama POST /jobs, polling, imprime resultados
```

`LOCAL_MODE=1` stubbea GCS (filesystem en `.local_bucket/`) y el dispatch de Cloud Run Jobs (corre el worker en el mismo proceso). No necesita credenciales GCP. Ver `docs/architecture.md` → sección LOCAL_MODE.

## Comandos útiles del Makefile

| Target | Qué hace |
|---|---|
| `make install` | Instala dependencias Python |
| `make dev` | FastAPI con recarga en LOCAL_MODE |
| `make test` | End-to-end contra `http://localhost:8000` |
| `make build` | Build de la imagen Docker |
| `make deploy PROJECT_ID=...` | Deploy completo (ver abajo) |
| `make logs` | Logs del Service en Cloud Run |
| `make logs-job` | Logs del Job en Cloud Run |
| `make clean` | Limpia `.local_bucket/` |

Variables overridables: `PROJECT_ID`, `SERVICE_NAME`, `JOB_NAME`, `REGION`, `BUCKET`.

## Deploy

```bash
export GEMINI_API_KEY=...       # provider primario
export OPENAI_API_KEY=...       # opcional: para fallback chains con OpenAI
make deploy PROJECT_ID=mi-proyecto
```

`make deploy` es idempotente y ejecuta en orden:
1. Build de imagen Docker compartida (misma imagen para Service y Job).
2. Creación del bucket GCS si no existe.
3. Creación de la SA `$SERVICE_NAME-worker` si no existe.
4. Deploy del **Service** `cv-filter-api` con `--no-allow-unauthenticated`.
5. Deploy del **Job** `cv-filter-batch` con `--command python --args -m,src.app.worker`.
6. IAM bindings: SA → `roles/storage.objectAdmin` sobre el bucket, SA → `roles/run.developer` sobre el proyecto.

## Docker

Misma imagen para Service y Job — el Job overridea el comando al deployarlo. La imagen es slim, sin Tesseract (~200 MB).
