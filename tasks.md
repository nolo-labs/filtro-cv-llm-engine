# Tasks

## 🔴 Antes del primer deploy

- [ ] **Commitear cambios de la sesión actual**
  Hay 12 archivos modificados y 5 docs nuevos sin commitear (resultado JSON, CLAUDE.md, docs/).
  `git add` + `git commit` con todo lo de esta sesión.

- [ ] **Eliminar `litellm.set_verbose = True`** — `src/app/llm.py:18`
  Está marcado como temporal ("Remover una vez identificado el problema con Gemini"). El problema ya está identificado y documentado en `docs/llm.md`. Removerlo o reemplazarlo por una env var `DEBUG_LLM=1`.

- [ ] **Limpiar `.local_bucket/`**
  Los archivos de test tienen la estructura JSON vieja (flat, sin `telemetry` anidado). Borrar todo el contenido de `.local_bucket/` y verificar que `make test` vuelve a pasar y genera archivos con la estructura nueva.

- [ ] **Sacar el PDF personal del repo** — `cvs/Presupuesto Sauce Inmobiliaria - Pablo Novero.pdf`
  Está en el working tree sin commitear. Borrarlo o moverlo fuera del repo. Agregar `cvs/` al `.gitignore` si no está ya.

---

## 🟡 Próximo

- [ ] **Definir y documentar la convención de `job_id`**
  El motor no aísla tenants — el `job_id` es el único mecanismo de separación. Acordar con la plataforma el formato (ej. `{tenant_id}-{uuid}`) y documentarlo en `docs/integration.md`. Sin esto, dos clientes con el mismo `job_id` se pisan.

- [ ] **Diseñar los tiers por funcionalidad de cliente**
  `src/app/config.py` tiene el comentario "Los tiers se redesignarán por funcionalidades de cliente, no por calidad de modelo". Definir qué significa eso: ¿tier = plan de pricing? ¿tier = features habilitados (ej. datos de contacto extra, scoring extendido)? Documentar la decisión antes de implementar.

- [ ] **Job cleanup — política de retención del bucket**
  El motor no borra nada. Con el tiempo el bucket acumula prefijos de jobs viejos. Decidir la política (ej. borrar jobs con más de 30 días) e implementar como un endpoint `DELETE /jobs/{job_id}` o un Cloud Scheduler que corra periódicamente. Documentado como gap en `docs/integration.md`.

---

## 🟢 Backlog

- [ ] **Alerta de rate limit de Gemini**
  Crear una alerta en Cloud Logging que dispare cuando aparezcan errores 429 de Gemini en los logs del Job. Esa es la señal para evaluar migración a Vertex AI (ver `docs/infra.md`).

- [ ] **Migración a Vertex AI**
  Cuando la alerta de rate limit empiece a disparar frecuentemente. Cambio: una línea en `src/app/config.py` (`gemini/` → `vertex_ai/`) + dar permiso `roles/aiplatform.user` a la SA del Job. Ver `docs/infra.md` para el análisis completo.
