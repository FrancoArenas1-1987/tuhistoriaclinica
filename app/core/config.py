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
    database_url: str
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")


settings = Settings()
