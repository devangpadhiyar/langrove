"""API endpoints for assistants (LangGraph SDK compatible)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from langrove.api.deps import get_db, get_graph_registry
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.graph.registry import GraphRegistry
from langrove.models.assistants import (
    Assistant,
    AssistantCreate,
    AssistantSearchRequest,
    AssistantUpdate,
    AgentSchemas,
)
from langrove.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistants", tags=["assistants"])


def _get_service(
    db: DatabasePool = Depends(get_db),
    registry: GraphRegistry = Depends(get_graph_registry),
) -> AssistantService:
    return AssistantService(AssistantRepository(db), registry)


@router.post("", response_model=Assistant)
async def create_assistant(
    body: AssistantCreate,
    service: AssistantService = Depends(_get_service),
):
    return await service.create(body)


@router.get("/{assistant_id}", response_model=Assistant)
async def get_assistant(
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    return await service.get(assistant_id)


@router.patch("/{assistant_id}", response_model=Assistant)
async def update_assistant(
    assistant_id: UUID,
    body: AssistantUpdate,
    service: AssistantService = Depends(_get_service),
):
    return await service.update(assistant_id, body)


@router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    await service.delete(assistant_id)
    return Response(status_code=204)


@router.post("/search", response_model=list[Assistant])
async def search_assistants(
    body: AssistantSearchRequest,
    service: AssistantService = Depends(_get_service),
):
    return await service.search(body)


@router.get("/{assistant_id}/schemas", response_model=AgentSchemas)
async def get_assistant_schemas(
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    return await service.get_schemas(assistant_id)
