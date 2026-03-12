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

Always use a SINGLE-LINE commit message. NEVER use heredoc, `cat <<EOF`, or multi-line strings — they cause `dquote>` errors in the user's terminal.

```bash
git add -A && git commit -m "feat: Sprint X — short summary"

git push origin main && git push gitea main
```

If the message needs more detail, keep it on one line with a semicolon or dash separator:

```bash
git add -A && git commit -m "feat: Sprint X — summary; detail one, detail two"
```

## Rules
- NEVER execute git commands directly — only provide them for the user to run
- Keep the commit message concise but descriptive
- Always include the sprint identifier in the commit message
- Always push to both `origin` and `gitea`
- Do NOT include Co-Authored-By lines in commit messages
- NEVER use heredoc or multi-line commit messages — SINGLE LINE ONLY
