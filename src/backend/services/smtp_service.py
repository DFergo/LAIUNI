"""SMTP service — email sending for auth codes, notifications, and reports.

Sprint 9: Best-effort email sending. Failures are logged but never block the system.
"""

import json
import logging
import secrets
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib

logger = logging.getLogger("backend.smtp")

_SETTINGS_PATH = Path("/app/data/smtp_config.json")
_AUTHORIZED_EMAILS_PATH = Path("/app/data/authorized_emails.json")

# In-memory auth code store: {session_token: {email, code, expires_at}}
_pending_codes: dict[str, dict[str, Any]] = {}
CODE_EXPIRY_SECONDS = 600  # 10 minutes


# --- Config ---

def _load_config() -> dict[str, Any]:
    defaults = {
        "host": "",
        "port": 587,
        "username": "",
        "password": "",
        "use_tls": True,
        "from_address": "",
        "notification_emails": [],
        "notify_on_report": False,
        "send_summary_to_user": False,
        "send_report_to_user": False,
    }
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text())
            # Migrate: old single admin_notify_address → notification_emails list
            if "admin_notify_address" in data and "notification_emails" not in data:
                old = data.pop("admin_notify_address", "")
                data["notification_emails"] = [old] if old else []
            elif "admin_notify_address" in data:
                data.pop("admin_notify_address", None)
            for key, val in defaults.items():
                data.setdefault(key, val)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load SMTP config: {e}, using defaults")
    return defaults


def is_configured() -> bool:
    """Check if SMTP has minimum config to send."""
    cfg = _load_config()
    return bool(cfg.get("host") and cfg.get("from_address"))


# --- Authorized Emails ---

def load_authorized_emails() -> list[str]:
    if _AUTHORIZED_EMAILS_PATH.exists():
        try:
            data = json.loads(_AUTHORIZED_EMAILS_PATH.read_text())
            return [e.lower().strip() for e in data.get("emails", [])]
        except Exception:
            pass
    return []


def save_authorized_emails(emails: list[str]):
    clean = sorted(set(e.lower().strip() for e in emails if e.strip()))
    _AUTHORIZED_EMAILS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _AUTHORIZED_EMAILS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"emails": clean}, indent=2))
    tmp.rename(_AUTHORIZED_EMAILS_PATH)
    logger.info(f"Authorized emails updated: {len(clean)} entries")


def is_email_authorized(email: str) -> bool:
    return email.lower().strip() in load_authorized_emails()


# --- Email Sending ---

