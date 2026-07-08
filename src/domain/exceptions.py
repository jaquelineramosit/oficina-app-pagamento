"""
Exceções de domínio.

Nenhuma dessas exceções conhece detalhes de infraestrutura (HTTP, SQS,
DynamoDB etc.) — apenas o significado de negócio do erro. As camadas de
infraestrutura (handlers) são responsáveis por traduzir cada uma delas
para o comportamento apropriado (retry, DLQ, status HTTP, etc.).
"""


class DomainValidationError(Exception):
    """Payload de entrada inválido ou incompleto (regra de negócio violada)."""


class PaymentGatewayError(Exception):
    """Erro ao comunicar com o gateway de pagamento (Mercado Pago)."""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OrderNotFoundError(Exception):
    """Order não encontrada (nem no Mercado Pago, nem no repositório local)."""


class WebhookSignatureError(Exception):
    """Assinatura do webhook inválida — possível tentativa de falsificação."""
