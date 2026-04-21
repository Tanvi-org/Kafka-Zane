import logging
from uuid import UUID

from app.db.postgres import PostgresService
from app.db.redis_client import RedisService

logger = logging.getLogger(__name__)


class TenantResolver:
    def __init__(self, redis: RedisService, pg: PostgresService) -> None:
        self._redis = redis
        self._pg = pg

    async def resolve_tenant(self, installation_id: object) -> UUID | None:
        if installation_id is None:
            logger.warning("missing_installation_id")
            return None
        if not isinstance(installation_id, int):
            logger.warning("invalid_installation_id type=%s", type(installation_id))
            return None

        cached = await self._redis.get_tenant_id(installation_id)
        if cached:
            logger.info(
                "tenant_resolved_redis installation_id=%s tenant_id=%s",
                installation_id,
                cached,
            )
            return cached

        tenant_id = await self._pg.fetch_tenant_for_installation(installation_id)
        if tenant_id is None:
            logger.error("tenant_not_in_db installation_id=%s", installation_id)
            return None

        await self._redis.set_tenant_id(installation_id, tenant_id)
        logger.info(
            "tenant_resolved_db installation_id=%s tenant_id=%s",
            installation_id,
            tenant_id,
        )
        return tenant_id
