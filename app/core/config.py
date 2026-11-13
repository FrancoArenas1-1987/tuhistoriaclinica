from pathlib import Path

from pydantic import EmailStr, Field, SecretStr
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TuHistoriaClinica.cl"
    environment: str = "dev"
    cookie_secure: bool = False
    secret_key: str
    access_token_expire_minutes: int = 480
    storage_dir: Path = Path(__file__).resolve().parents[2] / "storage"
    medical_order_quota_mb: int = 512
    registration_hour_limit: int = 5
    registration_day_limit: int = 20
    registration_site_hour_limit: int = 100
    registration_min_seconds: int = 2
    registration_token_seconds: int = 900
    patient_quota: int = 2000
    visit_quota: int = 20000
    appointment_quota: int = 20000
    medical_order_count_quota: int = 2000
    public_base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: EmailStr | None = None
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    password_reset_minutes: int = Field(default=15, ge=5, le=60)
    database_url: str
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")


settings = Settings()
