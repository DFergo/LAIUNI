# Branding: names, colours and logos (and what to review when the organization is not UNI)

The app is not tied to one organization. Everything that identifies it is a **token** in one catalog; nothing else in the app hardcodes it. Tokens are set once for the whole installation (**global**) and any frontend can override them. What a frontend leaves unset follows the global value, which follows the default (UNI's look, the app's original one).

## The tokens
| Token | Default | Where it shows |
|---|---|---|
| `org_name` | UNI Global Union | top bar (right), logo descriptions, default disclaimer / instructions, emails |
| `org_short_name` | UNI | short mentions in the default texts |
| `tool_name` | HRDD Helper | top bar title, browser tab, admin panel, emails |
| `color_primary` | #003087 | top bar, buttons, links, user chat bubbles |
| `color_on_primary` | #FFFFFF | text on the primary colour (use a dark colour if the primary is light) |
| `color_accent` | #E31837 | alerts, errors, destructive actions |
| `color_dark` | #1A1A2E | admin panel header |
| logo `header` | bundled | top bar (a white version is made from a transparent PNG automatically) |
| logo `page` | bundled | language, disclaimer and instructions pages |
| logo `chat_bg` | the page logo | faded background of the chat |

Fixed, not a token: the copyright line "© 2026 UNI Global Union".
Disclaimer and instructions texts may use `{{org_name}}`, `{{org_short_name}}` and `{{tool_name}}`; they are replaced when the page is shown and survive translation unchanged.

## Global branding (every frontend by default)
```
admin_api GET  /admin/branding                         → every token with its value, default and source, the logos, readability warnings
admin_api PUT  /admin/branding {"values": {"org_name": "Union X", "org_short_name": "UX", "tool_name": "Rights Desk",
                                            "color_primary": "#0A7F3C", "color_on_primary": "#FFFFFF"}}
admin_upload path="/admin/branding/logo/header"  file="~/logo.png"        (also page, chat_bg)
admin_api DELETE /admin/branding/logo/header
admin_api POST /admin/branding/reset                   (back to the defaults; needs confirm_destructive)
```
- An empty value in `values` puts that token back to its default. Colours are `#RRGGBB`.
- Frontends pick up a change within seconds. The admin panel wears the same colours and names.
- Look at `warnings` in the answer: a primary colour with unreadable text on it is reported (set `color_on_primary` to a dark colour for light primaries).

## One frontend with its own look
```
admin_api GET /admin/frontends/<id>/branding           → its settings + "catalog" (each token: value, inherited value, source)
admin_api PUT /admin/frontends/<id>/branding           → send the whole object you got, with the changes:
    {"tokens": {"org_name": "Campaign X", "color_primary": "#112233"}, ...rest as received...}
admin_upload path="/admin/frontends/<id>/branding/logo/chat_bg" file="~/logo.png"
admin_api DELETE /admin/frontends/<id>/branding/logo/chat_bg      (back to the global logo)
```
- In `tokens`, a value sets the override, an empty value ("") removes it. Leaving `tokens` out keeps what is saved.
- `app_title` is this frontend's tool name (same as `tokens.tool_name`).
- This PUT replaces the texts too: always start from the GET.

## What to ask the user (survey)
Organization name and a short name; what the tool should be called; two or three brand colours (or a website to read them from) and the text colour for buttons; their logo files (PNG with transparent background is best). Show the result with the contrast warnings before saving, and open a frontend to see it (`check_frontend`, then the site).

## When the organization is not UNI: review the prompts
The tokens change what people **see**. The assistant's instructions (prompts) and the knowledge it draws on still describe UNI's world in places, and that must be reviewed with the user — do not edit silently, and do not skip it.

1. **Find the mentions** (read-only). `admin_api GET /admin/prompts` lists the prompts; read each (`GET /admin/prompts/<name>`) and note where it names UNI, "UNI Global Union", the UNI summary / report, or an escalation path through UNI ("worker → national union → UNI"). Also look at the glossary and organizations list (`GET /admin/knowledge/organizations`, `/glossary`) and the knowledge-base documents (`GET /admin/rag/documents`).
2. **Write a short plan** for the user, in plain words: which prompts mention the old organization and what each mention does (who receives the internal summary? who is the escalation point? who is the example union?), what you propose to put instead, and what you suggest keeping. Prompts that carry methodology (frameworks, interview technique) normally stay as they are.
3. **Discuss it.** Ask what their escalation path is, who reads the internal reports, whether the reference organizations list should be replaced by their own (per-frontend lists are possible: guide `configure`). One prompt at a time if the user prefers.
4. **Apply** each agreed change with `PUT /admin/prompts/<name>` (or per frontend, guide `configure`), re-read it, and run `test_smoke`. `POST /admin/prompts/reset` restores a prompt to the shipped version if something goes wrong.
Record in `profile_save` that the review was done (`{"prompt_review": "done"}`) so a later session does not repeat it.
