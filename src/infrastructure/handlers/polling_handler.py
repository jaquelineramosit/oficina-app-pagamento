import logging

from src.application.use_cases.check_payment_status import CheckPaymentStatusUseCase
from src.domain.exceptions import OrderNotFoundError, PaymentGatewayError
from src.infrastructure.adapters.dynamodb_order_repository import DynamoDBOrderRepository
from src.infrastructure.adapters.mercado_pago_gateway import MercadoPagoGateway
from src.infrastructure.adapters.sqs_payment_status_notifier import SQSPaymentStatusNotifier
from src.infrastructure.config import settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Instanciados no escopo do módulo (fora do handler) para serem reaproveitados
# entre invocações "warm" da mesma execution environment da lambda.
_payment_gateway = MercadoPagoGateway()
_order_repository = DynamoDBOrderRepository()
_payment_status_notifier = SQSPaymentStatusNotifier()
_use_case = CheckPaymentStatusUseCase(
    _payment_gateway,
    _order_repository,
    _payment_status_notifier,
    order_expiration_minutes=settings.ORDER_EXPIRATION_MINUTES,
)


def lambda_handler(event, context):
    """
    Entry point acionado periodicamente pelo EventBridge (ver
    terraform/eventbridge.tf), no lugar do antigo webhook: busca no
    DynamoDB as orders com status 'efetuado' (aguardando confirmação de
    pagamento) e, para cada uma, consulta GET /v1/orders/{id} no Mercado
    Pago para saber se o Pix já foi processado.
    """
    settings.validate()

    pending_orders = _order_repository.list_pending_orders()

    logger.info("Orders pendentes para verificação | total=%s", len(pending_orders))

    results = []

    for order in pending_orders:
        try:
            result = _use_case.execute(order.id)
            results.append(result)

        except OrderNotFoundError as exc:
            logger.error(
                "Order não encontrada no Mercado Pago | order_id=%s | erro=%s", order.id, exc
            )

        except PaymentGatewayError as exc:
            logger.error(
                "Erro ao consultar Mercado Pago | order_id=%s | erro=%s", order.id, exc
            )

        except Exception:  # noqa: BLE001
            logger.exception("Erro inesperado ao verificar order | order_id=%s", order.id)

    return {"orders_verificadas": len(results)}
