"""CLI entry points for Langrove."""

from __future__ import annotations

import click


@click.group()
def main():
    """Langrove: Open-source LangGraph deployment server."""


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8123, type=int, help="Bind port")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool):
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "langrove.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@main.command()
@click.option("--worker-id", default=None, help="Unique worker identifier")
def worker(worker_id: str | None):
    """Start a background run worker."""
    import asyncio

    from langrove.worker import run_worker

    asyncio.run(run_worker(worker_id))


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
            'builder = StateGraph(State)\n'
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
