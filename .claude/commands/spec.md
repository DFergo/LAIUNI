# /spec — Specification Manager

Read and manage the product specification.

## Usage
- `/spec` — Show current spec summary
- `/spec section <name>` — Show a specific section
- `/spec update <section>` — Update a section based on discussion

## Instructions

1. Read `docs/SPEC-v2.md`
2. If no arguments, provide a concise summary of the current spec state
3. If a section is named, show that section's content
4. If updating, modify the spec file and show the diff
5. After any update, also update `docs/STATUS.md` if the change affects current work
6. NEVER remove existing content without explicit confirmation — only add or modify
