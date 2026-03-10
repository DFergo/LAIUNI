# /sprint — Sprint Manager

Plan and execute development sprints.

## Usage
- `/sprint plan <name>` — Plan a new sprint
- `/sprint start` — Begin the current planned sprint
- `/sprint done` — Finalize current sprint

## Instructions

### Planning
1. Read `docs/SPEC-v2.md` for requirements
2. Read `docs/STATUS.md` for current state
3. Read `docs/knowledge/lessons-learned.md` for pitfalls to avoid
4. Read `docs/ideas.md` — check if any captured ideas are relevant to this sprint and present them to Daniel
5. Define sprint scope with clear deliverables
6. Write plan to `docs/STATUS.md` under new sprint heading

### Starting
1. Confirm sprint plan exists in STATUS.md
2. Begin implementation following the plan
3. Update STATUS.md as items are completed

### Finalizing
1. Update STATUS.md — mark sprint complete
2. Update CHANGELOG.md with sprint summary
3. Provide git commit command (heredoc format):
```bash
git add -A && git commit -m "$(cat <<'EOF'
feat: Sprint <name> — <description>

<details>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```
4. Provide docker rebuild commands for affected containers
5. NEVER execute git commands directly
