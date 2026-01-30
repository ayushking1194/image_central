import os
import time
import uuid
from typing import Optional

import httpx

from app.config import settings
from app.models import Image, PrismCentral


class PrismClient:
    def __init__(self, pc: PrismCentral):
        self.pc = pc

    def ping(self) -> None:
        if not self.pc.api_url:
            raise ValueError("PC api_url is required for connectivity check.")
        auth = None
        if self.pc.username and self.pc.password:
            auth = (self.pc.username, self.pc.password)
        with httpx.Client(verify=False, timeout=20, auth=auth) as client:
            response = client.post(
                f"{self.pc.api_url}/api/nutanix/v3/clusters/list",
                json={"kind": "cluster"},
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"PC connectivity check failed: {response.status_code} {response.text}"
                )
        if settings.pc_validate_hub_source:
            self.test_hub_source_uri()

    def wait_for_task(self, task_uuid: str, timeout_seconds: int = 90) -> dict:
        if not self.pc.api_url:
            raise ValueError("PC api_url is required for task polling.")
        auth = (self.pc.username, self.pc.password)
        deadline = time.time() + timeout_seconds
        with httpx.Client(verify=False, timeout=20, auth=auth) as client:
            while time.time() < deadline:
                response = client.get(
                    f"{self.pc.api_url}/api/nutanix/v3/tasks/{task_uuid}"
                )
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"PC task polling failed: {response.status_code} {response.text}"
                    )
                body = response.json()
                if not isinstance(body, dict):
                    raise RuntimeError(f"Unexpected task response: {body}")
                state = body.get("status", {}).get("state", "").upper()
                if state in {"SUCCEEDED", "FAILED", "CANCELED"}:
                    return body
                time.sleep(3)
        raise RuntimeError("PC task polling timed out.")

    def _extract_task_uuid(self, body: dict) -> Optional[str]:
        if not isinstance(body, dict):
            return None
        for key in ("task_uuid", "taskUuid"):
            if key in body:
                return body[key]
        status = body.get("status")
        if isinstance(status, dict):
            exec_ctx = status.get("execution_context") or status.get("executionContext")
            if isinstance(exec_ctx, dict):
                for key in ("task_uuid", "taskUuid"):
                    if key in exec_ctx:
                        return exec_ctx[key]
        return None

    def test_hub_source_uri(self) -> None:
        if not settings.hub_base_url:
            raise ValueError("HUB_BASE_URL is required for source reachability check.")
        if not self.pc.api_url:
            raise ValueError("PC api_url is required for source reachability check.")

        test_name = f"hub-reachability-{uuid.uuid4().hex[:8]}"
        source_uri = f"{settings.hub_base_url.rstrip('/')}/reachability"
        payload = {
            "metadata": {"kind": "image"},
            "spec": {
                "name": test_name,
                "resources": {"image_type": "ISO_IMAGE", "source_uri": source_uri},
            },
        }

        auth = (self.pc.username, self.pc.password)
        with httpx.Client(verify=False, timeout=120, auth=auth) as client:
            response = client.post(
                f"{self.pc.api_url}/api/nutanix/v3/images", json=payload
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    "PC hub reachability check failed: "
                    f"{response.status_code} {response.text}"
                )
            body = response.json()
            task_uuid = self._extract_task_uuid(body)
            if task_uuid:
                task = self.wait_for_task(task_uuid)
                if not isinstance(task, dict):
                    raise RuntimeError(
                        f"Unexpected task payload: {task}"
                    )
                state = task.get("status", {}).get("state", "").upper()
                if state != "SUCCEEDED":
                    raise RuntimeError(
                        "PC hub reachability check failed: "
                        f"task state {state}"
                    )

    def import_image(self, image: Image) -> dict:
        if not self.pc.username or not self.pc.password:
            raise ValueError("PC credentials are required for import.")
        if not self.pc.api_url:
            raise ValueError("PC api_url is required for import.")

        if not settings.hub_base_url:
            raise ValueError("HUB_BASE_URL is required to publish images.")

        filename = os.path.basename(image.storage_uri)
        image_type = "DISK_IMAGE"
        if filename.lower().endswith(".iso"):
            image_type = "ISO_IMAGE"

        source_uri = (
            f"{settings.hub_base_url.rstrip('/')}/images/{image.id}/download"
        )
        payload = {
            "metadata": {"kind": "image"},
            "spec": {
                "name": image.name,
                "resources": {"image_type": image_type, "source_uri": source_uri},
            },
        }

        auth = (self.pc.username, self.pc.password)
        with httpx.Client(verify=False, timeout=120, auth=auth) as client:
            response = client.post(
                f"{self.pc.api_url}/api/nutanix/v3/images", json=payload
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"PC image import failed: {response.status_code} {response.text}"
                )
            try:
                body = response.json()
            except ValueError:
                body = response.text
            task_uuid = self._extract_task_uuid(body) if isinstance(body, dict) else None
            task = None
            if task_uuid:
                task = self.wait_for_task(task_uuid)
            return {
                "status_code": response.status_code,
                "body": body,
                "task_uuid": task_uuid,
                "task": task,
            }
