"""Fetch the latest customer-login workbook from the enterprise mailbox."""

from __future__ import annotations

import email
import imaplib
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REPORT_TIME_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d{2})-(\d{2})$")


class FreshEmailNotFound(RuntimeError):
    """Raised when the report expected for the current update slot is missing."""


@dataclass(frozen=True)
class EmailCandidate:
    message_id: bytes
    subject: str
    sender: str
    report_datetime: datetime
    received_at: datetime


def decode_mime_header(value: str | None) -> str:
    """Decode a MIME header into readable text."""
    return str(make_header(decode_header(value or "")))


def parse_report_datetime(subject: str) -> datetime | None:
    """Extract the report timestamp from the end of a message subject."""
    match = REPORT_TIME_PATTERN.search(subject.strip())
    if not match:
        return None
    date_part, hour, minute = match.groups()
    parsed = datetime.strptime(f"{date_part} {hour}:{minute}", "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=BEIJING_TZ)


def expected_report_datetime(now: datetime, slots: list[str]) -> datetime | None:
    """Return the latest report slot that should have arrived by now."""
    local_now = now.astimezone(BEIJING_TZ)
    eligible = []
    for slot in slots:
        slot_time = time.fromisoformat(slot)
        candidate = datetime.combine(local_now.date(), slot_time, tzinfo=BEIJING_TZ)
        if candidate <= local_now:
            eligible.append(candidate)
    return max(eligible) if eligible else None


def connect_mailbox(config: dict) -> imaplib.IMAP4_SSL:
    """Connect to the mailbox using environment-provided credentials."""
    email_config = config["email"]
    server = os.environ.get("IMAP_SERVER", email_config["imap_server"])
    port = int(os.environ.get("IMAP_PORT", email_config.get("imap_port", 993)))
    account = os.environ.get("EMAIL_ACCOUNT", email_config["email_account"])
    password = os.environ.get("EMAIL_PASSWORD", "")
    if not password:
        raise ValueError("EMAIL_PASSWORD is required")

    mailbox = imaplib.IMAP4_SSL(server, port, timeout=30)
    mailbox.login(account, password)
    status, _ = mailbox.select("INBOX", readonly=True)
    if status != "OK":
        mailbox.logout()
        raise RuntimeError("Unable to open INBOX")
    return mailbox


def _header_message(mailbox: imaplib.IMAP4_SSL, message_id: bytes) -> email.message.Message:
    status, response = mailbox.fetch(
        message_id,
        "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])",
    )
    if status != "OK":
        raise RuntimeError(f"Unable to fetch header for message {message_id!r}")
    raw = next((item[1] for item in response if isinstance(item, tuple)), b"")
    return email.message_from_bytes(raw)


def find_latest_email(
    mailbox: imaplib.IMAP4_SSL,
    config: dict,
    *,
    now: datetime | None = None,
    require_current_slot: bool = False,
) -> EmailCandidate:
    """Find the latest matching report after decoding headers client-side."""
    email_config = config["email"]
    local_now = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    lookback_days = int(email_config.get("lookback_days", 2))
    start_date = (local_now.date() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
    sender_filter = email_config.get("sender_filter", "").strip()
    subject_prefix = email_config["subject_prefix"]

    criteria: list[str] = ["SINCE", start_date]
    if sender_filter:
        criteria.extend(["FROM", sender_filter])
    status, response = mailbox.search(None, *criteria)
    if status != "OK":
        raise RuntimeError("IMAP search failed")

    candidates: list[EmailCandidate] = []
    for message_id in response[0].split():
        msg = _header_message(mailbox, message_id)
        subject = decode_mime_header(msg.get("Subject"))
        if not subject.startswith(subject_prefix):
            continue
        report_datetime = parse_report_datetime(subject)
        if report_datetime is None or report_datetime > local_now + timedelta(minutes=5):
            continue

        received_at = parsedate_to_datetime(msg.get("Date"))
        if received_at is None:
            received_at = report_datetime
        elif received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=BEIJING_TZ)
        received_at = received_at.astimezone(BEIJING_TZ)
        candidates.append(
            EmailCandidate(
                message_id=message_id,
                subject=subject,
                sender=decode_mime_header(msg.get("From")),
                report_datetime=report_datetime,
                received_at=received_at,
            )
        )

    if not candidates:
        raise FreshEmailNotFound("No matching customer-login email was found")

    latest = max(candidates, key=lambda item: item.report_datetime)
    if require_current_slot:
        expected = expected_report_datetime(
            local_now,
            email_config.get("report_slots", ["10:45", "13:15", "16:40"]),
        )
        if expected and latest.report_datetime < expected:
            raise FreshEmailNotFound(
                f"Latest report is {latest.report_datetime:%Y-%m-%d %H:%M}; "
                f"expected at least {expected:%Y-%m-%d %H:%M}"
            )
    return latest


def download_attachment(
    mailbox: imaplib.IMAP4_SSL,
    candidate: EmailCandidate,
    config: dict,
    output_dir: str | Path,
) -> dict:
    """Download the single Excel attachment from a selected message."""
    status, response = mailbox.fetch(candidate.message_id, "(BODY.PEEK[])")
    if status != "OK":
        raise RuntimeError("Unable to fetch the selected email")
    raw = next((item[1] for item in response if isinstance(item, tuple)), b"")
    msg = email.message_from_bytes(raw)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    attachment_prefix = config["email"].get("attachment_prefix", "")
    attachments: list[Path] = []
    for part in msg.walk():
        filename = decode_mime_header(part.get_filename())
        if not filename or not filename.lower().endswith(".xlsx"):
            continue
        if attachment_prefix and not filename.startswith(attachment_prefix):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        filepath = output_path / Path(filename).name
        filepath.write_bytes(payload)
        attachments.append(filepath)

    if len(attachments) != 1:
        raise RuntimeError(f"Expected one matching XLSX attachment, found {len(attachments)}")
    return {
        "path": str(attachments[0]),
        "subject": candidate.subject,
        "sender": candidate.sender,
        "report_datetime": candidate.report_datetime.isoformat(),
        "received_at": candidate.received_at.isoformat(),
    }


def fetch_latest_attachment(
    config: dict,
    output_dir: str | Path,
    *,
    require_current_slot: bool = False,
) -> dict:
    """Connect, select the latest matching email, and download its workbook."""
    mailbox = connect_mailbox(config)
    try:
        candidate = find_latest_email(
            mailbox,
            config,
            require_current_slot=require_current_slot,
        )
        return download_attachment(mailbox, candidate, config, output_dir)
    finally:
        try:
            mailbox.logout()
        except imaplib.IMAP4.error:
            pass
