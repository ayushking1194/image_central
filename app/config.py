from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "sqlite:///./image_hub.db"

    storage_backend: str = "local"
    local_storage_path: str = "./data/images"

    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    s3_endpoint_url: Optional[str] = None
    s3_access_key_id: Optional[str] = None
    s3_secret_access_key: Optional[str] = None

    pc_default_username: Optional[str] = None
    pc_default_password: Optional[str] = None
    pc_validate_connection: bool = True
    pc_validate_hub_source: bool = True
    hub_base_url: str = "http://localhost:8000"

    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
