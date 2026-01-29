# Image Central

Image Central is a Python/FastAPI service that centralizes VM image governance and sync across multiple Nutanix Prism Central instances, with a built‑in UI for managing images, PCs, and sync jobs.

## Quick start (dev)

1) Create venv and install deps:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Create env file:

```
cp .env.example .env
```

3) Run the API:

```
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Core concepts

- Image Hub = source of truth for images, metadata, approvals.
- Prism Central connectors = per-PC sync target, driven by hub jobs.

## API highlights

- POST `/images` (multipart upload)
- POST `/images/{image_id}/approve`
- POST `/images/{image_id}/publish` (creates sync jobs)
- POST `/pcs` (register Prism Central)
- GET `/sync-jobs`

## Notes

- For production, store secrets in a vault (do not store PC passwords in DB).
- Use S3-compatible storage (Nutanix Objects, MinIO, AWS S3).
- Run Celery workers to process sync jobs asynchronously.
