# Infraestructura y providers

## El costo real no es la infra

A escala baja/media, el gasto dominante es el LLM, no la infraestructura. Con datos reales del proyecto (muestra de 8 CVs procesados):

| Modelo | Promedio por CV |
|---|---|
| Gemini 2.5 Flash Lite (primario) | $0.000208 |
| GPT-4.1-nano (fallback) | $0.000384 |
| **Promedio overall** | **$0.000252** |

La infra GCP a 5,000 CVs/día cuesta menos de $5/mes. Optimizar el proveedor cloud antes de tener escala real es gastar tiempo de engineering en algo que no mueve el revenue.

---

## Cómo funciona el free tier de GCP

GCP tiene dos cosas distintas que llama "free":

**Always Free** — permanente, se renueva cada mes, no expira:

| Servicio | Free tier mensual |
|---|---|
| Cloud Run (Service + Jobs) | 180k vCPU-segundos + 360k GB-segundos + 2M requests |
| GCS | 5 GB storage + 5k operaciones escritura + 50k lectura |
| Cloud Logging | 50 GB ingestion |
| Artifact Registry | 0.5 GB (imagen Docker) |

**$300 de crédito de prueba** — solo cuentas nuevas, válido 12 meses. No aplica si ya tenés cuenta activa.

### Lo que el free tier NO cubre

**Gemini API y OpenAI son APIs externas** — no son servicios de GCP. Sus costos se pagan directamente a Google AI y OpenAI independientemente del plan de GCP que tengas. El free tier no los toca.

```
Costo total ≈ Costo LLM = CVs procesados × $0.000208
```

La infra es ruido hasta procesar millones de CVs por mes.

### Costos según volumen

| Escenario | Infra GCP | LLM (Gemini) | Total |
|---|---|---|---|
| Deployado, sin usuarios | $0 | $0 | **$0/mes** |
| ~500 CVs/día (5-10 personas) | $0 (free tier) | $3 | **~$3/mes** |
| ~5,000 CVs/día (50 personas × 100 CVs) | ~$1 | ~$38 | **~$39/mes** |

---

## Ventajas concretas de GCP para este proyecto

### Free tier permanente (no trial de 12 meses)

| Servicio | Free tier mensual |
|---|---|
| Cloud Run (Service + Jobs) | 180k vCPU-segundos + 360k GB-segundos + 2M requests |
| GCS | 5 GB storage + 50k operaciones de lectura |
| Cloud Logging | 50 GB ingestion |
| Artifact Registry | 0.5 GB (imagen Docker) |

A 5,000 CVs/día (~30,000 vCPU-segundos/mes de Job), la infra cuesta $0 de Cloud Run.

### Cloud Run Jobs es un fit natural para este patrón

Run-to-completion con retry automático, concurrencia configurable, y pago por segundo de ejecución real. El equivalente en AWS (Fargate Tasks + SQS) requiere más piezas. No hay alternativa igual de simple en otros providers.

### Gemini corre en la misma red

Los modelos `gemini/*` se llaman vía la API pública de Google AI. Si migrás a Vertex AI (ver sección siguiente), el tráfico Cloud Run → Vertex es red interna de Google → egress $0. Desde AWS o Hetzner, cada llamada a Gemini pagaría egress de salida.

### IAM service-to-service sin gestionar secretos

Auth entre servicios vía SA tokens nativos. No hay API keys rotando entre servicios.

---

## Vertex AI vs API pública de Gemini

El proyecto usa `gemini/gemini-2.5-flash-lite` (Google AI Studio / API pública). Migrar a `vertex_ai/gemini-2.5-flash-lite` da:

| Dimensión | API pública (actual) | Vertex AI |
|---|---|---|
| Egress desde Cloud Run | ~$0 (red interna de Google) | ~$0 (red interna de Google) |
| Rate limits | Por API key, fijo | Por proyecto GCP, **incrementable con un ticket** |
| SLA | Ninguno | SLA formal de uptime |
| Precio del modelo | Igual | Igual |
| Context caching | No funciona con el setup actual | Funciona con prompts >32k tokens |

> El egress no es la ventaja — ambos endpoints (`generativelanguage.googleapis.com` y `aiplatform.googleapis.com`) se enrutan por la red interna de GCP desde Cloud Run. La ventaja real es el rate limit y el SLA.

**Cómo migrar:** una línea en `src/app/config.py`:
```python
# De:
"gemini/gemini-2.5-flash-lite"
# A:
"vertex_ai/gemini-2.5-flash-lite"
```

Requiere: activar Vertex AI API en el proyecto GCP + dar permiso `roles/aiplatform.user` a la SA del Job.

---

## Por qué el caché de Gemini no funciona hoy

`prompt.py:73` setea `cache_control: {"type": "ephemeral"}` en el system message. Ese campo es **sintaxis de Claude/Anthropic** — LiteLLM no lo traduce a Gemini.

Evidencia en los datos reales del `.local_bucket`:
- Todas las llamadas Gemini: `cached_tokens: 0`
- Llamadas GPT-4.1-nano (fallback): `cached_tokens: 1792` ← OpenAI prefix caching automático sí funciona

Para que Gemini cachee vía Vertex AI hace falta:
1. Usar `vertex_ai/` prefix en el modelo.
2. Prompt total >32k tokens (mínimo requerido por Vertex AI context caching).
3. Usar la API de context caching de Vertex explícitamente.

Con el system prompt actual (~800 tokens) **no se alcanza el mínimo de 32k** aunque se migrara a Vertex. El caché de Gemini sólo valdría la pena si la JD fuera extremadamente larga o si se agregara mucho más contexto al system message.

**Conclusión práctica:** el caché funciona hoy sólo para OpenAI. Con Gemini los costos son los ya medidos ($0.000208/CV) sin descuento.

