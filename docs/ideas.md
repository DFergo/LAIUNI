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

### Campañas paralelas: prompts y RAG por frontend
**Added:** 2026-03-12 | **Sprint:** 8h | **Effort:** L (sprint completo)

Permitir campañas simultáneas con configuración independiente por frontend. Dos modelos distintos:

**Prompts — modelo exclusivo:** Toggle en admin Prompts. O global (mismo set para todos) o específico (cada frontend con su propio set que REEMPLAZA al global). No se mezclan. Si un frontend tiene prompts propios, esos se usan; si no, los globales.

**RAG — modelo aditivo con suscripción:** El panel de RAG global se mantiene. Un toggle "RAG por frontend" añade un subpanel por cada frontend registrado. Cada subpanel tiene: (1) toggle "incluir RAG global" (on por defecto), (2) gestión de documentos específicos de ese frontend. El sistema filtra por `frontend_id` de la sesión y aplica la unión de todas las fuentes a las que el frontend está suscrito (global si está activo + docs propios).

**Patrón reutilizado:** Misma lógica que lifecycle (Sprint 8f) — selector de frontend, toggle, config por `frontend_id`. El `frontend_id` ya está en `session.json` desde 8f. `prompt_assembler.py` recibe `frontend_id` → busca set específico, fallback a global. `rag_service.py` recibe `frontend_id` → junta chunks de fuentes suscritas.

**Analysis:** Encaja en Sprint 8h (ya planificado como Campaign-Specific RAG). Ampliar alcance para incluir prompts. Infraestructura de `frontend_id` ya validada. La parte de RAG es algo más compleja por el modelo de suscripción (índices separados por fuente, merge de chunks en query time), pero LlamaIndex soporta múltiples índices nativamente.

---

### Subida de documentos en batch (multi-upload)
**Added:** 2026-03-12 | **Sprint:** 8g-b (subsprint) | **Effort:** M (1-2 días)

Subir documentos uno a uno y esperar la respuesta del modelo es tedioso si hay varios. Permitir subir hasta 4 documentos a la vez. El sistema los procesa secuencialmente (extracción + resumen), y al terminar todos genera una sola respuesta automática comentando lo que ha recibido. Usar el LLM del compressor (summariser) en lugar del principal para los resúmenes individuales — ya se hace. La respuesta final podría usar también el summariser para ser más rápida, o el principal si se prefiere calidad.

**Analysis:** Factible. El sidecar ya acepta uploads individuales — ampliar a `<input multiple>` en frontend con límite de 4. Backend procesa cada archivo secuencialmente en `_handle_upload`, acumula resultados, y lanza una sola inferencia al final del batch. El summariser ya se usa para resúmenes individuales (más rápido). Requiere: (1) frontend `multiple` + cola de uploads, (2) sidecar batch endpoint o múltiples POSTs, (3) backend batch handler que agrupa uploads del mismo token antes de responder.

---

### Análisis de imágenes subidas como evidencia (modelo multimodal)
**Added:** 2026-03-12 | **Sprint:** Backlog | **Effort:** M (1-2 días)

Actualmente las imágenes (.jpg, .png) subidas como evidencia se almacenan en el dossier pero no se analizan. Usar un modelo multimodal (Qwen3.5-9b-mlx ya disponible en LM Studio) para describir/resumir imágenes al subirlas. El resumen se inyectaría como contexto igual que los documentos de texto, aunque las imágenes no irían al RAG de sesión.

**Implementación:** `evidence_processor.py` necesita enviar la imagen como base64 al modelo vía formato OpenAI multimodal (`image_url` en content array). `llm_provider.py` necesita soportar mensajes multimodales. Se podría usar el mismo modelo del summariser o uno dedicado configurable en admin LLM tab. El resumen de imagen se guardaría en `{filename}.summary.md` igual que los textos.

