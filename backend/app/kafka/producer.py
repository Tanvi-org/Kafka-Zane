import json
import logging

from aiokafka import AIOKafkaProducer

from app.config import Settings

logger = logging.getLogger(__name__)


class KafkaProducerService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await self._producer.start()
        logger.info(
            "kafka_producer_started bootstrap=%s",
            self._settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_github_event(self, envelope: dict) -> None:
        assert self._producer is not None
        inst = envelope.get("installation_id")
        pr = envelope.get("pr_number")
        key = f"{inst}:{pr}".encode("utf-8")
        await self._producer.send_and_wait(
            self._settings.kafka_topic_github,
            value=envelope,
            key=key,
        )

    async def send_dlq(self, envelope: dict, error: str) -> None:
        assert self._producer is not None
        dlq_payload = {**envelope, "dlq_error": error}
        await self._producer.send_and_wait(
            self._settings.kafka_topic_dlq,
            value=dlq_payload,
            key=str(envelope.get("delivery_id") or "").encode("utf-8"),
        )
