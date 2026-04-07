"""API endpoints for assistants (LangGraph SDK compatible)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from langrove.api.deps import authorize, authorize_read, get_db, get_graph_registry
from langrove.db.assistant_repo import AssistantRepository
from langrove.db.pool import DatabasePool
from langrove.graph.registry import GraphRegistry
from langrove.models.assistants import (
    AgentSchemas,
    Assistant,
    AssistantCreate,
    AssistantSearchRequest,
    AssistantUpdate,
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
    request: Request,
    body: AssistantCreate,
    service: AssistantService = Depends(_get_service),
):
    value = await authorize(request, "assistants", "create", body.model_dump(exclude_none=True))
    if isinstance(value, dict) and "metadata" in value:
        body = AssistantCreate(
            **{
                **body.model_dump(exclude_none=True),
                "metadata": value.get("metadata", body.metadata),
            }
        )
    return await service.create(body)


@router.get("/{assistant_id}", response_model=Assistant)
async def get_assistant(
    request: Request,
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    assistant = await service.get(assistant_id)
    await authorize_read(request, "assistants", assistant.metadata)
    return assistant


@router.patch("/{assistant_id}", response_model=Assistant)
async def update_assistant(
    request: Request,
    assistant_id: UUID,
    body: AssistantUpdate,
    service: AssistantService = Depends(_get_service),
):
    await authorize(
        request,
        "assistants",
        "update",
        {"assistant_id": str(assistant_id), "metadata": body.metadata},
    )
    return await service.update(assistant_id, body)


@router.delete("/{assistant_id}", status_code=204)
async def delete_assistant(
    request: Request,
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    await authorize(request, "assistants", "delete", {"assistant_id": str(assistant_id)})
    await service.delete(assistant_id)
    return Response(status_code=204)


@router.post("/search", response_model=list[Assistant])
async def search_assistants(
    request: Request,
    body: AssistantSearchRequest,
    service: AssistantService = Depends(_get_service),
):
    filters = await authorize(request, "assistants", "search", body.model_dump(exclude_none=True))
    if isinstance(filters, dict) and filters != body.model_dump(exclude_none=True):
        body_dict = body.model_dump(exclude_none=True)
        body_dict.setdefault("metadata", {}).update(filters)
        body = AssistantSearchRequest(**body_dict)
    return await service.search(body)


@router.get("/{assistant_id}/schemas", response_model=AgentSchemas)
async def get_assistant_schemas(
    request: Request,
    assistant_id: UUID,
    service: AssistantService = Depends(_get_service),
):
    assistant = await service.get(assistant_id)
    await authorize_read(request, "assistants", assistant.metadata)
    return await service.get_schemas(assistant_id)
