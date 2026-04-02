"""Alembic environment configuration."""

from logging.config import fileConfig

from dotenv import load_dotenv
from alembic import context
from langrove.settings import Settings

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Load URL from Settings (reads LANGROVE_DATABASE_URL / .env automatically)
url = Settings().database_url


def _sync_url(url: str) -> str:
    """Convert any postgres URL to psycopg (sync) URL for Alembic."""
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    url = url.replace("postgres+asyncpg://", "postgresql+psycopg://")
    # Plain postgresql:// defaults to psycopg2; force psycopg3
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(url), target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(_sync_url(url))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
