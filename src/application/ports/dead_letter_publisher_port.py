from abc import ABC, abstractmethod


class DeadLetterPublisherPort(ABC):
    """
    Porta (interface) de saída para publicar, na DLQ da fila de entrada,
    mensagens que não podem ser processadas (ex.: payload inválido) — para
    preservar o dado para investigação sem gastar tentativas de retry que
    nunca vão corrigir o problema.
    """

    @abstractmethod
    def publish(self, message_id: str, raw_body: str, error: str) -> None:
        """Publica a mensagem rejeitada, com o motivo do erro, na DLQ."""
        raise NotImplementedError  # pragma: no cover
