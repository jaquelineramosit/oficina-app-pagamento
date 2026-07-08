from unittest.mock import MagicMock

import pytest

from src.application.use_cases.create_payment_order import CreatePaymentOrderUseCase
from src.domain.entities import Order
from src.domain.exceptions import DomainValidationError, PaymentGatewayError
from src.domain.payment_status import PaymentStatus

VALID_PAYLOAD = {
    "type": "online",
    "processing_mode": "automatic",
    "external_reference": "order_test_001",
    "total_amount": "10.00",
    "description": "Order Pix - teste",
    "payer": {"email": "test@testuser.com"},
    "transactions": {
        "payments": [
            {"amount": "10.00", "payment_method": {"type": "bank_transfer", "id": "pix"}}
        ]
    },
}


def _fake_order():
    return Order(
        id="ORDTST01",
        type="online",
        processing_mode="automatic",
        external_reference="order_test_001",
        description="Order Pix - teste",
        total_amount="10.00",
        status="action_required",
        status_detail="waiting_transfer",
    )


def _build_use_case():
    gateway = MagicMock()
    gateway.create_order.return_value = _fake_order()
    repository = MagicMock()
    notifier = MagicMock()
    return CreatePaymentOrderUseCase(gateway, repository, notifier), gateway, repository, notifier


def test_execute_calls_gateway_and_repository():
    use_case, gateway, repository, notifier = _build_use_case()

    result = use_case.execute(VALID_PAYLOAD)

    gateway.create_order.assert_called_once()
    repository.save_created_order.assert_called_once()
    assert result["order_id"] == "ORDTST01"
    assert result["status"] == "action_required"


def test_execute_publishes_solicitado_pix_status():
    use_case, gateway, repository, notifier = _build_use_case()

    use_case.execute(VALID_PAYLOAD)

    notifier.notify.assert_called_once()
    notified_order, notified_status = notifier.notify.call_args.args
    assert notified_order.id == "ORDTST01"
    assert notified_status == PaymentStatus.SOLICITADO_PIX


def test_same_external_reference_always_uses_the_same_idempotency_key():
    use_case, gateway, repository, notifier = _build_use_case()

    use_case.execute(VALID_PAYLOAD)
    use_case.execute(VALID_PAYLOAD)

    first_key = gateway.create_order.call_args_list[0].args[1]
    second_key = gateway.create_order.call_args_list[1].args[1]
    assert first_key == second_key  # mesma order (mesmo external_reference) -> mesma chave


def test_different_external_reference_uses_a_different_idempotency_key():
    use_case, gateway, repository, notifier = _build_use_case()

    other_payload = {**VALID_PAYLOAD, "external_reference": "order_test_002"}

    use_case.execute(VALID_PAYLOAD)
    use_case.execute(other_payload)

    first_key = gateway.create_order.call_args_list[0].args[1]
    second_key = gateway.create_order.call_args_list[1].args[1]
    assert first_key != second_key


def test_execute_raises_on_invalid_payload_without_calling_gateway():
    use_case, gateway, repository, notifier = _build_use_case()

    with pytest.raises(DomainValidationError):
        use_case.execute({})

    gateway.create_order.assert_not_called()
    repository.save_created_order.assert_not_called()
    notifier.notify.assert_not_called()


def test_execute_propagates_gateway_error_without_saving_or_notifying():
    use_case, gateway, repository, notifier = _build_use_case()
    gateway.create_order.side_effect = PaymentGatewayError("timeout")

    with pytest.raises(PaymentGatewayError):
        use_case.execute(VALID_PAYLOAD)

    repository.save_created_order.assert_not_called()
    notifier.notify.assert_not_called()
