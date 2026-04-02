"""Parse langgraph.json configuration file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from langrove.exceptions import ConfigError


class CorsConfig(BaseModel):
    """CORS configuration."""

    allow_origins: list[str] = ["*"]
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]
    allow_credentials: bool = False
    expose_headers: list[str] = []
    max_age: int = 600


class AuthConfig(BaseModel):
    """Authentication configuration."""

    path: str | None = None
    type: str | None = None  # "jwt", "api_key", or None for custom handler


class HttpConfig(BaseModel):
    """HTTP server customization."""

    app: str | None = None
    cors: CorsConfig = CorsConfig()
    mount_prefix: str = ""
    middleware_order: str = "middleware_first"
    disable_assistants: bool = False
    disable_threads: bool = False
    disable_runs: bool = False
    disable_store: bool = False
    disable_meta: bool = False
    disable_webhooks: bool = False


class GraphConfig(BaseModel):
    """Parsed langgraph.json configuration."""

    graphs: dict[str, str] = {}
    dependencies: list[str] = []
    env: str | dict[str, str] = ".env"
    python_version: str = "3.12"
    auth: AuthConfig = AuthConfig()
    http: HttpConfig = HttpConfig()

    # Raw config for passthrough
    raw: dict[str, Any] = {}


def load_config(config_path: str) -> GraphConfig:
    """Load and parse langgraph.json or aegra.json configuration.

    Tries langgraph.json first, then aegra.json as fallback.
    Returns default config if neither exists.
    """
    path = Path(config_path)

    # Try the specified path first
    if path.exists():
        return _parse_config(path)

    # Fallback: try langgraph.json in current directory
    for fallback in ["langgraph.json", "aegra.json"]:
        fallback_path = Path(fallback)
        if fallback_path.exists():
            return _parse_config(fallback_path)

    # No config file -- return defaults
    return GraphConfig()


def _parse_config(path: Path) -> GraphConfig:
    """Parse a config file into a GraphConfig."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e

    graphs = raw.get("graphs", {})
    if not isinstance(graphs, dict):
        raise ConfigError(f"'graphs' in {path} must be a dict mapping graph_id to module:attr")

    auth_raw = raw.get("auth", {})
    auth = AuthConfig(**auth_raw) if isinstance(auth_raw, dict) else AuthConfig()

    http_raw = raw.get("http", {})
    http = HttpConfig(**http_raw) if isinstance(http_raw, dict) else HttpConfig()

    return GraphConfig(
        graphs=graphs,
        dependencies=raw.get("dependencies", []),
        env=raw.get("env", ".env"),
        python_version=raw.get("python_version", "3.12"),
        auth=auth,
        http=http,
        raw=raw,
    )
