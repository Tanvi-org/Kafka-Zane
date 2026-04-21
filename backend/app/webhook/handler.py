import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_github_signature(body: bytes, signature_256: str | None, secret: str) -> None:
    if not signature_256 or not signature_256.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing_signature")
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    if not hmac.compare_digest(expected, signature_256):
        raise HTTPException(status_code=401, detail="bad_signature")


@router.post("")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
):
    settings = get_settings()
    body = await request.body()

    if settings.verify_github_signature:
        _verify_github_signature(body, x_hub_signature_256, settings.github_webhook_secret)

    payload = json.loads(body.decode("utf-8"))
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")

    producer = request.app.state.producer
    envelope = {
        "schema_version": 1,
        "event_name": x_github_event,
        "delivery_id": x_github_delivery,
        "installation_id": installation_id,
        "pr_number": pr_number,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    logger.info(
        "webhook_accepted installation_id=%s tenant_id=pending delivery_id=%s event=%s pr_number=%s",
        installation_id,
        x_github_delivery,
        x_github_event,
        pr_number,
    )

    await producer.send_github_event(envelope)
    return JSONResponse(status_code=202, content={"status": "accepted"})
