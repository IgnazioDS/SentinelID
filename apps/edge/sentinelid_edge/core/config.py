import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "SentinelID Edge"
    API_V1_STR: str = "/api/v1"
    EDGE_ENV: str = os.getenv("EDGE_ENV", "dev")
    EDGE_AUTH_TOKEN: str = os.getenv("EDGE_AUTH_TOKEN", "devtoken")

    class Config:
        case_sensitive = True

settings = Settings()
