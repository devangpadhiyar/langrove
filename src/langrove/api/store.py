"""API endpoints for the store.

Uses LangGraph's AsyncPostgresStore (same store used by graph execution)
so that data written by agents via StoreBackend is accessible via the API.
Falls back to Langrove's own StoreRepository if the LangGraph store isn't available.
"""

from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from langrove.api.deps import get_db, get_store
from langrove.db.pool import DatabasePool
from langrove.db.store_repo import StoreRepository
from langrove.models.store import (
    Item,
    StoreDeleteRequest,
    StoreListNamespacesRequest,
    StorePutRequest,
    StoreSearchRequest,
)
from langrove.services.store_service import StoreService

router = APIRouter(prefix="/store", tags=["store"])
vfs_router = APIRouter(tags=["vfs"])


def _get_service(db: DatabasePool = Depends(get_db)) -> StoreService:
    return StoreService(StoreRepository(db))


@router.put("/items", status_code=204)
async def put_item(
    body: StorePutRequest,
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    if store is not None:
        await store.aput(tuple(body.namespace), body.key, body.value)
        return Response(status_code=204)
    await service.put(body)
    return Response(status_code=204)


@router.get("/items", response_model=Item)
async def get_item(
    key: str = Query(...),
    namespace: str = Query(default=""),
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    ns = namespace.split("/") if namespace else []

    if store is not None:
        item = await store.aget(tuple(ns), key)
        if item is None:
            from langrove.exceptions import NotFoundError

            raise NotFoundError("store_item", f"{namespace}/{key}")
        return Item(
            namespace=list(item.namespace) if hasattr(item, "namespace") else ns,
            key=item.key,
            value=item.value,
            created_at=getattr(item, "created_at", None),
            updated_at=getattr(item, "updated_at", None),
        )

    return await service.get(ns, key)


@router.delete("/items", status_code=204)
async def delete_item(
    body: StoreDeleteRequest,
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    if store is not None:
        await store.adelete(tuple(body.namespace), body.key)
        return Response(status_code=204)
    await service.delete(body)
    return Response(status_code=204)


@router.post("/items/search", response_model=dict)
async def search_items(
    body: StoreSearchRequest,
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    if store is not None:
        items = await store.asearch(
            tuple(body.namespace_prefix) if body.namespace_prefix else (),
            filter=body.filter,
            limit=body.limit,
            offset=body.offset,
        )
        return {
            "items": [
                {
                    "namespace": list(item.namespace) if hasattr(item, "namespace") else [],
                    "key": item.key,
                    "value": item.value,
                    "created_at": getattr(item, "created_at", None),
                    "updated_at": getattr(item, "updated_at", None),
                }
                for item in items
            ]
        }

    items = await service.search(body)
    return {"items": items}


@router.post("/namespaces", response_model=dict)
async def list_namespaces(
    body: StoreListNamespacesRequest,
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    if store is not None:
        namespaces = await store.alist_namespaces(
            prefix=tuple(body.prefix) if body.prefix else None,
            suffix=tuple(body.suffix) if body.suffix else None,
            max_depth=body.max_depth,
            limit=body.limit,
            offset=body.offset,
        )
        return {"namespaces": [{"path": list(ns)} for ns in namespaces]}

    namespaces = await service.list_namespaces(body)
    return {"namespaces": namespaces}


# ---------------------------------------------------------------------------
# VFS file-serving endpoint — serves raw files with proper MIME types
# so that multi-file Helios compositions work with relative imports.
# ---------------------------------------------------------------------------


@vfs_router.get("/vfs/{thread_id}/{file_path:path}")
async def serve_vfs_file(
    thread_id: str,
    file_path: str,
    store: Any = Depends(get_store),
    service: StoreService = Depends(_get_service),
):
    """Serve a VFS file as raw content with the correct MIME type.

    This enables multi-file Helios compositions where composition.html
    references src/main.js via relative imports. The browser resolves
    ``<script src="./src/main.js">`` against this endpoint.
    """
    key = f"/{file_path}" if not file_path.startswith("/") else file_path
    namespace = ("vfs", thread_id)

    # Fetch from LangGraph store or fallback repo
    item = None
    if store is not None:
        item = await store.aget(namespace, key)
    else:
        try:
            item = await service.get(list(namespace), key)
        except Exception:
            item = None

    if item is None:
        from langrove.exceptions import NotFoundError

        raise NotFoundError("vfs_file", f"{thread_id}/{file_path}")

    # Extract content from the stored JSONB value
    value = item.value if hasattr(item, "value") else item.get("value", {})
    content = value.get("content", "") if isinstance(value, dict) else str(value)
    if isinstance(content, list):
        content = "\n".join(content)

    # Determine MIME type from file extension
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "text/plain"

    # Rewrite bare npm package imports to esm.sh CDN URLs so browsers can
    # resolve them without a bundler (agents write bare specifiers like
    # `import { Helios } from '@helios-project/core'`).
    # Also rewrite problematic CDN URLs (skypack has CORS issues).
    if mime_type in ("text/javascript", "application/javascript", "text/html"):
        import re

        # Bare specifiers → esm.sh
        content = re.sub(
            r"""(from\s+['"])(@helios-project/[^'"]+)(['"])""",
            r"\1https://esm.sh/\2\3",
            content,
        )
        content = re.sub(
            r"""(from\s+['"])(gsap)(['"])""",
            r"\1https://esm.sh/\2\3",
            content,
        )
        # Skypack → esm.sh (skypack has CORS issues from iframes)
        content = re.sub(
            r"""https://cdn\.skypack\.dev/([^'"]+)""",
            r"https://esm.sh/\1",
            content,
        )

    return Response(
        content=content,
        media_type=mime_type,
        headers={"Cache-Control": "no-cache"},
    )
