# Lessons Learned from HRDD Helper v1

Critical bugs, pitfalls, and design decisions from the v1 codebase. **Read this before implementing polling, SSE, registry, or Docker code.**

---

## 1. SSE Streaming — EventSource Error Handling

**Bug:** EventSource `onerror` handler didn't unblock the UI. When SSE connection failed, `isStreaming` stayed `true` forever, freezing the chat.

**Fix:** Track connection failures in onerror. After 3 consecutive failures, call `callbacks.onError()` to unblock the UI:

```typescript
let connectionFailures = 0;
eventSource.onerror = () => {
  connectionFailures++;
  if (connectionFailures >= 3) {
    eventSource.close();
    callbacks.onError("Connection lost. Please try again.");
  }
};
eventSource.onmessage = () => {
  connectionFailures = 0; // Reset on successful message
};
```

---

## 2. Background Task Error Handling

**Bug:** `_dev_auto_process` used `asyncio.create_task()` with no error handling. If `process_message()` threw an exception, the task died silently — no error message, no UI update, nothing.

**Fix:** Always wrap background tasks in try-except and push error to the response stream:

```python
async def _safe_process(message):
    try:
        await process_message(message)
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        await backend_queue.push_error(message.session_token, str(e))
```

---

## 3. Health Check Can Crash Processing

**Bug:** `check_health()` in the polling service wasn't wrapped in try-except. If the LLM provider was down, the exception killed the entire processing pipeline — not just that message.

**Fix:** Wrap health checks in try-except with graceful fallback:

```python
try:
    health = await llm_provider.check_health()
except Exception:
    health = {"status": "unknown", "error": "health check failed"}
```

---

## 4. Nginx Must Disable Buffering for SSE

**Bug:** Nginx default configuration buffers responses. SSE tokens were batched instead of streaming in real-time.

**Fix:** These headers are MANDATORY for the `/internal/` location:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_set_header Connection '';
proxy_http_version 1.1;
chunked_transfer_encoding off;
proxy_read_timeout 600s;
```

---

## 5. Frontend Registry Persistence

**Bug:** Frontend registrations disappeared and reappeared randomly. The registry was not being persisted atomically.

**Fix:**
- Save to JSON file after EVERY mutation (register, update, delete)
- Use atomic write (write to temp file, then rename)
- Load from file on startup
- Never rely on in-memory state surviving restarts

```python
def _save(self):
    tmp = self._path.with_suffix('.tmp')
    tmp.write_text(json.dumps(self._data, indent=2))
    tmp.rename(self._path)
```

---

## 6. Docker Volume for Persistence

**Bug:** Data stored in container filesystem was lost on rebuild/redeploy.

**Fix:** ALL persistent data must live in `/app/data` which is a named Docker volume:
- Admin password hash (`.admin_hash`)
- JWT secret (`.jwt_secret`)
- Frontend registry (`frontends.json`)
- Sessions directory
- RAG index
- Prompt files

---

## 7. Backend Serves React = Confusion

**Bug:** Both backend and frontend Dockerfiles built the same React app. Opening the backend URL showed the user flow instead of admin. Extremely confusing.

**Fix in v2:** Backend serves ONLY the admin React app at root `/`. No user flow on backend. The admin app is a separate build or the same app with routing that shows only admin when on backend.

---

## 8. frontend_id Shared Secret = Fragile

**Bug:** The `frontend_id` was a manually configured shared secret that had to match between `deployment_frontend_worker.json` and `deployment_backend.json`. Misconfiguration caused silent polling failures with unhelpful error messages.

**Fix in v2:** Remove `frontend_id` entirely. Backend discovers frontends by URL via `GET /internal/config`. Registration uses auto-generated short IDs. No shared secrets needed.

---

## 9. DEV_MODE Processing Path

**Important:** `HRDD_DEV_MODE=true` enables `_dev_auto_process` which bypasses HTTP polling and processes messages locally. This is useful for testing but masks networking issues.

**Rule:** Always test with DEV_MODE off before declaring something "working." Many bugs only appear in production polling mode.

---

## 10. Same-Machine Testing Gotcha

When running both containers on the same machine, they MUST communicate via host IP (e.g., `http://10.210.66.103:8091`), NOT via `localhost` or Docker internal networking. Otherwise, moving the frontend to a separate machine will break everything.

---

## 11. Message Queue TTL

Messages in the queue have a 300-second (5 minute) TTL. If the backend polling is slow or the LLM takes too long, messages expire silently. Monitor this.

---

## 12. Git Configuration — NEVER TOUCH

**Disaster in v1:** An AI assistant modified git remote URLs, breaking SSH push to both GitHub and Gitea. Took significant effort to recover.

**ABSOLUTE RULE:** Never execute `git config`, `git remote add/set-url`, or any git configuration commands. Only provide commands for the user to copy and execute manually.