**Analysis:** Factible — el modelo ya está disponible en el hardware actual. Requiere: (1) soporte multimodal en `llm_provider.py` (~30 líneas), (2) ruta de imagen en `evidence_processor.py` (~20 líneas), (3) configuración de modelo multimodal en admin. No prioritario pero útil para fotos de documentos, capturas de condiciones laborales, etc.

---

### Compresión de contexto progresiva (anti-slowdown)
**Added:** 2026-03-12 | **Sprint:** Backlog (Sprint 12 si se integra con Letta) | **Effort:** M (1-2 días)

A medida que se acumulan mensajes y documentos, la ventana de contexto crece y cada inferencia es más lenta. Actualmente la compresión se dispara al llegar al threshold (75% de la ventana) — pero para entonces ya hay mucho contexto y la respuesta tarda.

**Opción A — Compresión escalonada:** Comprimir al llegar a 20k tokens, luego a 30k, 40k... con saltos de 15-20k. La conversación eventualmente podría llegar a los 200k del modelo, pero sería fluida entre compresiones. Cada compresión reduce los mensajes antiguos a un resumen ejecutivo. Riesgo: pérdida de detalle en conversaciones muy largas. La calidad depende del prompt de compresión y del modelo summariser.

**Opción B — Techo fijo:** No permitir que el contexto supere un límite (ej. 30k tokens). Comprimir agresivamente siempre que se acerque. Más predecible en latencia pero más pérdida de información.

**Opción C — Letta/MemGPT (Sprint 12):** Letta gestiona contexto, compresión, documentos y RAG de sesión de forma unificada. En lugar de tener sistemas separados (context_compressor + evidence_processor + session RAG + global RAG), Letta mantiene una "memoria" estructurada del agente que incluye hechos clave, documentos y contexto relevante. El modelo siempre trabaja con una ventana manejable. Es la solución más elegante pero requiere integración completa.

**Pregunta clave:** ¿Merece la pena iterar sobre la compresión manual (A/B) o esperar a Letta (C)? A/B son incrementales y rápidas de implementar. C es un cambio de paradigma que resuelve el problema de raíz pero es un sprint completo.

**Analysis:** A corto plazo, la opción A es la más pragmática — cambiar `compress_if_needed` para usar thresholds escalonados en vez de un solo umbral. A largo plazo, Letta (Sprint 12) unificaría todo. Las opciones no son excluyentes: A mejora el sistema actual, C lo reemplaza eventualmente.

---

### Respuestas simples para el usuario, información completa para el informe
**Added:** 2026-03-12 | **Sprint:** Fase de redacción de prompts + Sprint 10 (guardrails) | **Effort:** M (1-2 días)

El modelo da respuestas demasiado complejas, especialmente cuando acumula mucha información (documentos, RAG, contexto largo). En modo documentación, el objetivo es **extraer** información del trabajador, no apabullarle con análisis de marcos legales que no le son útiles. El modelo debe identificar patrones y relaciones con marcos globales internamente, pero al usuario darle solo una explicación sencilla y seguir extrayendo datos.

**Dos capas del problema:**

1. **Prompts conversacionales (perfil worker/rep):** Instruir al modelo para que sea breve, empático, haga preguntas cortas y guarde el análisis profundo para sí mismo. No citar artículos específicos de convenios salvo que el usuario pregunte. Esto es puro trabajo de prompt — no requiere código.

2. **Informe final vs. compresión:** Si la conversación no se comprime, el prompt de informe recibe la conversación completa → tiene toda la información. Si se comprime, ¿el resumen de compresión preserva las relaciones con marcos globales que el modelo identificó internamente? Opciones:
   - **A) Conversación completa al informe siempre** — leer de `conversation.jsonl` en disco, no del contexto comprimido. El informe siempre tiene todo. Coste: más tokens en la generación del informe, pero es un solo call.
   - **B) Compresión consciente** — ajustar el prompt de compresión para que preserve explícitamente las relaciones con marcos identificadas. Riesgo: si el modelo no las verbalizó en el chat (porque le dijimos que fuera simple), la compresión no las tiene.
   - **C) Notas internas del modelo** — un campo "internal_notes" donde el modelo anote relaciones con marcos que no muestra al usuario. Parecido a lo que haría Letta.

