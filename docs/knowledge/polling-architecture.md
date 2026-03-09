# Pull-Inverse Architecture — Deep Dive

## Why Pull-Inverse?

Traditional web apps have clients (frontends) that call servers (backends). In HRDD Helper, this is reversed:

- **Frontend = passive server** — holds user messages, waits to be polled
- **Backend = active client** — initiates all connections, pulls messages from frontends

This is called "pull-inverse" or "air-gap" architecture.

## Why Not Standard Client-Server?

1. **Network restrictions:** Union offices may block outbound connections. The frontend can sit behind a firewall that allows inbound only.
2. **Privacy:** The frontend doesn't need to know the backend's location. If the frontend is compromised, the attacker can't reach the backend.
3. **Flexibility:** One backend can poll many frontends across different locations. Frontends can be added/removed without backend reconfiguration (just register URL).

## How It Works

### Frontend Sidecar

The frontend container runs two processes:
- **Nginx** (port 80) — serves React SPA, proxies `/internal/*`
- **FastAPI sidecar** (port 8000) — message queue and config

The sidecar exposes:
```
POST /internal/queue          ← React app submits user messages here
GET  /internal/queue          ← Backend polls here to pick up messages
POST /internal/stream/{t}/chunk ← Backend pushes response tokens here
GET  /internal/stream/{t}    ← React app receives SSE stream here
GET  /internal/config         ← Returns frontend type and settings
```

### Backend Polling Loop

```python
async def _polling_loop():
    while True:
        for frontend in registry.list_enabled():
            try:
                messages = await poll_frontend(frontend.url)
                for msg in messages:
                    await process_and_push(msg, frontend.url)
            except Exception as e:
                logger.error(f"Poll failed for {frontend.url}: {e}")
        await asyncio.sleep(poll_interval)
```

### Message Lifecycle

```
1. User types message → stored in frontend sidecar queue
2. Backend polls → message dequeued (removed from frontend)
3. Backend processes with LLM → generates response tokens
4. Backend pushes tokens back to frontend sidecar
5. Frontend sidecar delivers tokens via SSE to React app
6. React renders tokens in real-time
```

## Key Design Constraints

### Stateless Polling
Each poll is stateless. The backend asks "do you have any messages?" and the frontend returns whatever is in the queue. No session affinity needed at the polling level.

### Message TTL
Messages expire after 300 seconds. If the backend doesn't poll within 5 minutes, messages are lost. This prevents stale messages from accumulating.

### Atomic Delivery
When the backend polls, messages are removed from the queue. There's no acknowledgment mechanism. If the backend crashes after polling but before processing, the message is lost. This is acceptable for the current use case (user can resend).

### Response Push
The backend pushes response tokens to the frontend sidecar, which stores them in a separate response queue. The React app's EventSource connection reads from this queue. The response is complete when the backend sends a `done` event.

## Dev Mode Shortcut

When `HRDD_DEV_MODE=true`, the backend skips HTTP polling and processes messages from its own local queue. This is useful for testing the LLM integration without a frontend container.

```python
if DEV_MODE:
    # Message goes directly to local queue → process locally
    # No HTTP polling needed
    asyncio.create_task(_dev_auto_process(message))
```

**WARNING:** Dev mode masks networking issues. Always test with dev mode OFF before declaring something working.

## Scaling Considerations

Current design: one backend polls all frontends sequentially. For future scaling:
- **Multiple frontends:** Already supported — backend iterates through registered frontends
- **Multiple backends:** NOT supported — would require coordination to avoid duplicate processing
- **Load balancing:** Not needed — each frontend serves a small number of concurrent users
