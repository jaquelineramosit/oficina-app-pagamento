import json
import logging

from src.application.use_cases.process_order_webhook import ProcessOrderWebhookUseCase
from src.domain.exceptions import (
    DomainValidationError,
    OrderNotFoundError,
    PaymentGatewayError,
    WebhookSignatureError,
)
from src.infrastructure.adapters.dynamodb_order_repository import DynamoDBOrderRepository
from src.infrastructure.adapters.mercado_pago_gateway import MercadoPagoGateway
from src.infrastructure.adapters.sqs_payment_status_notifier import SQSPaymentStatusNotifier
from src.infrastructure.config import settings
from src.infrastructure.security.webhook_signature import validate_webhook_signature

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_payment_gateway = MercadoPagoGateway()
_order_repository = DynamoDBOrderRepository()
_payment_status_notifier = SQSPaymentStatusNotifier()
_use_case = ProcessOrderWebhookUseCase(_payment_gateway, _order_repository, _payment_status_notifier)


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """
    Entry point acionado pelo API Gateway no endpoint
    POST /api/webhooks/mercadopago, configurado no painel do Mercado Pago
    com o tópico 'order' (Orders).

    Regras seguidas, conforme a documentação do Mercado Pago:
    - Responder 200/201 rapidamente (o MP reenvia se não houver resposta
      HTTP em até ~22s).
    - Validar a assinatura HMAC do header 'x-signature' quando
      MP_WEBHOOK_SECRET estiver configurado.
    - Buscar o recurso completo via GET /v1/orders/{id} usando o 'data.id'
      recebido na notificação, em vez de confiar apenas no corpo do webhook.
    """
    settings.validate()

    try:
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        query_params = event.get("queryStringParameters") or {}

        raw_body = event.get("body") or "{}"
        payload = json.loads(raw_body)

        data_id = (payload.get("data") or {}).get("id") or query_params.get("data.id")

        validate_webhook_signature(
            x_signature_header=headers.get("x-signature"),
            x_request_id_header=headers.get("x-request-id"),
            data_id=str(data_id).lower() if data_id else None,
            secret=settings.MP_WEBHOOK_SECRET,
        )

        result = _use_case.execute(payload)

        if result is None:
            # Tópico não tratado por esta lambda (ex.: 'payment'). Ainda assim
            # confirmamos o recebimento (200) para o MP não ficar reenviando.
            return _response(200, {"message": "Notificação recebida, tópico ignorado."})

        return _response(200, {"message": "Notificação processada com sucesso.", **result})

    except WebhookSignatureError as exc:
        logger.warning("Assinatura de webhook inválida: %s", exc)
        return _response(401, {"message": str(exc)})

    except DomainValidationError as exc:
        logger.error("Payload de webhook inválido: %s", exc)
        # Retornamos 200 para o MP não ficar reenviando indefinidamente uma
        # notificação malformada que nunca vai se tornar válida.
        return _response(200, {"message": f"Notificação ignorada: {exc}"})

    except OrderNotFoundError as exc:
        logger.error("Order não encontrada: %s", exc)
        return _response(200, {"message": str(exc)})

    except PaymentGatewayError as exc:
        logger.error("Erro ao consultar Mercado Pago: %s", exc)
        # 5xx aqui é proposital: sinaliza ao Mercado Pago que ele deve
        # reenviar a notificação mais tarde (erro temporário do nosso lado).
        return _response(502, {"message": "Erro temporário ao consultar o Mercado Pago."})

    except Exception:  # noqa: BLE001
        logger.exception("Erro inesperado ao processar webhook.")
        return _response(500, {"message": "Erro interno."})