---

## Cloud Run Jobs: CPU/Memory

**Spoiler: no vale la pena optimizar a esta escala.**

A 5,000 CVs/día el Job consume ~30,000 vCPU-segundos/mes, dentro del free tier de 180,000.
Incluso a 10× el volumen (50,000 CVs/día) el costo sería ~$3/mes.

Mínimo técnico viable: **1 vCPU + 512 MB RAM**. Menos que eso afecta la performance de PyMuPDF (parsing de PDFs) y las 20 llamadas async concurrentes del Semaphore.

Si alguna vez el compute del Job aparece en la factura como algo relevante, la respuesta es spot nodes en GKE, no bajar la config de Cloud Run.

---

## Comparación de providers

### GCP Cloud Run (recomendado, stack actual)
✅ Scale to zero, free tier generoso, Cloud Run Jobs, IAM nativo, Gemini en la misma red.  
❌ Vendor lock-in en Cloud Run Jobs si querés migrar el worker.

### AWS (Lambda + Fargate + S3)
✅ Ecosistema maduro, más opciones de cómputo.  
❌ Lambda tiene límite de 15 minutos de ejecución — un job con 200+ CVs puede superarlo. Necesitaría SQS + Lambda fan-out, que es más complejo. Costos similares a GCP.  
**Veredicto:** viable pero más piezas para el mismo resultado.

### Modal.com
✅ Diseñado para workloads AI/ML. SDK Python excelente. Pay-per-second. Pricing competitivo. Mapea casi 1:1 con el modelo actual (`@app.function` ≈ Cloud Run Job).  
❌ Migración real (reescribir el entrypoint del worker y el dispatch). Vendor más nuevo, menor garantía de uptime.  
**Veredicto:** la alternativa más interesante si en algún momento se quiere salir de GCP.

### Fly.io / Railway / Render
✅ Buenas para APIs web siempre-on.  
❌ El patrón de batch job run-to-completion no es su caso de uso. Workarounds necesarios.  
**Veredicto:** descartados para este stack.

### Hetzner VPS + Docker (Celery/ARQ)
✅ Lo más barato en costo puro con carga constante. Un AX41 (8 cores, 64 GB RAM) = €54/mes.  
❌ Sin scale-to-zero. Hay que operar infra. El costo de engineering supera el ahorro hasta tener factura de Cloud Run >$200/mes.  
**Veredicto:** válido sólo si el costo de infra se vuelve el problema principal y la carga es predecible.

---

## Web apps siempre encendidas en GCP

Para un frontend o dashboard que no puede tener cold start:

```bash
gcloud run deploy mi-app --min-instances=1 ...
```

`--min-instances=1` mantiene un container caliente. Costo: ~$6-10/mes para una instancia liviana (e2-micro equivalent). El resto de los beneficios de Cloud Run (scale-up bajo carga, managed TLS, etc.) se mantienen.

**Por qué no App Engine:** Google no desarrolla App Engine activamente — Cloud Run es el sucesor recomendado. App Engine Flexible no escala a cero ($40+/mes de piso). App Engine Standard tiene timeouts cortos, inadecuados para batch.

**Por qué no GKE para una sola app:** administrar nodes, deployments, services, ingress y certificates para un solo servicio es overhead desproporcionado.

---

## Cuándo migrar de Cloud Run a GKE

No hay una cifra exacta — hay dos señales concretas:

**Señal 1: costo**  
Si los Cloud Run Jobs están corriendo >14-16 horas por día de forma consistente, GKE con spot nodes (hasta 70% más barato) empieza a ganar. En la práctica: cuando la factura de Cloud Run supera $150-200/mes.

**Señal 2: control**  
Cloud Run Jobs tiene límite de 10k tasks por execution y timeout máximo de 24h. Si necesitás jobs más largos o mayor paralelismo por execution, GKE lo resuelve sin cambiar el código del worker (es el mismo container).

La migración a GKE no requiere cambiar `cv_processor.py`, `llm.py` ni `storage.py` — sólo el entrypoint del worker y el sistema de dispatch.

---

## Cálculo de costos: 50 personas × 100 CVs/día

**Volumen:** 5,000 CVs/día = 150,000 CVs/mes

### LLM (costo dominante)

Basado en datos reales del proyecto (Gemini 2.5 Flash Lite, promedio de 6 CVs medidos):

| Escenario | Costo/CV | Total mensual |
|---|---|---|
| Optimista (todo Gemini, sin imágenes pesadas) | $0.000170 | **$25.50** |
| Realista (mix Gemini + ocasional fallback GPT) | $0.000252 | **$37.80** |
| Pesimista (muchas imágenes, más fallbacks) | $0.000400 | **$60.00** |

### Infraestructura GCP

| Servicio | Uso mensual | Costo |
|---|---|---|
| Cloud Run Jobs (1 vCPU × ~20s × 50 jobs/día) | ~30,000 vCPU-s | **$0** (dentro del free tier de 180k) |
| Cloud Run Service (API) | ~16,500 requests | **$0** (free tier 2M requests) |
| GCS storage | ~10 GB (CVs en tránsito + results) | **$0.10** |
| GCS operaciones | ~160k writes + 300k reads | **$0.90** |
| Egress | Mínimo | **$0.05** |
| **Total infra** | | **~$1.05** |

### Total

| | Mensual |
|---|---|
| LLM (realista) | $37.80 |
| Infraestructura GCP | $1.05 |
| **Total** | **~$39/mes** |

A este volumen el 97% del gasto es LLM. Optimizar la infra mueve centavos. Optimizar el modelo (tier, caching cuando aplique, evitar fallbacks) mueve dólares.
