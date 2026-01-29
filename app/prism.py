import os
import uuid

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
            return {"status_code": response.status_code, "body": body}