**Analysis:** La opción A es la más segura y simple — el informe siempre usa `conversation.jsonl` completo desde disco, ignorando la compresión. El coste extra de tokens es asumible (un solo call no-streaming). Los prompts conversacionales son trabajo de contenido, no de código. Encaja en la fase de redacción de prompts (Daniel escribirá el contenido final) y Sprint 10 (guardrails que regulan el tono). La opción C es esencialmente lo que Letta haría en Sprint 12.

---

### Fase de test de calidad post-prompts (análisis de respuestas)
**Added:** 2026-03-12 | **Sprint:** Post-diseño de prompts (antes de Sprint 11) | **Effort:** M (1-2 días)

Después de definir los prompts finales por perfil/caso, dedicar una fase de testing profundo donde se analizan las respuestas del sistema en escenarios reales. No es testing funcional (eso se hace en cada sprint) — es testing de calidad de las respuestas del LLM con los prompts definitivos.

**Qué probar:**
- Calidad y tono de las respuestas por perfil (worker vs organizer vs officer)
- RAG por campaña: ¿el modelo usa correctamente los docs de campaña?
- Compresión: ¿la conversación mantiene coherencia tras compresiones?
- Documentos de cierre: ¿los informes y resúmenes internos capturan toda la información relevante?
- Respuestas simples para workers: ¿el modelo extrae info sin apabullar?
- Guardrails: ¿los prompts previenen respuestas inadecuadas sin necesidad del filtro hardcoded?

**Prerequisito:** Prompts finales escritos por Daniel. Requiere sesiones reales o simuladas con varios perfiles y escenarios.

**Analysis:** Encaja como fase intermedia entre el diseño de prompts y Sprint 11 (polish). No es un sprint de código — es un sprint de contenido y evaluación. Los hallazgos pueden resultar en ajustes a prompts, parámetros del modelo, o threshold de compresión. Debería hacerse con el modelo final que se usará en producción.

---

### Monitorización externa con alertas Telegram
**Added:** 2026-03-12 | **Sprint:** Backlog (post-Sprint 11) | **Effort:** S (horas)

Script bash en el Mac host (fuera de Docker) que chequea periódicamente la salud del sistema y envía alertas via Telegram Bot API si algo falla. Ejecutado por launchd cada 5-10 minutos.

**Checks posibles:**
- Backend health (`/health` endpoint)
- SMTP conectividad (si está configurado)
- LLM providers (LM Studio / Ollama online)
- Espacio en disco del volumen Docker
- Containers running (docker ps)

**Stack:** bash + curl + launchd plist en `~/Library/LaunchAgents/`. Telegram Bot API para notificaciones (funciona desde el móvil, no requiere sesión activa en el Mac). Alternativa: iMessage via osascript (requiere sesión).

**Requisitos:** Crear Telegram bot (@BotFather), obtener chat_id, guardar token como variable de entorno.

**Analysis:** No es un sprint de código del proyecto — es infraestructura del host. Implementable en una hora. Útil para producción headless. No tiene dependencias con ningún sprint. Se puede hacer en cualquier momento después de tener el backend en producción.

---

### Summariser dedicado para resúmenes de evidencia
**Added:** 2026-03-12 | **Sprint:** Backlog | **Effort:** S (horas)

Los resúmenes de documentos subidos usan el summariser (mismo modelo que la compresión de contexto). Para documentos largos puede ser lento. Permitir configurar un modelo específico para resúmenes de evidencia en el admin LLM tab — por ejemplo, Qwen3.5-9b-mlx que es más rápido que modelos más grandes. Actualmente el summariser se comparte con la compresión de contexto.

