"""CLI entry points for Langrove."""

from __future__ import annotations

import logging

import click


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
    db_pool_min_size: int | None,
    db_pool_max_size: int | None,
    log_level: str,
):
    """Start the API server."""
    import os

    import uvicorn

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
    db_pool_min_size: int | None,
    db_pool_max_size: int | None,
    log_level: str,
):
    """Start a background run worker (Celery / AsyncIO pool)."""
    import os

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
    click.echo("  uv run langrove serve")


if __name__ == "__main__":
    main()
