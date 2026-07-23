from abc import ABC, abstractmethod

from src.domain.entities import Order


class PaymentStatusNotifierPort(ABC):
    """
    Porta (interface) de saída para publicar o resultado do pagamento para o
    restante do seu sistema, através das filas 'sqs-pagamento-efetuado' ou
    'sqs-pagamento-recusado'.
    """

    @abstractmethod
    def notify(self, order: Order, status: str) -> None:
        """Publica uma mensagem informando o novo status (ex.: 'efetuado', 'recusado', 'pago')."""
        raise NotImplementedError  # pragma: no cover