**Analysis:** Cambio menor. Añadir `evidence_summariser_model` y `evidence_summariser_provider` a LLM settings. `evidence_processor.py` ya lee settings para elegir provider/model — solo cambiar las keys que consulta. UI: un selector más en admin LLM tab.

---

### Sprint de traducción de textos del frontend
**Added:** 2026-03-12 | **Sprint:** Post-diseño de prompts (después de fase de test de calidad) | **Effort:** M (1-2 días)

**Descripción:** Dedicar un sprint completo a revisar y completar la traducción de TODOS los textos fijos que ve el usuario final en el frontend. Actualmente muchos idiomas usan fallback a inglés. Los prompts y el admin se mantienen solo en inglés — este sprint es exclusivamente para textos del frontend (i18n.ts): UI labels, mensajes de error, disclaimer, instrucciones, respuestas fijas de guardrails, etc.

**Incluye:**
- Revisar i18n.ts: completar traducciones reales para los 31 idiomas (actualmente muchos son English fallback)
- Respuestas fijas de guardrails en los 31 idiomas
- Mensajes de auth, upload, errores — todo lo que el usuario final ve
- NO incluye: prompts del LLM (solo inglés), admin panel (solo inglés)

**Recurrencia:** Después de este sprint inicial, cada sprint de mejora que afecte a texto visible por el usuario final debe incluir una tarea de traducción de los nuevos textos.

**Analysis:** Encaja como sprint de contenido después de la fase de test de calidad de prompts y antes de producción final. No requiere cambios de código — solo contenido en i18n.ts y las respuestas hardcoded de guardrails. Se puede hacer con herramientas de traducción o nativos.

---

### Navegación: botón Back + aviso de no recargar
**Added:** 2026-03-12 | **Sprint:** Sprint 11 (Polish) o dedicado | **Effort:** M (1-2 días)

**Problema:** La app es una SPA con estado en memoria. Si el usuario recarga la página, vuelve a la selección de idioma y pierde todo el progreso. Si pulsa el botón "atrás" del navegador, sale de la app.

**Solución propuesta — dos partes:**

1. **Botón Back en todas las páginas pre-chat:** Disclaimer, Session, Role Select, Auth, Instructions y Survey deben tener un botón para volver al paso anterior. Actualmente el usuario no tiene forma de corregir un error sin recargar (y perder todo).

2. **Aviso de no recargar en Instructions page:** Antes de llegar al survey/chat, la página de instrucciones debe avisar claramente que recargar la página perderá el progreso. Algo como "No recargues la página durante la sesión — perderás la conversación."

3. **`beforeunload` handler (opcional):** `window.addEventListener("beforeunload", ...)` para mostrar confirmación del navegador al recargar/cerrar durante una sesión activa. No funciona en todos los navegadores móviles pero es una capa extra.

4. **`history.pushState` (opcional):** Meter cada fase como entrada en el historial del navegador para que "atrás" vaya al paso anterior en vez de salir de la app. Requiere algo de lógica pero es factible sin React Router.

**Analysis:** Las partes 1 y 2 son imprescindibles y sencillas (botones + texto i18n). Las partes 3 y 4 son mejoras opcionales que añaden robustez. Encaja en Sprint 11 (polish) o como tarea en cualquier sprint de mejora UX. No tiene dependencias técnicas.

---

### Múltiples destinatarios de notificaciones + asignación por frontend
**Added:** 2026-03-12 | **Sprint:** Backlog (post-Sprint 11) | **Effort:** M (1-2 días)

Poder añadir más direcciones de correo electrónico para notificaciones al admin o para notificaciones de nuevo report. Idealmente, poder asignar direcciones específicas por frontend en caso de que se use para campañas distintas gestionadas por distintas personas.

