# Message Flow — Pull-Inverse Architecture

## Overview

The frontend is a **passive server**. The backend **initiates all communication** by polling the frontend. The frontend never knows where the backend is. This enables deployment in restricted networks where outbound connections from the frontend are blocked.

## Sequence Diagram

```
┌──────┐     ┌──────────────┐     ┌──────────────┐     ┌─────┐
│ User │     │   Frontend   │     │   Backend    │     │ LLM │
│(React)│     │  (Sidecar)   │     │  (Polling)   │     │     │
└──┬───┘     └──────┬───────┘     └──────┬───────┘     └──┬──┘
   │                │                     │                │
   │ 1. Send msg    │                     │                │
   │───POST─────────>│                     │                │
   │  /internal/queue│                     │                │
   │                │  2. Enqueue          │                │
   │                │  (in-memory)         │                │
   │                │                     │                │
   │ 3. Open SSE    │                     │                │
   │───GET──────────>│                     │                │
   │ /internal/      │                     │                │
   │   stream/{token}│                     │                │
   │                │   (connection held open)              │
   │                │                     │                │
   │                │  4. Poll            │                │
   │                │<────GET─────────────│                │
   │                │  /internal/queue    │                │
   │                │                     │                │
   │                │  5. Return message  │                │
   │                │─────response───────>│                │
   │                │                     │                │
   │                │                     │ 6. Build prompt│
   │                │                     │  (system +     │
   │                │                     │   context +    │
   │                │                     │   RAG +        │
   │                │                     │   history)     │
   │                │                     │                │
   │                │                     │ 7. Inference   │
   │                │                     │───request─────>│
   │                │                     │                │
   │                │                     │ 8. Tokens      │
   │                │                     │<──stream───────│
   │                │                     │                │
   │                │  9. Push chunk      │                │
   │                │<────POST────────────│                │
   │                │  /internal/stream/  │                │
   │                │   {token}/chunk     │                │
   │                │                     │                │
   │ 10. SSE event  │                     │                │
   │<──event: token──│                     │                │
   │  data: "Hello"  │                     │                │
   │                │                     │                │
   │  (repeat 9-10 for each token)        │                │
   │                │                     │                │
   │ 11. Done       │                     │                │
   │<──event: done───│                     │                │
   │  data: "full text"                   │                │
   │                │                     │                │
```

## Component Responsibilities

### React App (User's browser)
- Submits messages via `POST /internal/queue`
- Opens EventSource for `GET /internal/stream/{session_token}`
- Renders tokens in real-time as they arrive
- Displays complete response on `done` event
- Handles errors (connection loss, timeout)

### Frontend Sidecar (FastAPI on port 8000, behind Nginx on port 80)
- **Inbound queue:** Receives user messages via POST, stores in-memory with TTL
- **Outbound queue:** Receives response chunks from backend via POST, delivers via SSE
- **Config endpoint:** Serves deployment config (frontend_type, auth settings)
- **Session recovery:** Stores/retrieves conversation history
- **Email auth:** Handles organizer verification flow
- **NO processing logic** — pure message relay

### Backend (FastAPI on port 8000)
- **Polling loop:** Background task that polls registered frontends every N seconds
- **Message processing:** Builds prompt (system + role + mode + context + RAG + history), sends to LLM
- **Token streaming:** Pushes response tokens back to frontend sidecar
- **Admin panel:** Serves admin React app and API
- **Registry:** Manages frontend registrations
- **Session store:** Persists conversation history
- **RAG:** Document indexing and retrieval

### Nginx (Frontend container only)
- Serves React SPA at `/`
- Proxies `/internal/*` to sidecar on port 8000
- Critical: SSE buffering disabled for streaming

## SSE Event Types

| Event | Data | Description |
|-------|------|-------------|
| `token` | `<token_text>` | Single token from LLM response |
| `done` | `<full_response>` | Complete response text |
| `error` | `<error_message>` | Processing error |

## Polling Details

- **Interval:** `poll_interval_seconds` (default: 2s)
- **Endpoint:** `GET {frontend_url}/internal/queue?max_count=10`
- **Auth:** None (frontend validates by checking if request comes to its sidecar)
- **Failure handling:** Log error, skip frontend, retry next interval
- **Health check:** Backend pings `/internal/config` to verify frontend is online

## Queue Behavior

- **TTL:** 300 seconds (5 minutes) — messages expire if not picked up
- **Delivery:** Messages are dequeued (removed) when the backend polls them
- **Thread safety:** asyncio locks for concurrent access
- **Persistence:** In-memory only (messages lost on container restart)
- **Response queue:** Separate queue for backend→frontend response chunks
