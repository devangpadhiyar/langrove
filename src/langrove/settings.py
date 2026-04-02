"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Langrove server configuration."""

    # Database
    database_url: str = "postgresql://langrove:langrove@localhost:5432/langrove"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Server
    host: str = "0.0.0.0"
    port: int = 8123

    # Worker
    worker_id: str = "worker-1"
    recovery_interval_seconds: int = 30
    task_timeout_seconds: int = 60
    max_delivery_attempts: int = 3

    # Config file
    config_path: str = "langgraph.json"

    model_config = {"env_prefix": "LANGROVE_", "env_file": ".env", "extra": "ignore"}