**Implementación:**
- **Nivel global:** Cambiar el campo `from_address` / admin email de un solo string a una lista de emails en `smtp_config.json`. Todas las notificaciones (flagged, new report) se envían a todos los emails de la lista. UI: campo multi-email en SMTP tab (chips/tags).
- **Nivel por frontend:** Añadir `notification_emails: string[]` a la config de campaña (`/app/data/campaigns/{frontend_id}/notification_config.json`). Si existe, las notificaciones de sesiones de ese frontend van a esos emails en vez de (o además de) los globales. UI: sección de notificaciones en el subpanel de cada frontend en SMTP tab o en Frontends tab.
- `smtp_service.py`: `notify_admin_report()` y similares reciben `frontend_id`, resuelven lista de destinatarios (frontend-specific + global fallback), envían a todos.

**Analysis:** Encaja perfectamente con la arquitectura de campañas por frontend (Sprint 8h). La infraestructura de `frontend_id` ya está en sesiones y en el sistema de campañas. Técnicamente sencillo — el cambio es principalmente en `smtp_service.py` (resolver destinatarios) y en admin UI (gestión de listas de emails). No tiene dependencias bloqueantes, pero es más útil después de tener campañas en uso real.

---

### Copyright y autoría en el código
**Added:** 2026-03-12 | **Sprint:** Sprint 11 (pre-producción) | **Effort:** S (horas)

Hay que poner autoría y copyright en el código. El diseño es de Daniel Fernandez, Head of UNI Graphical & Packaging, y la propiedad intelectual pertenece a Union Network International (UNI Global Union) con sede en Nyon, Suiza. No se permite la copia o reproducción sin autorización previa y se prohíbe expresamente el uso para fines comerciales.

**Implementación:**
- Archivo `LICENSE` en la raíz del repo con licencia propietaria/restrictiva (no open source)
- Header de copyright en archivos clave (main.py backend, App.tsx frontend, sidecar main.py)
- Footer visible en el frontend: "© UNI Global Union" (ya hay footer, añadir copyright)
- Actualizar `package.json` y `pyproject.toml`/metadata con autor y licencia
- Nota en README/INSTALL si existe

**Texto propuesto:**
```
© 2026 Union Network International (UNI Global Union), Nyon, Switzerland.
Designed by Daniel Fernandez, Head of UNI Graphical & Packaging.
All rights reserved. No copying, reproduction or commercial use permitted
without prior written authorization from UNI Global Union.
```

**Analysis:** Imprescindible antes de producción. Es trabajo de contenido, no de código — añadir headers y un archivo LICENSE. Encaja en Sprint 11 (polish/pre-producción). Sin dependencias técnicas. Nota: el repo de GitHub es público — hay que considerar si se cambia a privado o si la licencia restrictiva en un repo público es suficiente.

---

### Branding personalizable por frontend + logo UNI
**Added:** 2026-03-12 | **Sprint:** Backlog (sprint de campañas avanzado) | **Effort:** L (sprint completo)

**Dos partes:**

**1. Personalización de UI por frontend (admin):**
El disclaimer inicial, la página de instrucciones e incluso el branding podrían ser personalizables en un nuevo menú de admin para cada frontend. Esto complementa la lógica existente de campañas (prompts por frontend en 8h, RAG por frontend, notificaciones por frontend) para poder desplegar la herramienta en campañas para las que no fue inicialmente concebida. Un nuevo tab o sección en admin permitiría configurar por frontend:
- Texto del disclaimer
- Texto de instrucciones por perfil
- Nombre/título de la app mostrado al usuario
- Colores primarios (override de UNI blue)
- Logo custom (upload de imagen)

**2. Logo UNI y branding mejorado:**
Revisar el branding actual (que está bastante bien) y añadir el logo de UNI en:
- **Fondo del chat:** Logo en tonos muy apagados, casi transparente, fijo detrás de las burbujas de texto (watermark). Efecto visual elegante sin interferir con la lectura.
- **Encabezado:** Logo pequeño junto al título "HRDD Helper"
- **Página de inicio / selección de idioma:** Logo prominente
- **Disclaimer:** Logo como refuerzo institucional

