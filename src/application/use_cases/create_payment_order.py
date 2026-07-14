import logging
import uuid

from src.application.ports.order_repository_port import OrderRepositoryPort
from src.application.ports.payment_gateway_port import PaymentGatewayPort
from src.application.ports.payment_status_notifier_port import PaymentStatusNotifierPort
from src.domain.entities import Order, OrderRequest
from src.domain.exceptions import PaymentGatewayError
from src.domain.payment_status import PaymentStatus

logger = logging.getLogger(__name__)


class CreatePaymentOrderUseCase:
    """
    Caso de uso: recebe o payload de solicitação de pagamento (vindo da fila
    SQS 'sqs-pagamento-solicitar'), valida todos os campos obrigatórios e
    tenta criar a Order no Mercado Pago. Em caso de sucesso, persiste o
    resultado e publica em 'sqs-pagamento-efetuado'; em caso de recusa do
    gateway, persiste a tentativa como recusada e publica em
    'sqs-pagamento-recusado'.

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
        #    criada com sucesso (ex.: falha ao publicar na fila de saída, no
        #    passo 5). Com uma chave fixa por external_reference, o Mercado
        #    Pago reconhece a repetição e devolve a MESMA order já criada,
        #    em vez de gerar uma order duplicada.
        idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_OID, order_request.external_reference))

        logger.info(
            "Criando order no Mercado Pago | external_reference=%s | idempotency_key=%s",
            order_request.external_reference,
            idempotency_key,
        )

        # 3) Chamada ao gateway de pagamento (adapter de infraestrutura).
        #    Uma recusa aqui (PaymentGatewayError) é um resultado de
        #    NEGÓCIO esperado — não propagamos para o handler, que trataria
        #    como falha de infraestrutura e reprocessaria a mensagem.
        try:
            order = self._payment_gateway.create_order(order_request, idempotency_key)
        except PaymentGatewayError as exc:
            return self._handle_recusado(order_request, exc)

        # 4) Persistência do resultado no seu sistema
        self._order_repository.save_created_order(order)

        logger.info(
            "Order criada com sucesso | order_id=%s | status=%s/%s",
            order.id,
            order.status,
            order.status_detail,
        )

        # 5) Publica em 'sqs-pagamento-efetuado' avisando que o Pix foi
        #    solicitado, incluindo o QR Code para quem for exibi-lo ao pagador.
        self._payment_status_notifier.notify(order, PaymentStatus.EFETUADO)

        return {
            "outcome": "efetuado",
            "order_id": order.id,
            "status": order.status,
            "status_detail": order.status_detail,
            "external_reference": order.external_reference,
        }

    def _handle_recusado(self, order_request: OrderRequest, exc: PaymentGatewayError) -> dict:
        logger.warning(
            "Gateway de pagamento recusou a order | external_reference=%s | erro=%s",
            order_request.external_reference,
            exc,
        )

        # Não existe uma Order real do Mercado Pago nesse cenário (o
        # gateway falhou antes de devolver uma) — persistimos um registro
        # mínimo usando o external_reference como chave, para manter
        # rastreabilidade da tentativa recusada.
        order = Order(
            id=order_request.external_reference,
            external_reference=order_request.external_reference,
            status="recusado",
            status_detail=str(exc),
            total_amount=str(order_request.total_amount),
            currency=None,
        )

        # Persistência e notificação ficam FORA do try/except do gateway:
        # se uma delas falhar (erro transitório de infra), a exceção deve
        # subir e a mensagem deve ser reprocessada, ao contrário da recusa
        # do gateway em si, que é definitiva.
        self._order_repository.save_created_order(order)
        self._payment_status_notifier.notify(order, PaymentStatus.RECUSADO)

        return {
            "outcome": "recusado",
            "external_reference": order_request.external_reference,
            "reason": str(exc),
        }
