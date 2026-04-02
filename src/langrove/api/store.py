"""API endpoints for the store."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from langrove.api.deps import get_db
from langrove.db.pool import DatabasePool
from langrove.db.store_repo import StoreRepository
from langrove.models.store import (
    Item,
    NamespaceInfo,
    StoreDeleteRequest,
    StoreListNamespacesRequest,
    StorePutRequest,
    StoreSearchRequest,
)
from langrove.services.store_service import StoreService

router = APIRouter(prefix="/store", tags=["store"])


def _get_service(db: DatabasePool = Depends(get_db)) -> StoreService:
    return StoreService(StoreRepository(db))


@router.put("/items", status_code=204)
async def put_item(
    body: StorePutRequest,
    service: StoreService = Depends(_get_service),
):
    await service.put(body)
    return Response(status_code=204)


@router.get("/items", response_model=Item)
async def get_item(
    key: str = Query(...),
    namespace: str = Query(default=""),
    service: StoreService = Depends(_get_service),
):
    ns = namespace.split("/") if namespace else []
    return await service.get(ns, key)


@router.delete("/items", status_code=204)
async def delete_item(
    body: StoreDeleteRequest,
    service: StoreService = Depends(_get_service),
):
    await service.delete(body)
    return Response(status_code=204)


@router.post("/items/search", response_model=dict)
async def search_items(
    body: StoreSearchRequest,
    service: StoreService = Depends(_get_service),
):
    items = await service.search(body)
    return {"items": items}


@router.post("/namespaces", response_model=dict)
async def list_namespaces(
    body: StoreListNamespacesRequest,
    service: StoreService = Depends(_get_service),
):
    namespaces = await service.list_namespaces(body)
    return {"namespaces": namespaces}
