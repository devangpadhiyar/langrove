"""Agent Protocol /agents/* endpoints.

Thin delegation layer -- all logic lives in AssistantService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from langrove.api.deps import get_db, get_graph_registry
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.graph.registry import GraphRegistry
from langrove.models.assistants import Agent, AgentSchemas, AssistantSearchRequest
from langrove.services.assistant_service import AssistantService

router = APIRouter(prefix="/agents", tags=["agents"])


def _get_service(
    db: DatabasePool = Depends(get_db),
    registry: GraphRegistry = Depends(get_graph_registry),
) -> AssistantService:
    return AssistantService(AssistantRepository(db), registry)


@router.post("/search", response_model=list[Agent])
async def search_agents(
    body: AssistantSearchRequest,
    service: AssistantService = Depends(_get_service),
):
    """Search available agents (Agent Protocol)."""
    assistants = await service.search(body)
    return [service.to_agent(a) for a in assistants]


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(
    agent_id: str,
    service: AssistantService = Depends(_get_service),
):
    """Get agent by ID (Agent Protocol)."""
    from uuid import UUID

    assistant = await service.get(UUID(agent_id))
    return service.to_agent(assistant)


@router.get("/{agent_id}/schemas", response_model=AgentSchemas)
async def get_agent_schemas(
    agent_id: str,
    service: AssistantService = Depends(_get_service),
):
    """Get agent schemas (Agent Protocol)."""
    from uuid import UUID

    return await service.get_schemas(UUID(agent_id))
