"""API endpoints for cron jobs."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from langrove.api.deps import authorize, get_db
from langrove.db.cron_repo import CronRepository
from langrove.db.pool import DatabasePool
from langrove.models.crons import Cron, CronCreate, CronSearchRequest, CronUpdate
from langrove.services.cron_service import CronService

router = APIRouter(tags=["crons"])


def _get_service(db: DatabasePool = Depends(get_db)) -> CronService:
    return CronService(CronRepository(db))


@router.post("/runs/crons", response_model=Cron)
async def create_cron(
    request: Request,
    body: CronCreate,
    service: CronService = Depends(_get_service),
):
    await authorize(request, "crons", "create", body.model_dump(exclude_none=True))
    return await service.create(body)


@router.post("/threads/{thread_id}/runs/crons", response_model=Cron)
async def create_thread_cron(
    request: Request,
    thread_id: UUID,
    body: CronCreate,
    service: CronService = Depends(_get_service),
):
    await authorize(request, "crons", "create", body.model_dump(exclude_none=True))
    return await service.create(body, thread_id=thread_id)


@router.patch("/runs/crons/{cron_id}", response_model=Cron)
async def update_cron(
    request: Request,
    cron_id: UUID,
    body: CronUpdate,
    service: CronService = Depends(_get_service),
):
    await authorize(request, "crons", "update", {"cron_id": str(cron_id)})
    return await service.update(cron_id, body)


@router.delete("/runs/crons/{cron_id}", status_code=204)
async def delete_cron(
    request: Request,
    cron_id: UUID,
    service: CronService = Depends(_get_service),
):
    await authorize(request, "crons", "delete", {"cron_id": str(cron_id)})
    await service.delete(cron_id)
    return Response(status_code=204)


@router.post("/runs/crons/search", response_model=list[Cron])
async def search_crons(
    request: Request,
    body: CronSearchRequest,
    service: CronService = Depends(_get_service),
):
    await authorize(request, "crons", "search", body.model_dump(exclude_none=True))
    return await service.search(body)
