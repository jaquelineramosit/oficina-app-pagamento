from abc import ABC, abstractmethod

from src.domain.entities import Order


class PaymentStatusNotifierPort(ABC):
    """
    Porta (interface) de saída para publicar atualizações de status de
    pagamento para o restante do seu sistema, através da fila
    'sqs-retorno-pagamento'.
    """

    @abstractmethod
    def notify(self, order: Order, status: str) -> None:
        """Publica uma mensagem informando o novo status (ex.: 'solicitado-pix', 'pago')."""
        raise NotImplementedError
