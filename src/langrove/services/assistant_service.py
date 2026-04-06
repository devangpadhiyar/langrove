"""Business logic for assistants and agents."""

from __future__ import annotations

from uuid import UUID

from langrove.db.assistant_repo import AssistantRepository
from langrove.graph.registry import GraphRegistry
from langrove.models.assistants import (
    Agent,
    AgentSchemas,
    Assistant,
    AssistantCreate,
    AssistantSearchRequest,
    AssistantUpdate,
)


class AssistantService:
    """Manages assistant lifecycle and agent protocol compatibility."""

    def __init__(self, repo: AssistantRepository, registry: GraphRegistry):
        self._repo = repo
        self._registry = registry

    async def create(self, req: AssistantCreate) -> Assistant:
        """Create a new assistant."""
        if req.assistant_id and req.if_exists == "do_nothing":
            try:
                existing = await self._repo.get(req.assistant_id)
                return Assistant(**self._to_model(existing))
            except Exception:
                pass

        row = await self._repo.create(
            graph_id=req.graph_id,
            assistant_id=req.assistant_id,
            name=req.name,
            description=req.description,
            config=req.config,
            metadata=req.metadata,
        )
        return Assistant(**self._to_model(row))

    async def get(self, assistant_id: UUID) -> Assistant:
        """Get an assistant by ID."""
        row = await self._repo.get(assistant_id)
        return Assistant(**self._to_model(row))

    async def update(self, assistant_id: UUID, req: AssistantUpdate) -> Assistant:
        """Update an assistant."""
        fields = req.model_dump(exclude_none=True)
        row = await self._repo.update(assistant_id, **fields)
        return Assistant(**self._to_model(row))

    async def delete(self, assistant_id: UUID) -> None:
        """Delete an assistant."""
        await self._repo.delete(assistant_id)

    async def search(self, req: AssistantSearchRequest) -> list[Assistant]:
        """Search assistants."""
        rows = await self._repo.search(
            name=req.name,
            graph_id=req.graph_id,
            metadata=req.metadata,
            limit=req.limit,
            offset=req.offset,
        )
        return [Assistant(**self._to_model(r)) for r in rows]

    async def get_schemas(self, assistant_id: UUID) -> AgentSchemas:
        """Get input/output/state/config schemas for an assistant."""
        row = await self._repo.get(assistant_id)
        graph_id = row["graph_id"]

        try:
            info = self._registry.get(graph_id)
            return AgentSchemas(
                agent_id=str(assistant_id),
                input_schema=info.input_schema,
                output_schema=info.output_schema,
                state_schema=info.state_schema,
                config_schema=info.config_schema,
            )
        except Exception:
            return AgentSchemas(agent_id=str(assistant_id))

    def to_agent(self, assistant: Assistant) -> Agent:
        """Convert an Assistant to an Agent Protocol Agent."""
        return Agent(
            agent_id=str(assistant.assistant_id),
            name=assistant.name,
            description=assistant.description,
            metadata=assistant.metadata,
            capabilities={
                "ap.io.messages": True,
                "ap.io.streaming": True,
            },
        )

    async def auto_create_from_registry(self) -> None:
        """Auto-create assistants for all graphs in the registry."""
        for info in self._registry.list_graphs():
            existing = await self._repo.search(graph_id=info.graph_id, limit=1)
            if not existing:
                await self._repo.create(
                    graph_id=info.graph_id,
                    name=info.graph_id,
                )

    @staticmethod
    def _to_model(row: dict) -> dict:
        """Convert a DB row to model-compatible dict."""
        return {
            "assistant_id": row["assistant_id"],
            "graph_id": row["graph_id"],
            "name": row.get("name", ""),
            "description": row.get("description"),
            "config": row.get("config", {}),
            "metadata": row.get("metadata", {}),
            "version": row.get("version", 1),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
