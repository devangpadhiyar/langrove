"""CLI entry points for Langrove."""

from __future__ import annotations

import logging
from pathlib import Path

import click


def _load_dotenv_from_config(config_path: str) -> None:
    """Parse langgraph.json and load the .env it specifies.

    Must be called before any langrove module is imported so that
    module-level Settings() singletons (e.g. in queue/celery_app.py)
    pick up the correct environment variables.

    Silently skips if the config file is absent or has no ``env`` field.
    """
    import json

    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv not installed — nothing to do

    path = Path(config_path)
    if not path.exists():
        return

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    env_field = data.get("env", ".env")
    if isinstance(env_field, str):
        env_path = path.parent / env_field
        load_dotenv(env_path, override=True)
    elif isinstance(env_field, dict):
        import os

        os.environ.update(env_field)


def _setup_logging(level: str = "INFO") -> None:
    """Configure root logging so all langrove loggers emit to stdout."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Keep noisy third-party loggers quiet
    for noisy in ("asyncio", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@click.group()
def main():
    """Langrove: Open-source LangGraph deployment server."""


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8123, type=int, help="Bind port")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.option(
    "--config",
    "config_path",
    default="langgraph.json",
    show_default=True,
    help="Path to langgraph.json config file.",
)
@click.option("--db-pool-min-size", default=None, type=int, help="Min DB connections (default: 2)")
@click.option(
    "--db-pool-max-size", default=None, type=int, help="Max DB connections (default: 10)"
)
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Log level (default: info)",
)
def serve(
    host: str,
    port: int,
    reload: bool,
    config_path: str,
    db_pool_min_size: int | None,
    db_pool_max_size: int | None,
    log_level: str,
):
    """Start the API server."""
    import os

    import uvicorn

    _load_dotenv_from_config(config_path)
    _setup_logging(log_level)

    if db_pool_min_size is not None:
        os.environ["LANGROVE_DB_POOL_MIN_SIZE"] = str(db_pool_min_size)
    if db_pool_max_size is not None:
        os.environ["LANGROVE_DB_POOL_MAX_SIZE"] = str(db_pool_max_size)

    uvicorn.run(
        "langrove.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level=log_level.lower(),
    )


@main.command()
@click.option("--worker-id", default=None, help="Unique worker identifier (logged at startup)")
@click.option(
    "--queues",
    "-Q",
    multiple=True,
    metavar="QUEUE",
    help=(
        "Queue name(s) to process.  Repeat the flag to listen on multiple queues: "
        "-Q langrove -Q priority.  Default: all registered queues."
    ),
)
@click.option(
    "--concurrency",
    "-t",
    default=None,
    type=int,
    help="Number of concurrent async tasks (default: 5).",
)
@click.option(
    "--max-retries",
    default=None,
    type=int,
    help="Max delivery attempts before a message is dead-lettered (default: 3).",
)
@click.option(
    "--task-timeout", default=None, type=int, help="Task timeout in seconds (default: 900)."
)
@click.option(
    "--shutdown-timeout",
    default=None,
    type=int,
    help="Graceful shutdown timeout in seconds (default: 30).",
)
@click.option(
    "--config",
    "config_path",
    default="langgraph.json",
    show_default=True,
    help="Path to langgraph.json config file.",
)
@click.option("--db-pool-min-size", default=None, type=int, help="Min DB connections (default: 2)")
@click.option(
    "--db-pool-max-size", default=None, type=int, help="Max DB connections (default: 10)"
)
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Log level (default: info)",
)
def worker(
    worker_id: str | None,
    queues: tuple[str, ...],
    concurrency: int | None,
    max_retries: int | None,
    task_timeout: int | None,
    shutdown_timeout: int | None,
    config_path: str,
    db_pool_min_size: int | None,
    db_pool_max_size: int | None,
    log_level: str,
):
    """Start a background run worker (Celery / AsyncIO pool)."""
    import os

    _load_dotenv_from_config(config_path)

    from langrove.worker import run_worker

    _setup_logging(log_level)

    # CLI flags override env vars (Settings reads from env at import time)
    if concurrency is not None:
        os.environ["LANGROVE_WORKER_CONCURRENCY"] = str(concurrency)
    if max_retries is not None:
        os.environ["LANGROVE_MAX_DELIVERY_ATTEMPTS"] = str(max_retries)
    if task_timeout is not None:
        os.environ["LANGROVE_TASK_TIMEOUT_SECONDS"] = str(task_timeout)
    if shutdown_timeout is not None:
        os.environ["LANGROVE_SHUTDOWN_TIMEOUT_SECONDS"] = str(shutdown_timeout)
    if db_pool_min_size is not None:
        os.environ["LANGROVE_DB_POOL_MIN_SIZE"] = str(db_pool_min_size)
    if db_pool_max_size is not None:
        os.environ["LANGROVE_DB_POOL_MAX_SIZE"] = str(db_pool_max_size)

    run_worker(worker_id, queues=list(queues) if queues else None)


@main.command()
@click.option(
    "--config",
    "config_path",
    default="langgraph.json",
    show_default=True,
    help="Path to langgraph.json config file.",
)
@click.option("--revision", default="head", show_default=True, help="Target revision.")
def migrate(config_path: str, revision: str):
    """Run database migrations (alembic upgrade)."""
    import sys

    _load_dotenv_from_config(config_path)
    _setup_logging()

    # Locate the migrations directory bundled with the package
    from pathlib import Path

    migrations_dir = Path(__file__).parent / "migrations"
    alembic_ini = Path(__file__).parent.parent.parent / "alembic.ini"
    if not alembic_ini.exists():
        # Fallback: look relative to cwd (editable install / dev mode)
        alembic_ini = Path("alembic.ini")

    if not alembic_ini.exists():
        click.echo(
            "ERROR: alembic.ini not found. Run this command from the project root.", err=True
        )
        sys.exit(1)

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(migrations_dir))

    try:
        command.upgrade(alembic_cfg, revision)
        click.echo(f"Migrations applied up to: {revision}")
    except Exception as exc:
        click.echo(f"ERROR: Migration failed — {exc}", err=True)
        sys.exit(1)


@main.command()
@click.option("--template", default="chatbot", help="Project template")
def init(template: str):
    """Initialize a new Langrove project."""
    import json
    from pathlib import Path

    config = {
        "graphs": {"agent": "./agent.py:graph"},
        "dependencies": [],
        "env": ".env",
    }

    config_path = Path("langgraph.json")
    if config_path.exists():
        click.echo("langgraph.json already exists. Skipping.")
        return

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    click.echo("Created langgraph.json")

    # Create a minimal agent.py if it doesn't exist
    agent_path = Path("agent.py")
    if not agent_path.exists():
        agent_path.write_text(
            '"""Minimal Langrove agent."""\n\n'
            "from typing import TypedDict\n\n"
            "from langgraph.graph import StateGraph\n\n\n"
            "class State(TypedDict):\n"
            "    messages: list[dict]\n\n\n"
            "def echo(state: State) -> dict:\n"
            '    last = state["messages"][-1]\n'
            '    return {"messages": [{"role": "assistant", "content": last["content"]}]}\n\n\n'
            "builder = StateGraph(State)\n"
            'builder.add_node("echo", echo)\n'
            'builder.set_entry_point("echo")\n'
            'builder.set_finish_point("echo")\n'
            "graph = builder.compile()\n"
        )
        click.echo("Created agent.py")

    click.echo("\nNext steps:")
    click.echo("  docker compose up -d postgres redis")
    click.echo("  uv run langrove migrate")
    click.echo("  uv run langrove serve")


if __name__ == "__main__":
    main()
