import json
import logging

from src.application.use_cases.create_payment_order import CreatePaymentOrderUseCase
from src.domain.exceptions import DomainValidationError, PaymentGatewayError
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
_use_case = CreatePaymentOrderUseCase(_payment_gateway, _order_repository, _payment_status_notifier)


def lambda_handler(event, context):
    """
    Entry point acionado pela fila SQS 'sqs-solicitar-pagamento'.

    Implementa "partial batch response": se uma mensagem específica do lote
    falhar, apenas ela volta para a fila (ou eventualmente para a DLQ),
    sem afetar o processamento das demais mensagens do mesmo lote.

    Requer que o Event Source Mapping da fila tenha
    'FunctionResponseTypes: [ReportBatchItemFailures]' habilitado
    (já configurado no template.yaml).
    """
    settings.validate()

    batch_item_failures = []

    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            body = json.loads(record["body"])
            result = _use_case.execute(body)
            logger.info(
                "Mensagem processada com sucesso | messageId=%s | resultado=%s",
                message_id,
                result,
            )

        except DomainValidationError as exc:
            # Payload inválido (campo obrigatório ausente, tipo errado etc.).
            # Reprocessar não vai resolver, então NÃO marcamos como falha —
            # a mensagem é removida da fila. Fica registrado no CloudWatch
            # Logs para investigação; se preferir nunca perder a mensagem,
            # considere publicá-la também em uma fila/S3 de "mensagens
            # inválidas" antes de descartar.
            logger.error("Payload inválido | messageId=%s | erro=%s", message_id, exc)

        except PaymentGatewayError as exc:
            # Erro de comunicação/negócio no Mercado Pago (rede, 5xx, etc.):
            # vale a pena reprocessar, então marcamos como falha do lote.
            logger.error(
                "Erro no gateway de pagamento | messageId=%s | erro=%s", message_id, exc
            )
            batch_item_failures.append({"itemIdentifier": message_id})

        except Exception:  # noqa: BLE001
            logger.exception("Erro inesperado ao processar mensagem | messageId=%s", message_id)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
