import logging
import uuid

from src.application.ports.order_repository_port import OrderRepositoryPort
from src.application.ports.payment_gateway_port import PaymentGatewayPort
from src.application.ports.payment_status_notifier_port import PaymentStatusNotifierPort
from src.domain.entities import OrderRequest
from src.domain.payment_status import PaymentStatus

logger = logging.getLogger(__name__)


class CreatePaymentOrderUseCase:
    """
    Caso de uso: recebe o payload de solicitação de pagamento (vindo da fila
    SQS 'sqs-solicitar-pagamento'), valida todos os campos obrigatórios, cria
    a Order no Mercado Pago, persiste o resultado e publica o status
    'solicitado-pix' na fila 'sqs-retorno-pagamento'.

    Esta classe não sabe nada sobre SQS, HTTP ou DynamoDB — apenas orquestra
    o domínio através das portas (interfaces) injetadas.
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

    def execute(self, raw_payload: dict) -> dict:
        # 1) Validação de domínio - todos os campos são obrigatórios
        order_request = OrderRequest.from_dict(raw_payload)

        # 2) Idempotência - obrigatória pela API de Orders do Mercado Pago.
        #    A chave é DETERMINÍSTICA, derivada do external_reference (que é
        #    único por pedido). Isso é importante porque esta mensagem pode
        #    ser reprocessada pelo SQS mesmo depois da order já ter sido
        #    criada com sucesso (ex.: falha ao publicar na fila de retorno,
        #    no passo 5). Com uma chave fixa por external_reference, o
        #    Mercado Pago reconhece a repetição e devolve a MESMA order já
        #    criada, em vez de gerar uma order duplicada.
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_OID, order_request.external_reference))

        logger.info(
            "Criando order no Mercado Pago | external_reference=%s | idempotency_key=%s",
            order_request.external_reference,
            idempotency_key,
        )

        # 3) Chamada ao gateway de pagamento (adapter de infraestrutura)
        order = self._payment_gateway.create_order(order_request, idempotency_key)

        # 4) Persistência do resultado no seu sistema
        self._order_repository.save_created_order(order)

        logger.info(
            "Order criada com sucesso | order_id=%s | status=%s/%s",
            order.id,
            order.status,
            order.status_detail,
        )

        # 5) Publica na fila 'sqs-retorno-pagamento' avisando que o Pix foi
        #    solicitado, incluindo o QR Code para quem for exibi-lo ao pagador.
        self._payment_status_notifier.notify(order, PaymentStatus.SOLICITADO_PIX)

        return {
            "order_id": order.id,
            "status": order.status,
            "status_detail": order.status_detail,
            "external_reference": order.external_reference,
        }
