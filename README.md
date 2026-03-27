# MailScan

Automated mail processing pipeline. Monitors an IMAP mailbox for PDF attachments, OCRs them, classifies by company using a local LLM, and logs everything to a dashboard-ready database.

## Prerequisites

- **Docker Desktop for Mac** — [install here](https://www.docker.com/products/docker-desktop)
- **Ollama** — runs natively on macOS for Metal GPU acceleration

```bash
brew install ollama
ollama serve
```

## Setup

```bash
git clone https://github.com/MacMini-04/huntmail.git
cd mailscan
cp .env.example .env
# Edit .env with your IMAP credentials
docker compose up --build
```

That's it. On first boot the system will:
1. Build the OCR container (Tesseract + ImageMagick)
2. Build the MailScan container (FastAPI)
3. Start PostgreSQL and create the database
4. Auto-pull the `llama3.2:3b` model into Ollama if it isn't already downloaded

## Services

| Service   | Port  | Description                          |
|-----------|-------|--------------------------------------|
| mailscan  | 8000  | API + IMAP poller                    |
| ocr       | —     | Internal: Tesseract OCR over HTTP    |
| db        | —     | Internal: PostgreSQL                 |
| ollama    | 11434 | Host: native macOS for Metal accel.  |

## API

- `GET /api/records` — list all processed mail (newest first)
- `GET /api/records/{id}` — single record with full OCR text
- `GET /health` — service health check
- `GET /docs` — Swagger UI

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐
│ IMAP Mailbox│────▶│  Docker                              │
└─────────────┘     │  ┌─────────┐  ┌─────┐  ┌──────────┐ │
                    │  │MailScan │─▶│ OCR │  │PostgreSQL│ │
                    │  │ :8000   │  │:5001│  │ :5432    │ │
                    │  └────┬────┘  └─────┘  └──────────┘ │
                    └───────┼──────────────────────────────┘
                            │
                    ┌───────▼───────┐
                    │ Ollama (host) │
                    │ Metal / ANE   │
                    └───────────────┘
```

## Companies

The classifier maps mail to one of:
- Huntington Oil and Gas, LLC
- Huntington Oil and Gas II, LLC
- Huntington Fermi Fusion, LLC
- CANA Ventures, LLC
