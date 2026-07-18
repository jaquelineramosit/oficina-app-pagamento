import json
import logging
from datetime import datetime, timezone

import boto3

from src.application.ports.dead_letter_publisher_port import DeadLetterPublisherPort
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class SQSDeadLetterPublisher(DeadLetterPublisherPort):
    """
    Adapter de saída que publica mensagens rejeitadas (payload inválido,
    'DomainValidationError') diretamente na DLQ da fila
    'sqs-pagamento-solicitar' (sqs-pagamento-solicitar-dlq), sem esperar o
    ciclo normal de retry do SQS — reprocessar não corrige um payload
    malformado.
    """

    def __init__(self, queue_url: str = None, client=None):
        self._queue_url = queue_url or settings.SQS_PAGAMENTO_SOLICITAR_DLQ_URL
        self._client = client or boto3.client("sqs", region_name=settings.AWS_REGION)

    def publish(self, message_id: str, raw_body: str, error: str) -> None:
        if not self._queue_url:
            logger.warning(
                "DLQ de mensagens inválidas não configurada — a mensagem "
                "messageId=%s NÃO foi publicada na DLQ.",
                message_id,
            )
            return

        message = {
            "original_message_id": message_id,
            "error": error,
            "raw_body": raw_body,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Publicando mensagem rejeitada na DLQ %s | messageId=%s",
            self._queue_url,
            message_id,
        )

        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(message),
        )
