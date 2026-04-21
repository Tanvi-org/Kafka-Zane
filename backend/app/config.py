from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    github_webhook_secret: str = "dev-secret-change-me"
    verify_github_signature: bool = True

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_github: str = "github-events"
    kafka_topic_dlq: str = "github-events-dlq"
    kafka_group_id: str = "impact-worker"

    redis_url: str = "redis://localhost:6379/0"

    database_url: str = "postgresql://app:app@localhost:5432/app"

    idempotency_ttl_seconds: int = 86400


@lru_cache
def get_settings() -> Settings:
    return Settings()
