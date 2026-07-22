from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.application.use_cases.create_payment_order import CreatePaymentOrderUseCase
from src.domain.entities import Order
from src.domain.exceptions import PaymentGatewayError

scenarios("../features/criacao_pagamento.feature")


def _payload_valido(external_reference: str) -> dict:
    return {
        "type": "online",
        "processing_mode": "automatic",
        "external_reference": external_reference,
        "total_amount": "10.00",
        "description": "Order Pix - teste BDD",
        "payer": {"email": "test@testuser.com"},
        "transactions": {
            "payments": [
                {"amount": "10.00", "payment_method": {"type": "bank_transfer", "id": "pix"}}
            ]
        },
    }


@pytest.fixture
def contexto():
    return {}


@given(parsers.parse('uma solicitação de pagamento válida para o pedido "{external_reference}"'))
def dado_solicitacao_valida(contexto, external_reference):
    contexto["payload"] = _payload_valido(external_reference)
    contexto["gateway"] = MagicMock()
    contexto["repository"] = MagicMock()
    contexto["notifier"] = MagicMock()
    contexto["gateway"].create_order.return_value = Order(
        id=f"ORD-{external_reference}",
        external_reference=external_reference,
        status="action_required",
        status_detail="waiting_transfer",
        total_amount="10.00",
        currency="BRL",
    )


@given("o gateway de pagamento vai recusar a solicitação")
def dado_gateway_recusa(contexto):
    contexto["gateway"].create_order.side_effect = PaymentGatewayError(
        "Mercado Pago recusou a order (simulado no teste BDD)."
    )


@when("a solicitação é processada")
def quando_solicitacao_processada(contexto):
    use_case = CreatePaymentOrderUseCase(
        contexto["gateway"], contexto["repository"], contexto["notifier"]
    )
    contexto["resultado"] = use_case.execute(contexto["payload"])


@then("uma Order é criada no Mercado Pago")
def entao_order_criada(contexto):
    contexto["gateway"].create_order.assert_called_once()


@then("o resultado é persistido no repositório de orders")
def entao_resultado_persistido(contexto):
    contexto["repository"].save_created_order.assert_called_once()


@then(parsers.parse('uma notificação de status "{status}" é publicada'))
def entao_notificacao_publicada(contexto, status):
    contexto["notifier"].notify.assert_called_once()
    _, status_notificado = contexto["notifier"].notify.call_args.args
    assert status_notificado == status


@then("a tentativa recusada é registrada usando o external_reference como identificador")
def entao_recusa_registrada_com_external_reference(contexto):
    order_persistida = contexto["repository"].save_created_order.call_args.args[0]
    assert order_persistida.id == contexto["payload"]["external_reference"]
