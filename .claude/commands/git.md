# /git — Commit & Push Helper

Generate git commit and push commands for the current work.

## Instructions

1. Read `docs/STATUS.md` to identify the current sprint name/number
2. Analyze all uncommitted changes (`git status` + `git diff`)
3. Generate a single code block with:
   - `git add -A` + `git commit` with a descriptive message
   - Commit message format: `feat: Sprint <name> — <short summary>`
   - Body: bullet points describing the changes
   - Push to both remotes: `origin` (GitHub) and `gitea`

## Output Format

```bash
git add -A && git commit -m "<message>"

git push origin main && git push gitea main
```

## Rules
- NEVER execute git commands directly — only provide them for the user to run
- Keep the commit message concise but descriptive
- Always include the sprint identifier in the commit message
- Always push to both `origin` and `gitea`
- Do NOT include Co-Authored-By lines in commit messages
