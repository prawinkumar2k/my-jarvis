"""Gmail (or any IMAP/SMTP mailbox) with an app password: no Google Cloud project, no payment.

Reading uses IMAP in read-only mode, so nothing is marked as read or changed. Sending uses SMTP and is
always an explicit, per-message approval (see approval_policy). The app password lives only in `.env`;
it is never logged, shown or returned. Mail text is untrusted content: callers present it as a quote.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
import smtplib
import ssl
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

MAX_LIST = 10
BODY_CHARS = 1200
MAX_SEND_CHARS = 5000
TIMEOUT = 20
_ADDRESS = re.compile(r"^[^@\s<>\",;]+@[^@\s<>\",;]+\.[^@\s<>\",;]+$")


class MailError(RuntimeError):
    """Readable reason mail could not be used (shown to the user; never contains the password)."""


def _setting(name: str, default: str = "") -> str:
    return str(os.getenv(name) or default).strip()


def configured() -> bool:
    return bool(_setting("JARVIS_MAIL_ADDRESS") and _setting("JARVIS_MAIL_APP_PASSWORD"))


def _credentials() -> tuple[str, str]:
    address, password = _setting("JARVIS_MAIL_ADDRESS"), _setting("JARVIS_MAIL_APP_PASSWORD").replace(" ", "")
    if not address or not password:
        raise MailError(
            "Mail is not set up. Add JARVIS_MAIL_ADDRESS and JARVIS_MAIL_APP_PASSWORD to .env "
            "(Google Account > Security > 2-Step Verification > App passwords)."
        )
    return address, password


def _text(value: str | None) -> str:
    try:
        return str(make_header(decode_header(value or ""))).strip()
    except Exception:
        return str(value or "").strip()


def _imap() -> imaplib.IMAP4_SSL:
    address, password = _credentials()
    try:
        box = imaplib.IMAP4_SSL(_setting("JARVIS_MAIL_IMAP_HOST", "imap.gmail.com"),
                                int(_setting("JARVIS_MAIL_IMAP_PORT", "993")), timeout=TIMEOUT,
                                ssl_context=ssl.create_default_context())
        box.login(address, password)
    except imaplib.IMAP4.error:
        raise MailError("The mail server refused the login. Check the address and the app password.") from None
    except (OSError, ValueError):
        raise MailError("I could not reach the mail server.") from None
    return box


def _plain_text(message: email.message.Message) -> str:
    part = message
    if message.is_multipart():
        part = next((p for p in message.walk() if p.get_content_type() == "text/plain"), None)
        if part is None:
            return ""
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def recent_unread(limit: int = 5) -> list[dict]:
    """Newest unread messages: sender, subject, date and a short preview. Read-only."""
    count = max(1, min(int(limit or 5), MAX_LIST))
    box = _imap()
    try:
        if box.select("INBOX", readonly=True)[0] != "OK":
            raise MailError("I could not open the inbox.")
        status, data = box.search(None, "UNSEEN")
        ids = (data[0].split() if status == "OK" and data and data[0] else [])[-count:]
        found = []
        for number in reversed(ids):
            status, parts = box.fetch(number, "(BODY.PEEK[]<0.6000>)")
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), b"")
            if status != "OK" or not raw:
                continue
            message = email.message_from_bytes(raw)
            preview = re.sub(r"\s+", " ", _plain_text(message)).strip()[:BODY_CHARS]
            found.append({"from": _text(message.get("From")), "subject": _text(message.get("Subject")) or "(no subject)",
                          "date": _text(message.get("Date")), "preview": preview})
        return found
    except imaplib.IMAP4.error:
        raise MailError("The mail server could not list your messages.") from None
    finally:
        try:
            box.logout()
        except Exception:
            pass


def validate_message(to: str, subject: str, body: str) -> tuple[str, str, str]:
    to = str(to or "").strip()
    subject = str(subject or "").strip()
    body = str(body or "").strip()
    if not _ADDRESS.match(parseaddr(to)[1] or to) or "\n" in to or "\r" in to:
        raise MailError("Give exactly one valid email address to send to.")
    if "\n" in subject or "\r" in subject or not subject or len(subject) > 200:
        raise MailError("The subject must be one line, 1 to 200 characters.")
    if not body or len(body) > MAX_SEND_CHARS:
        raise MailError(f"The message must be 1 to {MAX_SEND_CHARS} characters.")
    return parseaddr(to)[1] or to, subject, body


def send(to: str, subject: str, body: str) -> str:
    """Send one plain-text email from the configured address. Callers must have the user's approval."""
    to, subject, body = validate_message(to, subject, body)
    address, password = _credentials()
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = address, to, subject
    message.set_content(body)
    host, port = _setting("JARVIS_MAIL_SMTP_HOST", "smtp.gmail.com"), int(_setting("JARVIS_MAIL_SMTP_PORT", "587"))
    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context) as server:
                server.login(address, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT) as server:
                server.starttls(context=context)
                server.login(address, password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise MailError("The mail server refused the login. Check the address and the app password.") from None
    except (smtplib.SMTPException, OSError):
        raise MailError("The email could not be sent.") from None
    return f"Email sent to {to}."
