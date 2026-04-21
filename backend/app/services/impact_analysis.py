import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def run_impact_analysis(tenant_id: UUID, payload: dict) -> None:
    """
    Replace this stub with your real impact analysis.
    All data access must be scoped by tenant_id (DB queries, object storage prefixes, etc.).
    """
    pr = payload.get("pull_request") or {}
    logger.info(
        "impact_analysis_done tenant_id=%s pr_number=%s title=%s",
        tenant_id,
        pr.get("number"),
        (pr.get("title") or "")[:80],
    )
