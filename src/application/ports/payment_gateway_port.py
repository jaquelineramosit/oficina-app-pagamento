from abc import ABC, abstractmethod

from src.domain.entities import Order, OrderRequest


class PaymentGatewayPort(ABC):
    """
    Porta (interface) de saída para o gateway de pagamento.

    A camada de aplicação (use cases) depende apenas deste contrato — nunca
    da implementação concreta. Quem implementa é um adapter de infraestrutura
    (ex.: MercadoPagoGateway, usando HTTP), o que permite trocar de provedor
    de pagamento ou usar um dublê (fake/mock) em testes sem tocar nas regras
    de negócio.
    """

    @abstractmethod
    def create_order(self, order_request: OrderRequest, idempotency_key: str) -> Order:
        """Cria uma Order no gateway (POST /v1/orders)."""
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """Consulta uma Order existente no gateway (GET /v1/orders/{id})."""
        raise NotImplementedError
