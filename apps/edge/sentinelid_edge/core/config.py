import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)

    PROJECT_NAME: str = "SentinelID Edge"
    API_V1_STR: str = "/api/v1"
    EDGE_ENV: str = os.getenv("EDGE_ENV", "dev")
    EDGE_HOST: str = os.getenv("EDGE_HOST", "127.0.0.1")
    EDGE_PORT: int = int(os.getenv("EDGE_PORT", "8787"))
    EDGE_AUTH_TOKEN: str = os.getenv("EDGE_AUTH_TOKEN", "devtoken")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ALLOW_FALLBACK_EMBEDDINGS: bool = (
        os.getenv("ALLOW_FALLBACK_EMBEDDINGS", "0").strip().lower() in {"1", "true", "yes"}
    )

    # Telemetry configuration
    TELEMETRY_ENABLED: bool = os.getenv("TELEMETRY_ENABLED", "false").lower() == "true"
    CLOUD_INGEST_URL: str = os.getenv("CLOUD_INGEST_URL", "http://localhost:8000/v1/ingest/events")
    TELEMETRY_BATCH_SIZE: int = int(os.getenv("TELEMETRY_BATCH_SIZE", "10"))
    TELEMETRY_MAX_RETRIES: int = int(os.getenv("TELEMETRY_MAX_RETRIES", "3"))
    TELEMETRY_EXPORT_INTERVAL_SECONDS: float = float(
        os.getenv("TELEMETRY_EXPORT_INTERVAL_SECONDS", "1.5")
    )
    TELEMETRY_SIGNAL_QUEUE_SIZE: int = int(os.getenv("TELEMETRY_SIGNAL_QUEUE_SIZE", "256"))
    TELEMETRY_HTTP_TIMEOUT_SECONDS: float = float(
        os.getenv("TELEMETRY_HTTP_TIMEOUT_SECONDS", "10.0")
    )

    # Storage paths
    DB_PATH: str = os.getenv("SENTINELID_DB_PATH", ".sentinelid/audit.db")
    KEYCHAIN_DIR: str = os.getenv("SENTINELID_KEYCHAIN_DIR", ".sentinelid/keys")

    # Input hardening
    MAX_REQUEST_BODY_BYTES: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(2 * 1024 * 1024)))  # 2 MB
    REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15.0"))
    MAX_FRAMES_PER_SESSION: int = int(os.getenv("MAX_FRAMES_PER_SESSION", "1200"))
    MAX_SESSION_LIFETIME_SECONDS: int = int(os.getenv("MAX_SESSION_LIFETIME_SECONDS", "120"))
    FRAME_PROCESSING_MAX_FPS: float = float(os.getenv("FRAME_PROCESSING_MAX_FPS", "10.0"))
    FRAME_CONTROLLER_STATE_TTL_SECONDS: int = int(
        os.getenv("FRAME_CONTROLLER_STATE_TTL_SECONDS", "180")
    )

    # Risk scoring thresholds (v0.7)
    # risk < R1: allow (if liveness passed)
    # R1 <= risk < R2: step-up required
    # risk >= R2: deny
    RISK_THRESHOLD_R1: float = float(os.getenv("RISK_THRESHOLD_R1", "0.45"))
    RISK_THRESHOLD_R2: float = float(os.getenv("RISK_THRESHOLD_R2", "0.75"))

    # Step-up limits
    MAX_STEP_UPS_PER_SESSION: int = int(os.getenv("MAX_STEP_UPS_PER_SESSION", "1"))

    # Verification threshold (v0.8)
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.50"))

    # Enrollment capture settings (v0.8)
    ENROLL_TARGET_FRAMES: int = int(os.getenv("ENROLL_TARGET_FRAMES", "8"))
    ENROLL_SESSION_TIMEOUT_SECONDS: int = int(
        os.getenv("ENROLL_SESSION_TIMEOUT_SECONDS", "180")
    )

    # Quality gates (v0.8)
    MIN_FACE_SIZE_PX: int = int(os.getenv("MIN_FACE_SIZE_PX", "80"))
    MIN_BLUR_VARIANCE: float = float(os.getenv("MIN_BLUR_VARIANCE", "60.0"))
    MIN_ILLUMINATION_MEAN: float = float(os.getenv("MIN_ILLUMINATION_MEAN", "40.0"))
    MAX_ILLUMINATION_MEAN: float = float(os.getenv("MAX_ILLUMINATION_MEAN", "225.0"))
    MAX_ABS_YAW_DEG: float = float(os.getenv("MAX_ABS_YAW_DEG", "25.0"))
    MAX_ABS_PITCH_DEG: float = float(os.getenv("MAX_ABS_PITCH_DEG", "25.0"))
    MAX_ABS_ROLL_DEG: float = float(os.getenv("MAX_ABS_ROLL_DEG", "25.0"))

    # Number of recent risk scores kept in memory for diagnostics
    RISK_SCORE_WINDOW_SIZE: int = int(os.getenv("RISK_SCORE_WINDOW_SIZE", "100"))

    # Perf window for p50/p95 diagnostics
    PERF_WINDOW_SIZE: int = int(os.getenv("PERF_WINDOW_SIZE", "300"))

settings = Settings()
