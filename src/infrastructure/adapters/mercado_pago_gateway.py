import logging

import requests

from src.application.ports.payment_gateway_port import PaymentGatewayPort
from src.domain.entities import Order, OrderRequest
from src.domain.exceptions import OrderNotFoundError, PaymentGatewayError
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class MercadoPagoGateway(PaymentGatewayPort):
    """
    Adapter de saída que implementa PaymentGatewayPort usando a API de
    Orders do Mercado Pago (https://api.mercadopago.com/v1/orders).

    Esta é a ÚNICA classe do projeto que sabe como falar HTTP com o
    Mercado Pago. Se um dia for necessário trocar de provedor, ou usar o
    SDK oficial em vez de chamadas HTTP diretas, apenas este arquivo muda.
    """

    def __init__(self, access_token: str = None, base_url: str = None, timeout: float = None):
        self._access_token = access_token or settings.MP_ACCESS_TOKEN
        self._base_url = (base_url or settings.MP_API_BASE_URL).rstrip("/")
        self._timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    def _headers(self, idempotency_key: str = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def create_order(self, order_request: OrderRequest, idempotency_key: str) -> Order:
        url = f"{self._base_url}/v1/orders"
        payload = order_request.to_mercado_pago_payload()

        try:
            response = requests.post(
                url, json=payload, headers=self._headers(idempotency_key), timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise PaymentGatewayError(
                f"Falha de rede ao chamar o Mercado Pago (criar order): {exc}"
            ) from exc

        if response.status_code not in (200, 201):
            logger.error(
                "Erro ao criar order no Mercado Pago | status=%s | body=%s",
                response.status_code,
                response.text,
            )
            raise PaymentGatewayError(
                f"Mercado Pago retornou status {response.status_code} ao criar a order.",
                status_code=response.status_code,
                response_body=response.text,
            )

        return Order.from_dict(response.json())

    def get_order(self, order_id: str) -> Order:
        url = f"{self._base_url}/v1/orders/{order_id}"

        try:
            response = requests.get(url, headers=self._headers(), timeout=self._timeout)
        except requests.RequestException as exc:
            raise PaymentGatewayError(
                f"Falha de rede ao consultar order no Mercado Pago: {exc}"
            ) from exc

        if response.status_code == 404:
            raise OrderNotFoundError(f"Order '{order_id}' não encontrada no Mercado Pago.")

        if response.status_code != 200:
            logger.error(
                "Erro ao consultar order no Mercado Pago | status=%s | body=%s",
                response.status_code,
                response.text,
            )
            raise PaymentGatewayError(
                f"Mercado Pago retornou status {response.status_code} ao consultar a order.",
                status_code=response.status_code,
                response_body=response.text,
            )

        return Order.from_dict(response.json())