**Relación con campañas:** Si un frontend tiene branding custom (parte 1), se usa ese. Si no, se usa el branding UNI por defecto (parte 2). Esto permite que UNI despliegue frontends con branding propio para campañas específicas (ej: una campaña sectorial con otro logo/colores) mientras el deployment principal mantiene el branding UNI.

**Analysis:** Son dos ideas relacionadas pero con esfuerzos distintos. La parte 2 (logo UNI) es sencilla — S effort, encaja en Sprint 11 (polish). La parte 1 (personalización por frontend) es un sprint completo: requiere nuevo modelo de datos por frontend, endpoints admin, UI de configuración, y lógica en el frontend React para aplicar config dinámica recibida del sidecar. La infraestructura de campañas (8h) ya tiene la base (`/app/data/campaigns/{frontend_id}/`), pero la config de UI es un concepto nuevo. Backlog hasta que haya demanda real de campañas multi-marca.

---

### Limpiar archivos de Claude Code del repo público (GitHub)
**Added:** 2026-03-12 | **Sprint:** Sprint 11 (pre-producción) | **Effort:** S (horas)

Quitar los archivos de Claude Code del repositorio de GitHub y quedarnos solo con los archivos del HRDD Helper. Eliminar: `CLAUDE.md`, `.claude/` (settings, commands/skills), memoria del proyecto. Preservar todo en Gitea (repo privado/interno) donde sí es útil tener la configuración de desarrollo.

**Implementación:**
- Opción A — `.gitignore` selectivo: No es posible tener `.gitignore` diferente por remote con git estándar.
- Opción B — Branch separado para GitHub: Mantener un branch `public` sin los archivos de Claude Code, push solo ese branch a GitHub. `main` con todo va a Gitea. Requiere merge discipline.
- Opción C — Script de push a GitHub: Un script que hace `git stash` de los archivos de Claude, pushea a GitHub, y los restaura. Frágil.
- Opción D — GitHub Actions / pre-push hook: Filtrar archivos en el push. Más complejo de lo necesario.
- **Opción E (recomendada):** Simplemente eliminar los archivos de Claude del repo y moverlos fuera del directorio del proyecto. Claude Code puede usar `~/.claude/` para settings globales y el `CLAUDE.md` se puede mantener como archivo local no trackeado (añadir a `.gitignore`). En Gitea se puede mantener un branch o tag con la snapshot actual que incluye todo.

**Analysis:** La opción más limpia es la E: `.gitignore` para `CLAUDE.md` y `.claude/`, un commit que los elimina, push a ambos remotes. Antes de eso, hacer un tag/snapshot en Gitea con la versión que incluye todo. Encaja en Sprint 11 junto con el copyright y la limpieza pre-producción.

---

### Frontworker no expone selección de modo — traducciones de modos solo para frontorganizer
**Added:** 2026-03-13 | **Sprint:** 12 | **Effort:** S (horas)

El branding custom (disclaimer, instrucciones, título, logo) solo se aplica al frontworker. El frontorganizer NO es personalizable — usa siempre los textos fijos de i18n.ts. Los textos de selección de modo (Document Violation, Interview, Advisory, etc.) solo existen en el frontorganizer y van como traducciones estáticas en i18n.ts, no por el sistema de branding/traducción LLM. El frontworker no expone selección de modo (worker/representative no tienen modos).

**Analysis:** Ya es así en el código. Las traducciones de modo van en i18n.ts junto con el resto de textos fijos del frontorganizer. No requiere cambio de código, solo tenerlo en cuenta al organizar el sprint de traducción.

---

### Placeholder [DATA_PROTECTION_EMAIL] configurable
**Added:** 2026-03-13 | **Sprint:** 12 | **Effort:** S (horas)

El placeholder `[DATA_PROTECTION_EMAIL]` en el disclaimer debe ser configurable en `deployment_backend.json` e inyectado al frontend en build time o vía el endpoint `/internal/config`. Lo mismo para cualquier dato de contacto legal futuro.

