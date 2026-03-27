"""
MailScan — Dockerized mail monitoring agent.
Polls IMAP for new emails, OCRs PDF attachments, classifies via Ollama,
and logs everything to PostgreSQL.
"""

import os
import time
import email
import imaplib
import logging
import hashlib
import threading
from datetime import datetime, timezone
from email.header import decode_header

import requests
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# ---------------------------------------------------------------------------
# Config (all wired via docker-compose environment)
# ---------------------------------------------------------------------------
IMAP_HOST = os.getenv("IMAP_HOST", "imap.mail.me.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

OCR_URL = os.getenv("OCR_URL", "http://ocr:5001/ocr")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mailscan.db")

COMPANIES = [
    "Huntington Oil and Gas, LLC",
    "Huntington Oil and Gas II, LLC",
    "Huntington Fermi Fusion, LLC",
    "CANA Ventures, LLC",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("mailscan")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
Base = declarative_base()


class MailRecord(Base):
    __tablename__ = "mail_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(255), unique=True, index=True)
    subject = Column(String(512), default="")
    sender = Column(String(255), default="")
    description = Column(Text, default="")
    company = Column(String(255), default="")
    filename = Column(String(512), default="")
    ocr_text = Column(Text, default="")
    status = Column(String(64), default="processed")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------
def ollama_generate(prompt: str) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        log.error("Ollama error: %s", e)
        return ""


def describe_mail(ocr_text: str) -> str:
    prompt = (
        "You are a mail monitoring agent. Your job is to take the following "
        "OCR text extracted from a scanned mail piece and generate a concise, "
        "plain-text description of what this document is.\n\n"
        f"OCR TEXT:\n{ocr_text}\n\n"
        "DESCRIPTION:"
    )
    return ollama_generate(prompt)


def classify_company(ocr_text: str) -> str:
    company_list = ", ".join(COMPANIES)
    prompt = (
        "Your sole job is to determine which company the following mail "
        f"belongs to. The possible companies are: {company_list}. "
        "Only output the name of the one company it belongs to. "
        "Guess if you need to.\n\n"
        f"MAIL TEXT:\n{ocr_text}\n\n"
        "COMPANY:"
    )
    return ollama_generate(prompt)


# ---------------------------------------------------------------------------
# OCR helper
# ---------------------------------------------------------------------------
def ocr_attachment(file_bytes: bytes, filename: str) -> str:
    try:
        resp = requests.post(
            OCR_URL,
            files={"file": (filename, file_bytes, "application/pdf")},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("text", "")
    except Exception as e:
        log.error("OCR error for %s: %s", filename, e)
        return ""


# ---------------------------------------------------------------------------
# IMAP polling
# ---------------------------------------------------------------------------
def decode_mime_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def make_message_hash(msg: email.message.Message, fallback_uid: str) -> str:
    mid = msg.get("Message-ID", "")
    if mid:
        return mid.strip()
    raw = f"{msg.get('Date','')}{msg.get('From','')}{msg.get('Subject','')}{fallback_uid}"
    return hashlib.sha256(raw.encode()).hexdigest()


def poll_mailbox():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select(IMAP_FOLDER)
    except Exception as e:
        log.error("IMAP connection failed: %s", e)
        return

    try:
        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            log.info("No new emails.")
            return

        uids = data[0].split()
        log.info("Found %d new email(s).", len(uids))

        db = SessionLocal()
        try:
            for uid in uids:
                _process_email(mail, uid, db)
        finally:
            db.close()
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def _process_email(mail, uid: bytes, db):
    status, msg_data = mail.fetch(uid, "(RFC822)")
    if status != "OK":
        return

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    message_id = make_message_hash(msg, uid.decode())
    subject = decode_mime_header(msg.get("Subject"))
    sender = decode_mime_header(msg.get("From"))

    existing = db.query(MailRecord).filter_by(message_id=message_id).first()
    if existing:
        log.info("Skipping duplicate: %s", subject)
        return

    log.info("Processing: %s (from %s)", subject, sender)

    for part in msg.walk():
        content_type = part.get_content_type()
        filename = part.get_filename()
        if not filename:
            continue
        if content_type not in ("application/pdf", "application/octet-stream"):
            if not filename.lower().endswith(".pdf"):
                continue

        file_bytes = part.get_payload(decode=True)
        if not file_bytes:
            continue

        log.info("  Attachment: %s (%d bytes)", filename, len(file_bytes))

        # Step 1: OCR
        ocr_text = ocr_attachment(file_bytes, filename)
        if not ocr_text:
            log.warning("  OCR returned empty for %s", filename)
            continue

        # Step 2: Describe
        description = describe_mail(ocr_text)
        log.info("  Description: %s", description[:120])

        # Step 3: Classify company
        company = classify_company(ocr_text)
        log.info("  Company: %s", company)

        # Step 4: Store
        record = MailRecord(
            message_id=message_id,
            subject=subject,
            sender=sender,
            description=description,
            company=company,
            filename=filename,
            ocr_text=ocr_text,
            status="processed",
        )
        db.add(record)
        db.commit()
        log.info("  Saved record #%d", record.id)


# ---------------------------------------------------------------------------
# Background poller thread
# ---------------------------------------------------------------------------
def _poll_loop():
    log.info("IMAP poller started (every %ds)", POLL_INTERVAL)
    while True:
        try:
            poll_mailbox()
        except Exception as e:
            log.exception("Poll cycle error: %s", e)
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    log.info("MailScan is running.")
    yield


app = FastAPI(title="MailScan", version="1.0.0", lifespan=lifespan)


@app.get("/api/records")
def list_records(limit: int = 50, offset: int = 0, db=Depends(get_db)):
    records = (
        db.query(MailRecord)
        .order_by(desc(MailRecord.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "message_id": r.message_id,
            "subject": r.subject,
            "sender": r.sender,
            "description": r.description,
            "company": r.company,
            "filename": r.filename,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@app.get("/api/records/{record_id}")
def get_record(record_id: int, db=Depends(get_db)):
    record = db.query(MailRecord).filter_by(id=record_id).first()
    if not record:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {
        "id": record.id,
        "message_id": record.message_id,
        "subject": record.subject,
        "sender": record.sender,
        "description": record.description,
        "company": record.company,
        "filename": record.filename,
        "ocr_text": record.ocr_text,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
