from datetime import datetime
import json

from celery import Celery
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Image, PrismCentral, SyncJob
from app.prism import PrismClient

celery_app = Celery(
    "image_hub",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


@celery_app.task
def run_sync_job(job_id: int):
    db: Session = SessionLocal()
    try:
        job = db.query(SyncJob).filter(SyncJob.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()

        image = db.query(Image).filter(Image.id == job.image_id).first()
        pc = db.query(PrismCentral).filter(PrismCentral.id == job.pc_id).first()
        if not image or not pc:
            job.status = "failed"
            job.detail = "Missing image or PC."
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        pc.connected = False
        pc.last_checked_at = datetime.utcnow()
        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()

        result = PrismClient(pc).import_image(image)
        job.status = "completed"
        job.detail = json.dumps(result)
        job.updated_at = datetime.utcnow()
        task_state = ""
        task = result.get("task") if isinstance(result, dict) else None
        if isinstance(task, dict):
            task_state = task.get("status", {}).get("state", "").upper()
        elif task is not None:
            job.detail = json.dumps(
                {"error": "Unexpected task payload", "task": task}
            )
            task_state = "FAILED"
        if task_state and task_state != "SUCCEEDED":
            pc.connected = False
        else:
            pc.connected = True
        pc.last_checked_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)
        job.updated_at = datetime.utcnow()
        if "pc" in locals() and pc:
            pc.connected = False
            pc.last_checked_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
