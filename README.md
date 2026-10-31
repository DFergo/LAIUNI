# HRDD Helper

A self-hosted AI assistant that helps workers, union representatives and organisers document labour-rights violations against international frameworks (ILO standards, OECD Guidelines, UN Guiding Principles, EU due-diligence rules).

It runs as two kinds of Docker containers:

- **Backend** — admin panel, language-model connections, knowledge base, sessions and all stored data.
- **Frontend** — the web page users see, one per campaign. The backend polls the frontends; a frontend never connects to the backend.

Language models can run on your own hardware (Ollama, LM Studio or any OpenAI-compatible server) or at a cloud provider.

## Install it with an AI agent

Open Claude Code (or another coding agent) in an empty folder and paste:

```
Read https://raw.githubusercontent.com/DFergo/LAIUNI/main/SETUP-AGENT.md and follow it to install HRDD Helper. Ask me before every step that changes something.
```

The agent downloads the app and connects its MCP server (`ops/hrdd_mcp.py`), which then guides the whole setup: a short survey of what you have and know, the recommended layout, Docker and Tailscale, a VPS, a domain and a Cloudflare Tunnel, AI models (cloud or local), email, frontends and an end-to-end test. Later, the same MCP helps you administer it ("add a frontend", "change the report model", "why is this site offline?"). It asks before every change and keeps passwords and keys out of the chat.

## Documentation

- **[Installation guide](docs/INSTALL.md)** — requirements, backend and frontend setup, the three deployment topologies, access modes, operation and troubleshooting.
- [Deployment examples](deploy/) — compose files for the backend, and for a frontend on the local network, on a VPS (with Tailscale or Cloudflare Access), or on the same machine as the backend.
- [Agent setup](SETUP-AGENT.md) and [MCP guides](ops/guides/) — what the AI agent follows.
- [Campaign deployment](docs/CAMPAIGN-DEPLOYMENT.md) — tailoring a frontend to a company or campaign: prompts, feature modules and campaign documents.
- [Changelog](docs/CHANGELOG.md)

## Images

- `ghcr.io/dfergo/laiuni-backend` (`arm64`)
- `ghcr.io/dfergo/laiuni-frontend` (`amd64`, `arm64`)

Tags: `latest` (the `main` branch) and `sha-<commit>`.

## License

See [LICENSE](LICENSE).
