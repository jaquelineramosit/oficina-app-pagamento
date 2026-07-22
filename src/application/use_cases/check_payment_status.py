import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.application.ports.order_repository_port import OrderRepositoryPort
from src.application.ports.payment_gateway_port import PaymentGatewayPort
from src.application.ports.payment_status_notifier_port import PaymentStatusNotifierPort
from src.domain.entities import Order
from src.domain.payment_status import MercadoPagoOrderStatus, PaymentStatus

logger = logging.getLogger(__name__)

_PAID_STATUS = MercadoPagoOrderStatus.PROCESSED


class CheckPaymentStatusUseCase:
    """
    Caso de uso: consulta o status atual de uma order (GET
    /v1/orders/{id}) e atualiza o status do pedido no repositório local.

    Acionado pelo polling periódico (ver `polling_handler.py`), em vez de
    esperar uma notificação de webhook: aqui é a própria aplicação quem
    pergunta ao Mercado Pago "esse pagamento já foi processado?".

    Orders que não são confirmadas dentro de `order_expiration_minutes`
    (contados a partir de `Order.created_date`) são marcadas como
    `PaymentStatus.RECUSADO` e publicadas em 'sqs-pagamento-recusado' — a
    partir daí, `list_pending_orders()` para de devolvê-las e o polling
    para de verificá-las.
    """

    def __init__(
        self,
        payment_gateway: PaymentGatewayPort,
        order_repository: OrderRepositoryPort,
        payment_status_notifier: PaymentStatusNotifierPort,
        order_expiration_minutes: int = 10,
    ):
        self._payment_gateway = payment_gateway
        self._order_repository = order_repository
        self._payment_status_notifier = payment_status_notifier
        self._order_expiration_minutes = order_expiration_minutes

    def execute(self, order_id: str) -> dict:
        order = self._payment_gateway.get_order(order_id)

        if self._is_paid(order):
            self._order_repository.update_order_status(order)
            self._payment_status_notifier.notify(order, PaymentStatus.PAGO)
            logger.info("Order confirmada como paga via polling | order_id=%s", order.id)

        elif self._is_expired(order):
            order.status = PaymentStatus.RECUSADO
            order.status_detail = (
                f"Pix nao confirmado em {self._order_expiration_minutes} minuto(s) - expirado."
            )
            self._order_repository.update_order_status(order)
            self._payment_status_notifier.notify(order, PaymentStatus.RECUSADO)
            logger.info(
                "Order expirada sem confirmacao de pagamento | order_id=%s | limite=%s min",
                order.id,
                self._order_expiration_minutes,
            )

        else:
            self._order_repository.update_order_status(order)
            logger.info(
                "Order %s ainda não está confirmada como paga (status=%s) "
                "— nada foi publicado.",
                order.id,
                order.status,
            )

        return {
            "order_id": order.id,
            "status": order.status,
            "status_detail": order.status_detail,
        }

    @staticmethod
    def _is_paid(order: Order) -> bool:
        return order.status == _PAID_STATUS

    def _is_expired(self, order: Order) -> bool:
        created_at = self._parse_created_date(order.created_date)
        if created_at is None:
            return False
        age = datetime.now(timezone.utc) - created_at
        return age >= timedelta(minutes=self._order_expiration_minutes)

    @staticmethod
    def _parse_created_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
