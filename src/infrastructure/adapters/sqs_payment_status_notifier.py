import json
import logging
from datetime import datetime, timezone

import boto3

from src.application.ports.payment_status_notifier_port import PaymentStatusNotifierPort
from src.domain.entities import Order
from src.domain.payment_status import PaymentStatus
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class SQSPaymentStatusNotifier(PaymentStatusNotifierPort):
    """
    Adapter de saída que publica o resultado do pagamento em
    'sqs-pagamento-efetuado' (sucesso/confirmação) ou 'sqs-pagamento-recusado'
    (falha no gateway), para que outros sistemas/serviços consumam essa
    informação (ex.: atualizar o status do pedido no seu backend/e-commerce).
    """

    def __init__(self, efetuado_queue_url: str = None, recusado_queue_url: str = None, client=None):
        self._efetuado_queue_url = efetuado_queue_url or settings.SQS_PAGAMENTO_EFETUADO_QUEUE_URL
        self._recusado_queue_url = recusado_queue_url or settings.SQS_PAGAMENTO_RECUSADO_QUEUE_URL
        self._client = client or boto3.client("sqs", region_name=settings.AWS_REGION)

    def notify(self, order: Order, status: str) -> None:
        queue_url = self._queue_url_for(status)

        if not queue_url:
            logger.warning(
                "Fila de destino para o status '%s' não configurada — a "
                "mensagem NÃO foi publicada para a order %s.",
                status,
                order.id,
            )
            return

        message = self._build_message(order, status)

        logger.info(
            "Publicando status '%s' na fila %s | order_id=%s",
            status,
            queue_url,
            order.id,
        )

        self._client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message),
        )

    def _queue_url_for(self, status: str) -> str:
        if status == PaymentStatus.RECUSADO:
            return self._recusado_queue_url
        return self._efetuado_queue_url

    @staticmethod
    def _build_message(order: Order, status: str) -> dict:
        first_payment = order.payments[0] if order.payments else None

        message = {
            "order_id": order.id,
            "external_reference": order.external_reference,
            "status": status,
            "mercado_pago_status": order.status,
            "mercado_pago_status_detail": order.status_detail,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "notified_at": datetime.now(timezone.utc).isoformat(),
        }

        # Os dados do QR Code Pix só fazem sentido na primeira mensagem
        # (efetuado) — é o que a aplicação cliente precisa para exibir a
        # cobrança ao pagador.
        if status == PaymentStatus.EFETUADO and first_payment:
            message["pix"] = {
                "payment_id": first_payment.id,
                "qr_code": first_payment.qr_code,
                "qr_code_base64": first_payment.qr_code_base64,
                "ticket_url": first_payment.ticket_url,
                "date_of_expiration": first_payment.date_of_expiration,
            }

        return message
