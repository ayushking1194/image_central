import importlib
import os
import sys
from pathlib import Path

import httpx
import pytest


def load_app(tmp_path: Path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["LOCAL_STORAGE_PATH"] = str(tmp_path / "storage")
    os.environ["PC_VALIDATE_CONNECTION"] = "false"
    os.environ.pop("CELERY_BROKER_URL", None)
    os.environ.pop("CELERY_RESULT_BACKEND", None)

    for module_name in list(sys.modules):
        if module_name.startswith("app."):
            del sys.modules[module_name]
        if module_name == "app":
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return main.app


def create_client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_register_and_list_pcs(tmp_path):
    app = load_app(tmp_path)
    async with create_client(app) as client:
        payload = {"name": "pc-1", "api_url": "https://pc-1.example.com:9440"}
        response = await client.post("/pcs", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "pc-1"

        response = await client.get("/pcs")
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["api_url"] == payload["api_url"]


@pytest.mark.asyncio
async def test_image_upload_approve_publish(tmp_path):
    app = load_app(tmp_path)
    async with create_client(app) as client:
        pc_payload = {
            "name": "pc-1",
            "api_url": "https://pc-1.example.com:9440",
        }
        await client.post("/pcs", json=pc_payload)

        files = {"file": ("image.qcow2", b"fake-image-bytes")}
        data = {"name": "ubuntu", "version": "1.0", "source": "golden"}
        response = await client.post("/images", data=data, files=files)
        assert response.status_code == 200
        image = response.json()
        assert image["approved"] is False

        image_id = image["id"]
        response = await client.post(f"/images/{image_id}/approve")
        assert response.status_code == 200
        assert response.json()["approved"] is True

        response = await client.post(f"/images/{image_id}/publish")
        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "queued"