**Implementación:** Añadir `data_protection_email` a `deployment_backend.json`. El sidecar lo recibe vía el endpoint `/internal/config` (el backend lo pushea o el sidecar lo expone desde su propia config). El frontend sustituye `[DATA_PROTECTION_EMAIL]` en el texto del disclaimer por el valor real. Para branding custom (frontworker), el email también se inyecta en el texto traducido por el LLM.

**Analysis:** Encaja en Sprint 12. Config global en deployment_backend.json. Técnicamente trivial: un campo más en config, un string replace en el frontend antes de renderizar el disclaimer. Aprobado por Daniel como placeholder dinámico.

---

### Descripciones de modo como helper text dinámico en el survey
**Added:** 2026-03-13 | **Sprint:** 12 | **Effort:** S (horas)

Las descripciones cortas de cada modo de consulta (Document Violation, Interview, Advisory, Submit Materials, Training) deben renderizarse como texto de ayuda directamente debajo del selector de modo en el formulario de survey. Aparecen dinámicamente cuando se selecciona un modo o en hover/focus. No mostrar todas las descripciones a la vez — mantener la UI limpia.

**Analysis:** Ya existe un selector de modo en SurveyPage.tsx para organizer/officer. Añadir un `<p>` condicional debajo del selector con la descripción del modo seleccionado. Los textos van en i18n.ts. Trivial en código, el esfuerzo está en traducir los textos.

---

### En Interview mode, clarificar que el asistente ayuda al organizador
**Added:** 2026-03-13 | **Sprint:** 12 (prompts + UX) | **Effort:** S (horas)

En modo Interview, el organizador puede estar usando la herramienta sentado con el trabajador. La UI debe dejar claro que el asistente ayuda al organizador, no habla directamente al trabajador. Esto afecta tanto a las instrucciones como al prompt del LLM.

**Analysis:** Dos capas: (1) texto de instrucciones para Interview mode — ya cubierto en el documento de textos hardcoded. (2) Prompt del LLM para Interview — dejar explícito que se dirige al organizador, no al trabajador. Ambas son trabajo de contenido, no de código.

---

### LLM por frontend: asignar modelo de inferencia distinto por frontend ✅ DONE
**Added:** 2026-03-15 | **Completed:** 2026-03-15 | **Effort:** M

Poder asignar un LLM distinto (provider + modelo) para inferencia a cada frontend registrado. Esto permite tener dos modelos distintos respondiendo a dos frontends distintos simultáneamente — por ejemplo, un modelo grande (Qwen 32B) para el frontorganizer y uno más rápido (Mistral 7B) para el frontworker.

**Implementación:**
- `get_llm_settings(frontend_id)` busca primero en `/app/data/campaigns/{frontend_id}/llm_settings.json`, fallback a global
- Modificar ~5 call sites en `polling.py` para pasar `frontend_id` a `get_llm_settings()`
- Nuevos endpoints admin: `GET/PUT /admin/frontends/{frontend_id}/llm-settings`
- UI en admin Frontends tab: selector de provider/model por frontend (o "usar global")
- Backward compatible: si no hay config por frontend, usa la global

**Analysis:** Técnicamente sencillo. `frontend_id` ya se pasa por todo el pipeline de procesamiento. El patrón de config por frontend ya existe para prompts, RAG, branding y notificaciones (`/app/data/campaigns/{frontend_id}/`). Solo hay que extenderlo a LLM settings. No rompe nada existente.

---

### Training mode solo para officers (ya implementado)
**Added:** 2026-03-13 | **Sprint:** N/A (ya hecho) | **Effort:** N/A

El modo Training solo debe estar disponible para officers. Si el rol es "organizer", esta opción no debe aparecer en el selector de modo.

**Analysis:** Ya implementado en SurveyPage.tsx — `MODES_BY_ROLE.organizer` no incluye 'training', solo `MODES_BY_ROLE.officer` lo tiene. No requiere cambio.
