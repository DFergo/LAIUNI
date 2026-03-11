# HRDD Helper — Ideas & Improvements

Ideas captured during development. Reviewed when planning each sprint.

---

### Prompts monolíticos por perfil+caso + nuevo flujo de inicio
**Added:** 2026-03-10 | **Sprint:** 7c | **Effort:** L (2-3 días)

**Flujo nuevo:** idioma → disclaimer (qué es HRDD Helper + limitaciones AI, requiere aceptar) → session (new/recover) → selección de perfil (worker: worker/rep, organizer: organizer/officer) → auth si procede → instrucciones hardcoded por perfil → encuesta → chat.

**Prompts:** system + case_prompt (por perfil+caso) + context_template + post-processing. Elimina concatenación modular.

**Modos por perfil:**
- Worker: un solo prompt (documentar violación guiada)
- Representative: un solo prompt (documentar violación guiada)
- Organizer: Document, Interview, Advisory, Submit(?), Training(?)
- Officer: Document, Interview, Advisory, Submit(?), Training

**Encuesta:** Worker/Rep: solo company, country, description obligatorios (nota: anónimo permitido pero recomendado dejar contacto). Organizer/Officer: todo obligatorio excepto company en advisory/training.

**Relacionado:** Upload de documentos en chat (móvil compatible via `<input type="file">`, no sale de la SPA). Botón finalizar sesión. Documentos procesados por summariser → contexto fijo + RAG de sesión.

**Analysis:** Separar en Sprint 7c (flujo + prompts + encuesta) y Sprint 8 (persistencia + upload + finalización). El flujo se puede probar sin persistencia. Mobile upload es nativo del navegador, sin riesgo de perder sesión. Requiere actualizar SPEC-v2.md (nuevos modos, flujo reordenado).

---

### Gestión de documentos de evidencia en sesión
**Added:** 2026-03-11 | **Sprint:** 8g | **Effort:** M (1-2 días)

**Decisión:** Los documentos subidos no se pueden eliminar. Igual que en ChatGPT o Claude — lo que se sube se queda. Es lo más sencillo y arquitectónicamente sólido.

**Motivo:** El resumen del documento ya está inyectado en la conversación como contexto. Eliminar el original no elimina lo que el LLM ya "aprendió" de él. La conversación ya lo referencia.

**Impacto en recovery (8b):** Cuando se recupera una sesión con documentos, los resúmenes de evidencia están implícitamente cubiertos por el resumen de compresión. No hace falta re-inyectar documentos individualmente.

**Analysis:** Decisión simple. No requiere UI de gestión, solo upload. Documentos en `/app/data/sessions/{token}/evidence/`.

---

### Prompts de resumen y documentos internos por perfil
**Added:** 2026-03-11 | **Sprint:** 8c/8d | **Effort:** M (1-2 días)

**Resúmenes de cierre por perfil:** Los prompts de resumen de sesión (visibles al usuario al finalizar) deben ser únicos por perfil (worker, representative, organizer, officer). La información relevante y la forma de presentarla varía según el tipo de usuario. Requiere crear `session_summary_worker.md`, `session_summary_representative.md`, `session_summary_organizer.md`, `session_summary_officer.md` en lugar del genérico `session_summary.md`.

**Documentos internos al cerrar sesión:** Además del resumen visible al usuario, al cerrar sesión se generan dos documentos internos (no visibles al usuario, directo al disco):
1. **Resumen interno UNI** — resumen operativo para el equipo de UNI. Nuevo prompt y archivo (`{token}/internal_summary.md`).
2. **Informe estructurado interno** — ya planificado en 8d como `report.md` (prompt `internal_case_file.md`).

**Analysis:** Los resúmenes por perfil encajan en 8c (ampliar la lógica actual que usa un prompt genérico → resolver prompt por `role` como ya hace `prompt_assembler.py` con los case prompts). El resumen interno UNI es un documento adicional que encaja en 8d junto con el informe estructurado y el assessment. La mecánica es la misma: LLM inference con prompt dedicado → guardar en disco. Sprint 8d ya contempla report + assessment; añadir el resumen interno UNI es un prompt más en la misma cadena.

---

### Prompts: capacidades explícitas del modelo (can/cannot do)
**Added:** 2026-03-11 | **Sprint:** Prompt drafting phase | **Effort:** S (hours)

The LLM is offering to prepare PDFs for the user to download. It doesn't have this capability and should not offer it. When drafting the final prompts, include explicit instructions telling the model what it CAN and CANNOT do — specifically that it cannot generate files, PDFs, or downloadable documents. It should focus on providing information within the chat.

**Analysis:** Not a code change — goes into the prompt text itself. When writing the final per-profile prompts, add a "Capabilities & Limitations" section listing what the model can do (guide, document, advise, reference frameworks) and what it cannot (generate files, access external systems, send emails, create PDFs). Simple addition to each prompt file.

---

### Auto-archivado de sesiones por frontend con panel de configuración
**Added:** 2026-03-11 | **Sprint:** 8e o 8f | **Effort:** M (1 día)

**Descripción:** Panel de configuración en la parte superior del tab Sessions del admin. Un toggle por cada frontend registrado que activa/desactiva el archivado automático de sesiones, con un campo de horas de retención configurable por frontend. Permite asignar límites distintos para worker (ej: 48h) y organizer (ej: 120h), o desactivar el archivado durante la fase de diseño.

**Importante:** El "borrado" es solo lógico — la sesión deja de ser visible/accesible desde el backend (no aparece en admin, no se puede recuperar). Los archivos en el volumen de Docker (`/app/data/sessions/{token}/`) **nunca se eliminan automáticamente**. Solo se pueden borrar manualmente desde la máquina del backend. Esto garantiza que los datos de caso siempre existen para auditoría.

**Implementación:**
- Configuración persistida en `/app/data/session_retention.json` (por frontend_id)
- Campo `archived: true` + `archived_at` en session.json (soft delete)
- Background task en backend: escanea sesiones activas, archiva las que superan el límite
- Admin Sessions tab: las archivadas no aparecen por defecto (filtro opcional "Archived")
- Recovery: sesión archivada → error "Session expired"

**Analysis:** Encaja naturalmente en 8e (admin session enhancements) o 8f (inactivity timeout). La retención por frontend es útil operativamente. El soft-delete protege los datos. Se puede implementar junto con el timeout de inactividad ya que comparten la lógica de escaneo periódico.

---