async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email. Returns True on success, False on failure. Never raises."""
    cfg = _load_config()
    if not cfg.get("host") or not cfg.get("from_address"):
        logger.debug("SMTP not configured, skipping email")
        return False

    msg = EmailMessage()
    msg["From"] = cfg["from_address"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            username=cfg.get("username") or None,
            password=cfg.get("password") or None,
            start_tls=cfg.get("use_tls", True),
        )
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


async def test_connection() -> dict[str, str]:
    """Test SMTP connection. Returns status dict."""
    cfg = _load_config()
    if not cfg.get("host"):
        return {"status": "error", "message": "SMTP host not configured"}

    try:
        smtp = aiosmtplib.SMTP(
            hostname=cfg["host"],
            port=cfg["port"],
            start_tls=cfg.get("use_tls", True),
        )
        await smtp.connect()
        if cfg.get("username") and cfg.get("password"):
            await smtp.login(cfg["username"], cfg["password"])
        await smtp.quit()

        # Send test email if notification emails configured
        notify_emails = cfg.get("notification_emails", [])
        if notify_emails:
            first = notify_emails[0]
            sent = await send_email(
                first,
                "HRDD Helper — SMTP Test",
                "This is a test email from HRDD Helper. SMTP is working correctly."
            )
            if sent:
                return {"status": "ok", "message": f"Connected and test email sent to {first}"}
            return {"status": "warning", "message": "Connected but failed to send test email"}

        return {"status": "ok", "message": "Connection successful"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def check_smtp_health():
    """Non-blocking health check on startup. Logs warning if unreachable."""
    cfg = _load_config()
    if not cfg.get("host"):
        return
    try:
        smtp = aiosmtplib.SMTP(
            hostname=cfg["host"],
            port=cfg["port"],
            start_tls=cfg.get("use_tls", True),
        )
        await smtp.connect()
        await smtp.quit()
        logger.info("SMTP health check: OK")
    except Exception as e:
        logger.warning(f"SMTP health check failed: {e} — email features may not work")


# --- Auth Codes ---

def generate_auth_code(session_token: str, email: str) -> str:
    """Generate a 6-digit auth code for a session."""
    code = f"{secrets.randbelow(1000000):06d}"
    _pending_codes[session_token] = {
        "email": email.lower().strip(),
        "code": code,
        "expires_at": time.time() + CODE_EXPIRY_SECONDS,
    }
    # Clean expired codes
    now = time.time()
    expired = [k for k, v in _pending_codes.items() if v["expires_at"] < now]
    for k in expired:
        del _pending_codes[k]

    return code


def verify_auth_code(session_token: str, code: str) -> bool:
    """Verify an auth code. Returns True if valid."""
    pending = _pending_codes.get(session_token)
    if not pending:
        return False
    if time.time() > pending["expires_at"]:
        del _pending_codes[session_token]
        return False
    if pending["code"] == code:
        del _pending_codes[session_token]
        return True
    return False


def get_pending_email(session_token: str) -> str | None:
    """Get the email associated with a pending auth code."""
    pending = _pending_codes.get(session_token)
    if pending and time.time() <= pending["expires_at"]:
        return pending["email"]
    return None


async def send_auth_code(email: str, code: str, language: str = "en") -> bool:
    """Send an auth code email. Returns True on success."""
    subjects = {
        "en": "HRDD Helper — Your verification code",
        "es": "HRDD Helper — Tu código de verificación",
        "fr": "HRDD Helper — Votre code de vérification",
    }
    bodies = {
        "en": f"Your verification code is: {code}\n\nThis code expires in 10 minutes.\nIf you did not request this code, please ignore this email.",
        "es": f"Tu código de verificación es: {code}\n\nEste código caduca en 10 minutos.\nSi no has solicitado este código, ignora este email.",
        "fr": f"Votre code de vérification est : {code}\n\nCe code expire dans 10 minutes.\nSi vous n'avez pas demandé ce code, veuillez ignorer cet email.",
    }
    subject = subjects.get(language, subjects["en"])
    body = bodies.get(language, bodies["en"])
    return await send_email(email, subject, body)


# --- Notification recipients ---

_CAMPAIGNS_DIR = Path("/app/data/campaigns")

def _resolve_notification_recipients(frontend_id: str = "") -> list[str]:
    """Resolve notification recipients: per-frontend list + global fallback."""
    recipients: list[str] = []

    # Per-frontend notification emails
    if frontend_id:
        fe_config_path = _CAMPAIGNS_DIR / frontend_id / "notification_config.json"
        if fe_config_path.exists():
            try:
                data = json.loads(fe_config_path.read_text())
                fe_emails = data.get("notification_emails", [])
                recipients.extend(e.lower().strip() for e in fe_emails if e.strip())
            except (json.JSONDecodeError, OSError):
                pass

    # Global notification emails (always added)
    cfg = _load_config()
    global_emails = cfg.get("notification_emails", [])
    recipients.extend(e.lower().strip() for e in global_emails if e.strip())

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for e in recipients:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique


def save_frontend_notification_emails(frontend_id: str, emails: list[str]):
    """Save per-frontend notification emails."""
    dir_path = _CAMPAIGNS_DIR / frontend_id
    dir_path.mkdir(parents=True, exist_ok=True)
    config_path = dir_path / "notification_config.json"
    clean = sorted(set(e.lower().strip() for e in emails if e.strip()))
    tmp = config_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"notification_emails": clean}, indent=2))
    tmp.rename(config_path)
    logger.info(f"Frontend {frontend_id} notification emails updated: {len(clean)} entries")


def load_frontend_notification_emails(frontend_id: str) -> list[str]:
    """Load per-frontend notification emails."""
    config_path = _CAMPAIGNS_DIR / frontend_id / "notification_config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            return [e.lower().strip() for e in data.get("notification_emails", []) if e.strip()]
        except (json.JSONDecodeError, OSError):
            pass
    return []


# --- Notifications ---

async def notify_admin_report(session_token: str, report_content: str, frontend_id: str = ""):
    """Notify all configured recipients that a report was generated."""
    cfg = _load_config()
    if not cfg.get("notify_on_report"):
        return
    recipients = _resolve_notification_recipients(frontend_id)
    if not recipients:
        return
    subject = f"HRDD Helper — Report generated for session {session_token}"
    body = f"A report has been generated for session {session_token}.\n\n---\n\n{report_content}"
    for addr in recipients:
        await send_email(addr, subject, body)


async def send_user_summary(email: str, session_token: str, summary: str, language: str = "en"):
    """Send session summary to user."""
    cfg = _load_config()
    if not cfg.get("send_summary_to_user"):
        return
    subjects = {
        "en": f"HRDD Helper — Session summary ({session_token})",
        "es": f"HRDD Helper — Resumen de sesión ({session_token})",
        "fr": f"HRDD Helper — Résumé de session ({session_token})",
    }
    subject = subjects.get(language, subjects["en"])
    await send_email(email, subject, summary)


async def send_user_report(email: str, session_token: str, report: str, language: str = "en"):
    """Send report to user."""
    cfg = _load_config()
    if not cfg.get("send_report_to_user"):
        return
    subjects = {
        "en": f"HRDD Helper — Session report ({session_token})",
        "es": f"HRDD Helper — Informe de sesión ({session_token})",
        "fr": f"HRDD Helper — Rapport de session ({session_token})",
    }
    subject = subjects.get(language, subjects["en"])
    await send_email(email, subject, report)
