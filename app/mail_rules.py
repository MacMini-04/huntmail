# app/mail_rules.py
from typing import List, Dict, Any

from ollama_client import classify_emails, OllamaError
from mail_client import get_inbox_emails, move_email_to_mailbox, MailClientError


def fetch_and_classify(limit: int = 20) -> Dict[str, Dict[str, str]]:
    """
    Fetch emails from Mail.app and ask Ollama to classify them.

    Returns dict:
      {
        "decisions": { email_id: folder_name, ... },
        "errors": { email_id: error_message, ... }
      }
    """
    emails = get_inbox_emails(limit=limit)

    if not emails:
        return {"decisions": {}, "errors": {}}

    try:
        decisions = classify_emails(emails)
    except OllamaError as exc:
        # If Ollama fails, we don't move anything
        return {"decisions": {}, "errors": {"_ollama": str(exc)}}

    errors: Dict[str, str] = {}

    for email in emails:
        eid = str(email["id"])
        folder = decisions.get(eid)
        if not folder:
            continue
        try:
            move_email_to_mailbox(eid, folder)
        except MailClientError as exc:
            errors[eid] = str(exc)

    return {"decisions": decisions, "errors": errors}
