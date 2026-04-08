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

    # Database pool sizes (asyncpg)
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # Psycopg pool sizes (LangGraph checkpointer + store)
    checkpointer_pool_max_size: int = 5
    store_pool_max_size: int = 5

    # Worker
    worker_concurrency: int = 5
    task_timeout_seconds: int = 900
    max_delivery_attempts: int = 3
    shutdown_timeout_seconds: int = 30

    # Event stream cleanup
    event_stream_ttl_seconds: int = 86400

    # Config file
    config_path: str = "langgraph.json"

    model_config = {"env_prefix": "LANGROVE_", "env_file": ".env", "extra": "ignore"}
