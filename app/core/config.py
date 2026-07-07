from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "messaging-platform"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = Field(..., description="Used to sign JWTs / internal tokens")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    API_KEY_HEADER: str = "X-API-Key"
    # Comma-separated list of valid static API keys (in production, back this with a DB table)
    VALID_API_KEYS: str = ""
    WEBHOOK_HMAC_SECRET: str = Field(..., description="Used to verify inbound provider webhook signatures")

    # --- CORS ---
    CORS_ORIGINS: str = "*"

    # --- Database ---
    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # --- Redis / Celery ---
    REDIS_URL: RedisDsn
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_TASK_MAX_RETRIES: int = 5
    CELERY_TASK_RETRY_BACKOFF: int = 5  # seconds, exponential base

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 120

    # --- Bulk import ---
    BULK_IMPORT_MAX_FILE_SIZE_MB: int = 25
    BULK_IMPORT_MAX_ROWS: int = 200_000
    BULK_IMPORT_BATCH_SIZE: int = 1000

    # --- Messaging / providers ---
    DEFAULT_MESSAGE_CHANNEL: Literal["sms", "email", "whatsapp"] = "sms"
    PROVIDER_NAME: Literal["mock", "twilio", "sendgrid"] = "mock"
    MESSAGE_SEND_MAX_RETRIES: int = 3
    MESSAGE_SEND_RETRY_BACKOFF: int = 10  # seconds

    # --- Notifications ---
    NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS: int = 5
    NOTIFICATION_MAX_RETRIES: int = 5

    @field_validator("CELERY_BROKER_URL", mode="after")
    @classmethod
    def default_broker(cls, v, info):
        return v or str(info.data.get("REDIS_URL"))

    @field_validator("CELERY_RESULT_BACKEND", mode="after")
    @classmethod
    def default_backend(cls, v, info):
        return v or str(info.data.get("REDIS_URL"))

    @property
    def cors_origin_list(self) -> list[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def valid_api_keys_set(self) -> set[str]:
        return {k.strip() for k in self.VALID_API_KEYS.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()