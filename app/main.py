from datetime import datetime
import os
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, ensure_sqlite_columns, get_db
from app.models import Image, PrismCentral, SyncJob
from app.schemas import (
    ImageRead,
    PrismCentralCreate,
    PrismCentralRead,
    SyncJobRead,
)
from app.storage import storage_client
from app.tasks import run_sync_job
from app.prism import PrismClient

Base.metadata.create_all(bind=engine)
ensure_sqlite_columns()

app = FastAPI(title="Image Hub", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ASSET_DIR = "/Users/ayush.srivastava/.cursor/projects/Users-ayush-srivastava-Desktop-temp/assets"
if os.path.isdir(ASSET_DIR):
    app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        "home.html", {"request": request, "title": "Home"}
    )


@app.post("/pcs", response_model=PrismCentralRead)
def register_pc(payload: PrismCentralCreate, db: Session = Depends(get_db)):
    pc = PrismCentral(
        name=payload.name,
        api_url=payload.api_url,
        username=payload.username or settings.pc_default_username,
        password=payload.password or settings.pc_default_password,
    )
    if settings.pc_validate_connection:
        PrismClient(pc).ping()
    db.add(pc)
    db.commit()
    db.refresh(pc)
    return pc


@app.get("/pcs", response_model=List[PrismCentralRead])
def list_pcs(db: Session = Depends(get_db)):
    return db.query(PrismCentral).all()


