# /idea — Idea Tracker

Capture, evaluate, and schedule product ideas.

## Arguments
$ARGUMENTS — Description of the idea (can be in any language)

## Instructions

1. Read these files to understand current project state:
   - `docs/MILESTONES.md` — sprint plan and deliverables
   - `docs/STATUS.md` — current sprint and what's next
   - `docs/SPEC-v2.md` — product specification
   - `docs/ideas.md` — existing ideas already captured

2. Evaluate the idea:
   - **Feasibility:** Is it technically doable with our stack?
   - **Fit:** Does it align with the product vision in the spec?
   - **Dependencies:** Does it require other sprints to be done first?
   - **Effort:** Small (hours), medium (1-2 days), large (full sprint)

3. Determine placement:
   - Does it fit in an existing sprint? → note which one and why
   - Is it a new feature not in any sprint? → suggest where it goes (new sprint or append to existing)
   - Is it a long-term improvement? → add to backlog

4. Write the idea to `docs/ideas.md` using this format:
   ```
   ### [Short title]
   **Added:** [date] | **Sprint:** [target sprint or "Backlog"] | **Effort:** [S/M/L]

   [Description as provided by user]

   **Analysis:** [1-2 sentences on feasibility and fit]
   ```

5. Present a short summary to the user:
   - One line: what the idea is
   - One line: where it fits (sprint number or backlog)
   - Flag any concerns or dependencies

## Rules
- NEVER modify MILESTONES.md or SPEC-v2.md — only suggest changes
- If the idea conflicts with the spec, flag it clearly
- If the idea duplicates an existing one in ideas.md, point it out instead of adding a duplicate
- Keep the analysis honest — if an idea is bad or doesn't fit, say so respectfully
- Respond in the same language the user used
