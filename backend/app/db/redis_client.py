import logging
from uuid import UUID

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._url, decode_responses=True)
        await self._client.ping()
        logger.info("redis_connected")

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @staticmethod
    def inst_key(installation_id: int) -> str:
        return f"inst:{installation_id}"

    async def get_tenant_id(self, installation_id: int) -> UUID | None:
        assert self._client is not None
        v = await self._client.get(self.inst_key(installation_id))
        if not v:
            return None
        return UUID(v)

    async def set_tenant_id(
        self,
        installation_id: int,
        tenant_id: UUID,
        ttl_seconds: int = 86400,
    ) -> None:
        assert self._client is not None
        await self._client.set(
            self.inst_key(installation_id),
            str(tenant_id),
            ex=ttl_seconds,
        )

    async def is_processed(self, key: str) -> bool:
        assert self._client is not None
        return await self._client.get(key) is not None

    async def mark_processed(self, key: str, ttl_seconds: int) -> None:
        assert self._client is not None
        await self._client.set(key, "1", ex=ttl_seconds)
