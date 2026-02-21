import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SentinelID Edge"
    API_V1_STR: str = "/api/v1"
    EDGE_ENV: str = os.getenv("EDGE_ENV", "dev")
    EDGE_AUTH_TOKEN: str = os.getenv("EDGE_AUTH_TOKEN", "devtoken")

    # Telemetry configuration
    TELEMETRY_ENABLED: bool = os.getenv("TELEMETRY_ENABLED", "false").lower() == "true"
    CLOUD_INGEST_URL: str = os.getenv("CLOUD_INGEST_URL", "http://localhost:8000/v1/ingest/events")
    TELEMETRY_BATCH_SIZE: int = int(os.getenv("TELEMETRY_BATCH_SIZE", "10"))
    TELEMETRY_MAX_RETRIES: int = int(os.getenv("TELEMETRY_MAX_RETRIES", "3"))

    class Config:
        case_sensitive = True

settings = Settings()
