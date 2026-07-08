from abc import ABC, abstractmethod
from typing import Optional

from src.domain.entities import Order


class OrderRepositoryPort(ABC):
    """
    Porta (interface) de saída para persistência do estado dos pedidos no
    seu sistema (ex.: DynamoDB, Postgres, etc.). A aplicação depende apenas
    deste contrato.
    """

    @abstractmethod
    def save_created_order(self, order: Order) -> None:
        """Persiste uma order recém-criada."""
        raise NotImplementedError

    @abstractmethod
    def update_order_status(self, order: Order) -> None:
        """Atualiza o status de uma order já existente (chamado pelo webhook)."""
        raise NotImplementedError

    @abstractmethod
    def find_by_id(self, order_id: str) -> Optional[Order]:
        """Busca uma order pelo id, caso já esteja persistida."""
        raise NotImplementedError
