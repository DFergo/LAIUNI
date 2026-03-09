# HRDD Helper — Project Status

**Last Updated:** 2026-03-09

## Current State: v2 Rewrite — Sprint 0 (Setup)

Starting fresh rewrite based on SPEC-v2.md. Previous v1 codebase (Sprints 8-11f) had accumulated technical debt and a chat regression that couldn't be cleanly bisected.

### Sprint 0 — Project Setup
- [x] Product specification written (SPEC-v2.md)
- [x] Project structure created
- [x] Claude Code configuration ready
- [x] GitHub repo created (https://github.com/DFergo/LAIUNI)
- [ ] Initial project scaffolding (package.json, requirements.txt, Dockerfiles)
- [ ] Backend skeleton (FastAPI + admin auth)
- [ ] Frontend skeleton (React + Tailwind + Vite)
- [ ] Docker compose files
- [ ] Deployment configs

### What Works
- Nothing yet — clean slate

### What's Needed Next
1. **Sprint 1:** Project scaffolding — Dockerfiles, compose files, deployment configs, build pipeline
2. **Sprint 2:** Backend core — FastAPI app, admin auth (first-run setup + JWT), config loader
3. **Sprint 3:** Frontend core — React app with full user flow (language → disclaimer → session → survey → chat shell)
4. **Sprint 4:** Message queue + polling — the pull-inverse architecture
5. **Sprint 5:** LLM integration — LM Studio/Ollama provider, prompt assembly, streaming
6. **Sprint 6:** Admin panel — all 6 tabs (Frontends, Prompts, LLM, RAG, Sessions, SMTP)
7. **Sprint 7:** RAG + MemGPT/Letta integration
8. **Sprint 8:** Session management, recovery, finalization (summary + report)
9. **Sprint 9:** SMTP integration (auth codes, report forwarding, notifications)
10. **Sprint 10:** Polish, testing, production deployment

---

## Previous Version (v1) History

v1 was developed from Sprint 8 through Sprint 11f. The chat flow worked in Sprint 11a but regressed in later sprints. A bisection effort was underway but the codebase had accumulated enough technical debt to warrant a clean rewrite.

Key lessons from v1 are documented in `docs/knowledge/lessons-learned.md`.
