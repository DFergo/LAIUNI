# HRDD Helper — setup instructions for AI agents

You are an AI coding agent (Claude Code, Codex, Cursor or similar). A user asked you to install HRDD Helper, a self-hosted assistant that helps unions document labour-rights violations. The user may not be technical. These steps only download the app and connect its own MCP server; the MCP server then provides the guided setup (survey, recommendations, installation, configuration, tests).

Rules for the whole process:
- Speak the user's language. Explain each step in a sentence or two before doing it.
- **Ask before every command that installs, downloads or changes something**, and wait for a yes.
- Never ask the user to paste passwords, API keys or tokens into the chat; the MCP has safer ways.
- Only run installers from the official sources named here or in the MCP's guides.

## Step 1 — Look at the machine (read-only)
Find out the operating system and whether `git`, `python3` (3.9 or newer) and `docker` are available (`git --version`, `python3 --version`, `docker --version`). Do not install anything yet. Tell the user what you found.

- macOS without `git`/`python3`: they come with Apple's command line tools — `xcode-select --install` (ask first; a system dialog opens).
- Linux: `sudo apt install -y git python3` (Debian/Ubuntu; ask first).
- Windows: recommend WSL 2 with Ubuntu (`wsl --install` in an administrator PowerShell, then restart) and continue inside the Ubuntu terminal.
Docker is installed later, with the MCP's help.

## Step 2 — Download the app
Ask where to keep it (suggest `~/hrdd`). Then:
```bash
mkdir -p ~/hrdd && cd ~/hrdd
git clone https://github.com/DFergo/LAIUNI.git app
```
The app is in `~/hrdd/app` (it contains `SETUP-AGENT.md`, `deploy/`, `ops/`).

## Step 3 — Connect the HRDD MCP server
It is a single Python file with no dependencies: `~/hrdd/app/ops/hrdd_mcp.py`. Use the absolute path.

- **Claude Code**: `claude mcp add --scope user hrdd -- python3 /ABSOLUTE/PATH/hrdd/app/ops/hrdd_mcp.py`
- **Claude Desktop**: add to `claude_desktop_config.json` (Settings → Developer → Edit Config):
  `{"mcpServers": {"hrdd": {"command": "python3", "args": ["/ABSOLUTE/PATH/hrdd/app/ops/hrdd_mcp.py"]}}}` and restart the app.
- **Cursor**: `~/.cursor/mcp.json` with the same `mcpServers` entry.
- **Codex CLI**: `codex mcp add hrdd -- python3 /ABSOLUTE/PATH/hrdd/app/ops/hrdd_mcp.py`
- Other agents: a local stdio MCP server, command `python3 <path>/ops/hrdd_mcp.py`.

Quick self-test (read-only): `python3 ~/hrdd/app/ops/hrdd_mcp.py call check_machine` prints a JSON report.

Most clients only load a new MCP server in a new session: tell the user to restart the agent (in Claude Code: exit and run `claude` again, in the same folder) and to say **"continue the HRDD Helper setup"**.

## Step 4 — Hand over to the MCP
In the new session, use the `hrdd` MCP server: run its prompt **`start`** (Claude Code: `/mcp__hrdd__start`), or call its tool `guide` with topic `overview` and follow it. From here on the MCP's guides and tools lead the process; it asks the user before every change.

## Later
- Cloudflare (public websites): the MCP's guide `domain-cloudflare` explains when to add Cloudflare's own plugin.
- To come back later: open the agent and say "use the hrdd MCP to …" (add a frontend, change models, diagnose a problem, update). The MCP's prompts `add-frontend`, `configure`, `diagnose`, `update` cover the common cases.
- Full manual for humans: `docs/INSTALL.md`.
