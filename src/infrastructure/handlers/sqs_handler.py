import json
import logging

from src.application.use_cases.create_payment_order import CreatePaymentOrderUseCase
from src.domain.exceptions import DomainValidationError, PaymentGatewayError
from src.infrastructure.adapters.dynamodb_order_repository import DynamoDBOrderRepository
from src.infrastructure.adapters.mercado_pago_gateway import MercadoPagoGateway
from src.infrastructure.adapters.sqs_dead_letter_publisher import SQSDeadLetterPublisher
from src.infrastructure.adapters.sqs_payment_status_notifier import SQSPaymentStatusNotifier
from src.infrastructure.config import settings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Instanciados no escopo do módulo (fora do handler) para serem reaproveitados
# entre invocações "warm" da mesma execution environment da lambda.
_payment_gateway = MercadoPagoGateway()
_order_repository = DynamoDBOrderRepository()
_payment_status_notifier = SQSPaymentStatusNotifier()
_dead_letter_publisher = SQSDeadLetterPublisher()
_use_case = CreatePaymentOrderUseCase(_payment_gateway, _order_repository, _payment_status_notifier)


def lambda_handler(event, context):
    """
    Entry point acionado pela fila SQS 'sqs-pagamento-solicitar'.

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
            # Tanto "efetuado" quanto "recusado" são resultados de negócio
            # já persistidos/notificados pelo use case — nenhum dos dois
            # entra em batch_item_failures (não há o que reprocessar).
            logger.info(
                "Mensagem processada | messageId=%s | resultado=%s",
                message_id,
                result,
            )

        except DomainValidationError as exc:
            # Payload inválido (campo obrigatório ausente, tipo errado etc.).
            # Reprocessar não vai resolver, então NÃO marcamos como falha —
            # a mensagem é removida da fila 'sqs-pagamento-solicitar'. Para
            # não perdê-la de vez, publicamos o payload original + o motivo
            # do erro diretamente na DLQ dessa fila, para investigação manual.
            logger.error("Payload inválido | messageId=%s | erro=%s", message_id, exc)
            try:
                _dead_letter_publisher.publish(message_id, record["body"], str(exc))
            except Exception:
                # Se nem a publicação na DLQ funcionar, é melhor reprocessar
                # (retry) do que perder a mensagem por completo.
                logger.exception(
                    "Falha ao publicar payload inválido na DLQ | messageId=%s", message_id
                )
                batch_item_failures.append({"itemIdentifier": message_id})

        except PaymentGatewayError as exc:
            # Rede de segurança: no fluxo normal o use case já captura
            # PaymentGatewayError internamente (vira outcome "recusado",
            # persistido e publicado em 'sqs-pagamento-recusado'). Se mesmo
            # assim uma escapar (bug, uso direto do use case sem esse
            # tratamento, etc.), tratamos da mesma forma — resultado de
            # negócio definitivo — em vez de reprocessar indefinidamente.
            logger.error(
                "Erro no gateway de pagamento (fora do fluxo normal) | messageId=%s | erro=%s",
                message_id,
                exc,
            )
            try:
                result = _use_case.handle_gateway_error_as_recusado(body, exc)
                logger.info(
                    "Recusa registrada a partir de erro inesperado de gateway | "
                    "messageId=%s | resultado=%s",
                    message_id,
                    result,
                )
            except Exception:
                logger.exception(
                    "Falha ao registrar recusa para erro inesperado de gateway | messageId=%s",
                    message_id,
                )
                batch_item_failures.append({"itemIdentifier": message_id})

        except Exception:  # noqa: BLE001
            logger.exception("Erro inesperado ao processar mensagem | messageId=%s", message_id)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
