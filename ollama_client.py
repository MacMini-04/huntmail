# app/ollama_client.py
import requests
from typing import List, Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"  # or whatever model name you use locally


class OllamaError(Exception):
    pass


def classify_emails(emails: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Ask Ollama which folder each email should go into.

    emails: list of dicts with at least:
      - id: str
      - subject: str
      - sender: str
      - preview: str (short body text)

    Returns:
      dict mapping email_id -> folder_name
    """
    if not emails:
        return {}

    prompt_lines = [
        "You are an email classification assistant for a Mac Mail user.",
        "You are given a list of emails and must decide which folder each email should be moved into.",
        "Respond ONLY with JSON of the form:",
        '{ "email_id": "folder_name", ... }',
        "",
        "Here are the emails:",
    ]

    for e in emails:
        prompt_lines.append(
            f'- id: "{e["id"]}", sender: "{e["sender"]}", '
            f'subject: "{e["subject"]}", preview: "{e["preview"]}"'
        )

    prompt_lines.append("")
    prompt_lines.append(
        "Decide folder names using short, consistent labels like "
        '"Work", "Finance", "Newsletters", "Personal", or "Other". '
        "If unsure, use \"Other\"."
    )

    prompt = "\n".join(prompt_lines)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
    except requests.RequestException as exc:
        raise OllamaError(f"Error calling Ollama: {exc}") from exc

    if resp.status_code != 200:
        raise OllamaError(
            f"Ollama returned status {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    text = data.get("response") or data.get("output") or ""

    # Very defensive parsing – assume model returns JSON somewhere in the text
    import json
    import re

    # Extract JSON block between first '{' and last '}'.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise OllamaError(f"Could not find JSON in Ollama response: {text[:500]}")

    json_str = match.group(0)
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Failed to parse JSON from Ollama: {exc}\n{text[:500]}")

    # Ensure keys/values are strings
    cleaned = {str(k): str(v) for k, v in result.items()}
    return cleaned
