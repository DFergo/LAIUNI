# /status — Project Status Manager

Track and update project status.

## Usage
- `/status` — Show current status
- `/status update` — Update STATUS.md based on recent work

## Instructions

1. Read `docs/STATUS.md`
2. If no arguments, show current sprint, what works, what's broken, and next steps
3. If updating:
   - Update the current sprint section
   - Move completed items to done
   - Add any new issues discovered
   - Update the "Last Updated" timestamp
4. Always preserve the full history — never delete previous sprint entries
5. Format: use checkboxes `[x]` for done, `[ ]` for pending, `[!]` for blocked
