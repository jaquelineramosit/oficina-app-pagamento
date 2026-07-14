import json
from unittest.mock import MagicMock

from src.domain.entities import Order, PaymentResult
from src.domain.payment_status import PaymentStatus
from src.infrastructure.adapters.sqs_payment_status_notifier import SQSPaymentStatusNotifier

EFETUADO_QUEUE_URL = "https://sqs.fake/sqs-pagamento-efetuado"
RECUSADO_QUEUE_URL = "https://sqs.fake/sqs-pagamento-recusado"


def _order_with_pix_payment():
    payment = PaymentResult(
        id="PAY01",
        amount="10.00",
        status="action_required",
        status_detail="waiting_transfer",
        qr_code="00020126...AAB6",
        qr_code_base64="iVBORw0KGgo...",
        ticket_url="https://www.mercadopago.com.br/sandbox/payments/xxx/ticket",
        date_of_expiration="2026-07-07T18:10:11.873+00:00",
    )
    return Order(
        id="ORDTST01",
        external_reference="order_test_001",
        status="action_required",
        status_detail="waiting_transfer",
        total_amount="10.00",
        currency="BRL",
        payments=[payment],
    )


def _build_notifier(client):
    return SQSPaymentStatusNotifier(
        efetuado_queue_url=EFETUADO_QUEUE_URL,
        recusado_queue_url=RECUSADO_QUEUE_URL,
        client=client,
    )


def test_notify_sends_message_with_pix_data_when_efetuado():
    client = MagicMock()
    notifier = _build_notifier(client)

    notifier.notify(_order_with_pix_payment(), PaymentStatus.EFETUADO)

    client.send_message.assert_called_once()
    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"] == EFETUADO_QUEUE_URL

    body = json.loads(kwargs["MessageBody"])
    assert body["order_id"] == "ORDTST01"
    assert body["status"] == "efetuado"
    assert body["pix"]["qr_code"] == "00020126...AAB6"
    assert body["pix"]["ticket_url"].startswith("https://www.mercadopago.com.br")


def test_notify_sends_message_without_pix_data_when_pago():
    client = MagicMock()
    notifier = _build_notifier(client)

    order = _order_with_pix_payment()
    order.status = "processed"
    order.status_detail = "accredited"

    notifier.notify(order, PaymentStatus.PAGO)

    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"] == EFETUADO_QUEUE_URL

    body = json.loads(kwargs["MessageBody"])
    assert body["status"] == "pago"
    assert body["mercado_pago_status"] == "processed"
    assert "pix" not in body


def test_notify_sends_message_to_recusado_queue():
    client = MagicMock()
    notifier = _build_notifier(client)

    order = Order(id="order_test_001", external_reference="order_test_001", status="recusado")

    notifier.notify(order, PaymentStatus.RECUSADO)

    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"] == RECUSADO_QUEUE_URL

    body = json.loads(kwargs["MessageBody"])
    assert body["status"] == "recusado"
    assert "pix" not in body


def test_notify_skips_when_queue_url_is_not_configured():
    client = MagicMock()
    notifier = SQSPaymentStatusNotifier(efetuado_queue_url="", recusado_queue_url="", client=client)

    notifier.notify(_order_with_pix_payment(), PaymentStatus.EFETUADO)

    client.send_message.assert_not_called()
