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
    Adapter de saída que publica o status do pagamento na fila
    'sqs-retorno-pagamento', para que outros sistemas/serviços consumam essa
    informação (ex.: atualizar o status do pedido no seu backend/e-commerce).
    """

    def __init__(self, queue_url: str = None, client=None):
        self._queue_url = queue_url or settings.RETORNO_PAGAMENTO_QUEUE_URL
        self._client = client or boto3.client("sqs", region_name=settings.AWS_REGION)

    def notify(self, order: Order, status: str) -> None:
        if not self._queue_url:
            logger.warning(
                "RETORNO_PAGAMENTO_QUEUE_URL não configurado — a mensagem de "
                "status '%s' NÃO foi publicada para a order %s.",
                status,
                order.id,
            )
            return

        message = self._build_message(order, status)

        logger.info(
            "Publicando status '%s' na fila sqs-retorno-pagamento | order_id=%s",
            status,
            order.id,
        )

        self._client.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(message),
        )

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
        # (solicitado-pix) — é o que a aplicação cliente precisa para exibir
        # a cobrança ao pagador.
        if status == PaymentStatus.SOLICITADO_PIX and first_payment:
            message["pix"] = {
                "payment_id": first_payment.id,
                "qr_code": first_payment.qr_code,
                "qr_code_base64": first_payment.qr_code_base64,
                "ticket_url": first_payment.ticket_url,
                "date_of_expiration": first_payment.date_of_expiration,
            }

        return message
