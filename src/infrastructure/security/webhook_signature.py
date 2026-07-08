import hashlib
import hmac
import logging
from typing import Optional

from src.domain.exceptions import WebhookSignatureError

logger = logging.getLogger(__name__)


def validate_webhook_signature(
    x_signature_header: Optional[str],
    x_request_id_header: Optional[str],
    data_id: Optional[str],
    secret: str,
) -> None:
    """
    Valida a assinatura HMAC-SHA256 enviada pelo Mercado Pago no header
    'x-signature', conforme a documentação oficial de segurança de Webhooks.

    Formato do header:  "ts=1704908010,v1=618536f...c6fb7"
    Manifest assinado:  "id:{data_id};request-id:{x_request_id};ts:{ts};"

    Importante: o 'data_id' usado no manifest deve estar em minúsculas
    (é assim que o Mercado Pago o utiliza ao gerar a assinatura).

    Se 'secret' estiver vazio, a validação é ignorada (útil apenas em
    desenvolvimento) — um aviso é logado nesse caso. Em produção, configure
    sempre MP_WEBHOOK_SECRET com o valor exibido no painel de Webhooks.
    """
    if not secret:
        logger.warning(
            "MP_WEBHOOK_SECRET não configurado — validação de assinatura "
            "foi pulada. NÃO faça isso em produção."
        )
        return

    if not x_signature_header:
        raise WebhookSignatureError("Header 'x-signature' ausente na requisição.")

    parts = dict(
        item.strip().split("=", 1) for item in x_signature_header.split(",") if "=" in item
    )
    ts = parts.get("ts")
    received_hash = parts.get("v1")

    if not ts or not received_hash:
        raise WebhookSignatureError("Header 'x-signature' malformado.")

    manifest = f"id:{data_id};request-id:{x_request_id_header};ts:{ts};"

    computed_hash = hmac.new(
        key=secret.encode("utf-8"),
        msg=manifest.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise WebhookSignatureError("Assinatura do webhook inválida.")
