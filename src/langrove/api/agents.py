"""Agent Protocol /agents/* endpoints.

Thin delegation layer -- all logic lives in AssistantService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from langrove.api.deps import authorize, authorize_read, get_db, get_graph_registry
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
    request: Request,
    body: AssistantSearchRequest,
    service: AssistantService = Depends(_get_service),
):
    """Search available agents (Agent Protocol)."""
    filters = await authorize(request, "assistants", "search", body.model_dump(exclude_none=True))
    if isinstance(filters, dict) and filters != body.model_dump(exclude_none=True):
        body_dict = body.model_dump(exclude_none=True)
        body_dict.setdefault("metadata", {}).update(filters)
        body = AssistantSearchRequest(**body_dict)
    assistants = await service.search(body)
    return [service.to_agent(a) for a in assistants]


@router.get("/{agent_id}", response_model=Agent)
async def get_agent(
    request: Request,
    agent_id: str,
    service: AssistantService = Depends(_get_service),
):
    """Get agent by ID (Agent Protocol)."""
    from uuid import UUID

    assistant = await service.get(UUID(agent_id))
    await authorize_read(request, "assistants", assistant.metadata)
    return service.to_agent(assistant)


@router.get("/{agent_id}/schemas", response_model=AgentSchemas)
async def get_agent_schemas(
    request: Request,
    agent_id: str,
    service: AssistantService = Depends(_get_service),
):
    """Get agent schemas (Agent Protocol)."""
    from uuid import UUID

    assistant = await service.get(UUID(agent_id))
    await authorize_read(request, "assistants", assistant.metadata)
    return await service.get_schemas(UUID(agent_id))
