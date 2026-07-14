import logging
from typing import Optional

from src.application.ports.order_repository_port import OrderRepositoryPort
from src.application.ports.payment_gateway_port import PaymentGatewayPort
from src.application.ports.payment_status_notifier_port import PaymentStatusNotifierPort
from src.domain.entities import Order
from src.domain.exceptions import DomainValidationError
from src.domain.payment_status import PaymentStatus

logger = logging.getLogger(__name__)

# Tópicos que esta lambda sabe processar. Outros tópicos (ex.: "payment",
# "merchant_order") são confirmados (200) mas ignorados, para o Mercado
# Pago não ficar reenviando.
SUPPORTED_TOPICS = {"order"}

# Status/status_detail da Orders API do Mercado Pago que indicam que o
# pagamento foi efetivamente confirmado (pago). Ajuste/complemente aqui se
# identificar outras combinações nos seus testes de homologação — hoje
# cobre o caminho documentado pelo Mercado Pago para Pix via Orders API.
_PAID_STATUS = "processed"
_PAID_STATUS_DETAIL = "accredited"


class ProcessOrderWebhookUseCase:
    """
    Caso de uso: recebe a notificação (webhook) do Mercado Pago para o
    tópico 'order', busca o recurso completo (GET /v1/orders/{id}) e
    atualiza o status do pedido no repositório local.

    Segue o fluxo recomendado pela documentação do Mercado Pago: a
    notificação webhook é apenas um "aviso" — o dado confiável é sempre
    buscado na API logo em seguida.
    """

    def __init__(
        self,
        payment_gateway: PaymentGatewayPort,
        order_repository: OrderRepositoryPort,
        payment_status_notifier: PaymentStatusNotifierPort,
    ):
        self._payment_gateway = payment_gateway
        self._order_repository = order_repository
        self._payment_status_notifier = payment_status_notifier

    def execute(self, webhook_payload: dict) -> Optional[dict]:
        topic = self._extract_topic(webhook_payload)

        if topic not in SUPPORTED_TOPICS:
            logger.info(
                "Notificação ignorada | topic/type=%s (não tratado por esta lambda)",
                topic,
            )
            return None

        order_id = self._extract_order_id(webhook_payload)
        if not order_id:
            raise DomainValidationError(
                "Não foi possível extrair 'data.id' da notificação recebida."
            )

        logger.info("Notificação de order recebida | order_id=%s", order_id)

        order = self._payment_gateway.get_order(order_id)

        self._order_repository.update_order_status(order)

        logger.info(
            "Order atualizada a partir do webhook | order_id=%s | status=%s/%s",
            order.id,
            order.status,
            order.status_detail,
        )

        if self._is_paid(order):
            # Publica em 'sqs-pagamento-efetuado' avisando que o pagamento
            # foi confirmado (mesma fila usada pela criação bem-sucedida da
            # order, já que o domínio só distingue efetuado/recusado).
            self._payment_status_notifier.notify(order, PaymentStatus.PAGO)
        else:
            logger.info(
                "Order %s ainda não está confirmada como paga (status=%s/%s) "
                "— nada foi publicado.",
                order.id,
                order.status,
                order.status_detail,
            )

        return {
            "order_id": order.id,
            "status": order.status,
            "status_detail": order.status_detail,
        }

    @staticmethod
    def _is_paid(order: Order) -> bool:
        return order.status == _PAID_STATUS and order.status_detail == _PAID_STATUS_DETAIL

    @staticmethod
    def _extract_topic(payload: dict) -> Optional[str]:
        # O Mercado Pago costuma enviar o tópico no campo "type" do corpo.
        # Alguns fluxos legados usam "topic" como query string; aceitamos
        # ambos por robustez.
        return payload.get("type") or payload.get("topic")

    @staticmethod
    def _extract_order_id(payload: dict) -> Optional[str]:
        data = payload.get("data") or {}
        return data.get("id") or payload.get("resource")
