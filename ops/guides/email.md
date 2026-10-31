# Email for the app (SMTP)

Used for: login codes for profiles with authentication, reports and summaries to authorised people, administrator alerts (e.g. a model is down). Optional for worker-only anonymous sites, needed otherwise.

## Choose the account
Best: a **dedicated mailbox** (e.g. `hrdd@union.org` or on the app's own domain), not a person's mailbox. The app sends with **STARTTLS on port 587** (username + password). Implicit TLS on port 465 is not supported: use 587.

| Union uses | How |
|---|---|
| Google Workspace / Gmail | Server `smtp.gmail.com`, port 587. The account needs 2-Step Verification and an **app password** (Google account → Security → App passwords). Workspace admins can disable app passwords — check with them. |
| Microsoft 365 | Server `smtp.office365.com`, port 587, only if **SMTP AUTH** is enabled for that mailbox (often disabled by default). Microsoft is phasing out password-based SMTP — if their IT cannot enable it, use a transactional provider instead. |
| Own mail server / hosting (e.g. Infomaniak Mail) | The SMTP server, port 587 and mailbox credentials from the provider's help pages. |
| None of the above / problems | A transactional email service (e.g. Brevo, Mailjet — EU-based) with a sender on the app's domain; they explain the DNS records (SPF/DKIM) to add in Cloudflare. |

## Configure
The user puts the password in the local keys file (`~/.config/hrdd-ops/keys.env`, `SMTP_PASSWORD=...`):
```
admin_api PUT /admin/smtp
  {"host": "smtp.gmail.com", "port": 587, "use_tls": true,
   "username": "hrdd@union.org", "password": "env:~/.config/hrdd-ops/keys.env#SMTP_PASSWORD",
   "from_address": "hrdd@union.org", "notification_emails": ["admin@union.org"]}
admin_api POST /admin/smtp/test     (see admin_api_reference filter="smtp" for its fields)
```
Other settings (`notify_on_report`, `send_summary_to_user`, `send_report_to_user`, per-frontend notification addresses, authorised emails): explain each and ask.

## If the test fails
Authentication error → app password / SMTP AUTH; timeout → port blocked (some networks block 587 outbound) or wrong host; messages in spam → sender domain without SPF/DKIM.