@app.post("/images", response_model=ImageRead)
def upload_image(
    name: str = Form(...),
    version: str = Form(...),
    source: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    payload = file.file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file.")

    image = Image(
        name=name,
        version=version,
        source=source,
        sha256="pending",
        storage_uri="pending",
        approved=False,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    storage_uri, digest = storage_client.save(image.id, file.filename, payload)
    image.sha256 = digest
    image.storage_uri = storage_uri
    db.commit()
    db.refresh(image)
    return image


@app.get("/images", response_model=List[ImageRead])
def list_images(db: Session = Depends(get_db)):
    return db.query(Image).all()


@app.get("/images/{image_id}/download")
def download_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")

    if image.storage_uri.startswith("s3://"):
        body, filename, content_length = storage_client.open_s3_stream(
            image.storage_uri
        )
        return StreamingResponse(
            body,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(content_length) if content_length else None,
            },
        )

    filename = os.path.basename(image.storage_uri)
    return FileResponse(path=image.storage_uri, filename=filename)


@app.head("/images/{image_id}/download")
def download_image_head(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")

    if image.storage_uri.startswith("s3://"):
        filename, content_length = storage_client.head_s3_object(image.storage_uri)
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return PlainTextResponse("", headers=headers)

    if not os.path.exists(image.storage_uri):
        raise HTTPException(status_code=404, detail="Image file not found.")
    filename = os.path.basename(image.storage_uri)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(os.path.getsize(image.storage_uri)),
    }
    return PlainTextResponse("", headers=headers)


@app.get("/reachability")
def reachability_check():
    return PlainTextResponse("ok")


@app.post("/images/{image_id}/approve", response_model=ImageRead)
def approve_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    image.approved = True
    db.commit()
    db.refresh(image)
    return image


@app.post("/images/{image_id}/publish", response_model=List[SyncJobRead])
def publish_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    if not image.approved:
        raise HTTPException(status_code=400, detail="Image not approved.")

    pcs = db.query(PrismCentral).all()
    if not pcs:
        raise HTTPException(status_code=400, detail="No Prism Central instances.")

    jobs: List[SyncJob] = []
    for pc in pcs:
        job = SyncJob(
            image_id=image.id,
            pc_id=pc.id,
            status="queued",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        jobs.append(job)

        if settings.celery_broker_url:
            run_sync_job.delay(job.id)
        else:
            run_sync_job(job.id)

    return jobs


@app.get("/sync-jobs", response_model=List[SyncJobRead])
def list_sync_jobs(db: Session = Depends(get_db)):
    return db.query(SyncJob).all()


@app.get("/ui/tasks")
def ui_list_tasks(request: Request, db: Session = Depends(get_db)):
    jobs = db.query(SyncJob).all()
    return templates.TemplateResponse(
        "tasks/index.html",
        {"request": request, "title": "Tasks", "jobs": jobs},
    )


@app.get("/ui/images")
def ui_list_images(request: Request, db: Session = Depends(get_db)):
    images = db.query(Image).all()
    return templates.TemplateResponse(
        "images/index.html",
        {"request": request, "title": "Images", "images": images},
    )


@app.get("/ui/pcs")
def ui_list_pcs(request: Request, db: Session = Depends(get_db)):
    pcs = db.query(PrismCentral).all()
    return templates.TemplateResponse(
        "pcs/index.html", {"request": request, "title": "Prism Centrals", "pcs": pcs}
    )


@app.get("/ui/pcs/new")
def ui_new_pc(request: Request):
    return templates.TemplateResponse(
        "pcs/new.html",
        {
            "request": request,
            "title": "Register Prism Central",
        },
    )


@app.post("/ui/pcs/new")
def ui_register_pc(
    request: Request,
    address: str = Form(...),
    port: str = Form(...),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    address = address.strip()
    port = port.strip()
    username = (username or "").strip()
    password = (password or "").strip()

    errors = []
    if not address:
        errors.append("Address is required.")
    if "://" in address:
        errors.append("Address should not include a scheme (use host only).")
    if not port.isdigit():
        errors.append("Port must be a number.")
    else:
        port_value = int(port)
        if port_value < 1 or port_value > 65535:
            errors.append("Port must be between 1 and 65535.")
    if not username:
        errors.append("Username is required.")
    if not password:
        errors.append("Password is required.")

    if errors:
        return templates.TemplateResponse(
            "pcs/new.html",
            {
                "request": request,
                "title": "Register Prism Central",
                "message": " ".join(errors),
            },
            status_code=400,
        )

    api_url = f"https://{address}:{port}"
    name = address
    pc = PrismCentral(
        name=name,
        api_url=api_url,
        username=username or settings.pc_default_username,
        password=password or settings.pc_default_password,
    )
    if settings.pc_validate_connection:
        try:
            PrismClient(pc).ping()
        except Exception as exc:
            return templates.TemplateResponse(
                "pcs/new.html",
                {
                    "request": request,
                    "title": "Register Prism Central",
                    "message": f"Connection failed: {exc}",
                },
                status_code=400,
            )
    db.add(pc)
    db.commit()
    return RedirectResponse(url="/ui/pcs", status_code=303)


@app.post("/ui/pcs/{pc_id}/delete")
def ui_delete_pc(pc_id: int, db: Session = Depends(get_db)):
    pc = db.query(PrismCentral).filter(PrismCentral.id == pc_id).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Prism Central not found.")
    db.query(SyncJob).filter(SyncJob.pc_id == pc_id).delete()
    db.delete(pc)
    db.commit()
    return RedirectResponse(url="/ui/pcs", status_code=303)


@app.get("/ui/images/upload")
def ui_upload_form(request: Request):
    return templates.TemplateResponse(
        "images/upload.html", {"request": request, "title": "Upload Image"}
    )


@app.post("/ui/images/upload")
def ui_upload_image(
    request: Request,
    name: str = Form(...),
    version: str = Form(...),
    source: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    payload = file.file.read()
    if not payload:
        return templates.TemplateResponse(
            "images/upload.html",
            {
                "request": request,
                "title": "Upload Image",
                "message": "Empty file.",
            },
            status_code=400,
        )

    image = Image(
        name=name,
        version=version,
        source=source,
        sha256="pending",
        storage_uri="pending",
        approved=False,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    storage_uri, digest = storage_client.save(image.id, file.filename, payload)
    image.sha256 = digest
    image.storage_uri = storage_uri
    db.commit()

    return RedirectResponse(url="/ui/images", status_code=303)


@app.get("/ui/images/{image_id}")
def ui_image_detail(image_id: int, request: Request, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    return templates.TemplateResponse(
        "images/detail.html",
        {"request": request, "title": "Image Details", "image": image},
    )


@app.post("/ui/images/{image_id}/approve")
def ui_approve_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    image.approved = True
    db.commit()
    return RedirectResponse(url=f"/ui/images/{image_id}", status_code=303)


@app.post("/ui/images/{image_id}/publish")
def ui_publish_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    if not image.approved:
        return RedirectResponse(url=f"/ui/images/{image_id}", status_code=303)

    pcs = db.query(PrismCentral).all()
    if not pcs:
        return RedirectResponse(url=f"/ui/images/{image_id}", status_code=303)

    for pc in pcs:
        job = SyncJob(
            image_id=image.id,
            pc_id=pc.id,
            status="queued",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        if settings.celery_broker_url:
            run_sync_job.delay(job.id)
        else:
            run_sync_job(job.id)

    return RedirectResponse(url=f"/ui/images/{image_id}", status_code=303)


@app.post("/ui/images/{image_id}/delete")
def ui_delete_image(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found.")
    db.query(SyncJob).filter(SyncJob.image_id == image_id).delete()
    db.delete(image)
    db.commit()
    return RedirectResponse(url="/ui/images", status_code=303)
