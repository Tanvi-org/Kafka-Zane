import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class PostgresService:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10)
        logger.info("postgres_connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def fetch_tenant_for_installation(self, installation_id: int) -> UUID | None:
        assert self._pool is not None
        row = await self._pool.fetchrow(
            "SELECT tenant_id FROM github_installations WHERE installation_id = $1",
            installation_id,
        )
        if not row:
            return None
        return row["tenant_id"]
