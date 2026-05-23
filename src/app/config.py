"""Configuración del motor de CV screening."""
import os

# --- GCP ---
# GCS_BUCKET y GCP_PROJECT cambian por entorno → env vars. El resto del runtime
# es config interna del proyecto y vive como constante acá.
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
GCP_PROJECT = os.getenv("GCP_PROJECT", "")

# Cloud Run Job que dispara el Service. Tienen que matchear con el deploy (Makefile).
# Si cambiás estos valores, actualizá también las variables del Makefile.
JOB_NAME = "cv-filter-batch"
JOB_REGION = "us-central1"

# Modo local: storage usa filesystem, el dispatcher invoca el worker en proceso (sin GCP)
LOCAL_MODE = os.getenv("LOCAL_MODE", "0") == "1"
LOCAL_BUCKET_DIR = "./.local_bucket"

# --- LLM ---
# Modelos disponibles: ambos soportan texto e imágenes (multimodal).
# Primary: gemini-2.5-flash-lite (más barato). Fallback: gpt-4.1-nano.
# Los tiers se redesignarán por funcionalidades de cliente, no por calidad de modelo.
MODELS: list[str] = [
    "gemini/gemini-2.5-flash-lite",
    "openai/gpt-4.1-nano",
]
# Alias de compatibilidad hasta que se rediseñen los tiers por features.
MODEL_TIERS: dict[str, list[str]] = {"default": MODELS}
DEFAULT_MODEL_TIER = "default"

# Concurrencia de llamadas LLM dentro de UN Job execution (asyncio.Semaphore).
MAX_CONCURRENT_LLM = 20

# --- Formatos soportados ---
TEXT_FORMATS = (".pdf", ".docx", ".txt", ".md")
IMAGE_FORMATS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
SUPPORTED_FORMATS = TEXT_FORMATS + IMAGE_FORMATS

# Truncado del texto del CV antes de enviarlo al LLM
MAX_CV_CHARS = 30000
