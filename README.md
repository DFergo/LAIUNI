# HRDD Helper

A self-hosted AI assistant that helps workers, union representatives and organisers document labour-rights violations against international frameworks (ILO standards, OECD Guidelines, UN Guiding Principles, EU due-diligence rules).

It runs as two kinds of Docker containers:

- **Backend** — admin panel, language-model connections, knowledge base, sessions and all stored data.
- **Frontend** — the web page users see, one per campaign. The backend polls the frontends; a frontend never connects to the backend.

Language models can run on your own hardware (Ollama, LM Studio or any OpenAI-compatible server) or at a cloud provider.

## Documentation

- **[Installation guide](docs/INSTALL.md)** — requirements, backend and frontend setup, the three deployment topologies, access modes, operation and troubleshooting.
- [Deployment examples](deploy/) — compose files for a frontend on the local network, on a remote server, or on the same machine as the backend.
- [Campaign deployment](docs/CAMPAIGN-DEPLOYMENT.md) — tailoring a frontend to a company or campaign: prompts, feature modules and campaign documents.
- [Changelog](docs/CHANGELOG.md)

## Images

- `ghcr.io/dfergo/laiuni-backend` (`arm64`)
- `ghcr.io/dfergo/laiuni-frontend` (`amd64`, `arm64`)

Tags: `latest` (the `main` branch) and `sha-<commit>`.

## License

See [LICENSE](LICENSE).
