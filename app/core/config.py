from pathlib import Path

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
    database_url: str
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")


settings = Settings()
