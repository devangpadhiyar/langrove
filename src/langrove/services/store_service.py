"""Business logic for the store."""

from __future__ import annotations

from langrove.db.store_repo import StoreRepository
from langrove.exceptions import NotFoundError
from langrove.models.store import (
    Item,
    NamespaceInfo,
    StoreDeleteRequest,
    StoreListNamespacesRequest,
    StorePutRequest,
    StoreSearchRequest,
)


class StoreService:
    """Manages store items -- CRUD and search."""

    def __init__(self, repo: StoreRepository):
        self._repo = repo

    async def put(self, req: StorePutRequest) -> None:
        """Create or update a store item."""
        await self._repo.put(req.namespace, req.key, req.value)

    async def get(self, namespace: list[str], key: str) -> Item:
        """Get a store item by namespace + key."""
        row = await self._repo.get(namespace, key)
        if row is None:
            raise NotFoundError("store_item", f"{'/'.join(namespace)}/{key}")
        return Item(
            namespace=row["namespace"],
            key=row["key"],
            value=row["value"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    async def delete(self, req: StoreDeleteRequest) -> None:
        """Delete a store item."""
        await self._repo.delete(req.namespace, req.key)

    async def search(self, req: StoreSearchRequest) -> list[Item]:
        """Search store items."""
        rows = await self._repo.search(
            namespace_prefix=req.namespace_prefix,
            filter=req.filter,
            limit=req.limit,
            offset=req.offset,
        )
        return [
            Item(
                namespace=r["namespace"],
                key=r["key"],
                value=r["value"],
                created_at=r.get("created_at"),
                updated_at=r.get("updated_at"),
            )
            for r in rows
        ]

    async def list_namespaces(self, req: StoreListNamespacesRequest) -> list[NamespaceInfo]:
        """List distinct namespaces."""
        namespaces = await self._repo.list_namespaces(
            prefix=req.prefix,
            suffix=req.suffix,
            max_depth=req.max_depth,
            limit=req.limit,
            offset=req.offset,
        )
        return [NamespaceInfo(path=ns) for ns in namespaces]
