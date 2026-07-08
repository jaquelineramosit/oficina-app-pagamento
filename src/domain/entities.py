"""
Entidades de domínio do módulo de pagamentos (Pix via Mercado Pago Orders API).

Este módulo é o núcleo da arquitetura hexagonal: NÃO possui nenhuma
dependência de frameworks, SDKs de nuvem (boto3) ou bibliotecas HTTP
(requests). Apenas Python padrão + regras de negócio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from src.domain.exceptions import DomainValidationError


def _to_decimal(value, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise DomainValidationError(
            f"Campo '{field_name}' deve ser um valor numérico válido (ex.: \"10.00\")."
        )


# ---------------------------------------------------------------------------
# Objetos de entrada (o que a lambda de SQS recebe / envia para o Mercado Pago)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Payer:
    email: str

    def __post_init__(self):
        if not self.email or "@" not in self.email:
            raise DomainValidationError(
                "Campo 'payer.email' é obrigatório e deve ser um e-mail válido."
            )


@dataclass(frozen=True)
class PaymentMethod:
    type: str
    id: str

    def __post_init__(self):
        if not self.type:
            raise DomainValidationError("Campo 'payment_method.type' é obrigatório.")
        if not self.id:
            raise DomainValidationError("Campo 'payment_method.id' é obrigatório.")


@dataclass(frozen=True)
class PaymentRequest:
    amount: Decimal
    payment_method: PaymentMethod

    @staticmethod
    def from_dict(data: dict) -> "PaymentRequest":
        if not isinstance(data, dict):
            raise DomainValidationError(
                "Cada item de 'transactions.payments' deve ser um objeto."
            )

        amount_raw = data.get("amount")
        if amount_raw in (None, ""):
            raise DomainValidationError(
                "Campo 'transactions.payments[].amount' é obrigatório."
            )

        payment_method_raw = data.get("payment_method")
        if not isinstance(payment_method_raw, dict):
            raise DomainValidationError(
                "Campo 'transactions.payments[].payment_method' é obrigatório."
            )

        return PaymentRequest(
            amount=_to_decimal(amount_raw, "transactions.payments[].amount"),
            payment_method=PaymentMethod(
                type=payment_method_raw.get("type"),
                id=payment_method_raw.get("id"),
            ),
        )


@dataclass(frozen=True)
class OrderRequest:
    """
    Payload de entrada já validado, pronto para ser enviado à API de Orders
    do Mercado Pago. Todos os campos são obrigatórios, conforme requisito.
    """
    type: str
    processing_mode: str
    external_reference: str
    total_amount: Decimal
    description: str
    payer: Payer
    payments: List[PaymentRequest]

    @staticmethod
    def from_dict(data: dict) -> "OrderRequest":
        if not isinstance(data, dict):
            raise DomainValidationError("Payload da mensagem deve ser um objeto JSON.")

        required_top_level = [
            "type",
            "processing_mode",
            "external_reference",
            "total_amount",
            "description",
            "payer",
            "transactions",
        ]
        missing = [f for f in required_top_level if data.get(f) in (None, "")]
        if missing:
            raise DomainValidationError(
                f"Campos obrigatórios ausentes: {', '.join(missing)}"
            )

        payer_raw = data.get("payer")
        if not isinstance(payer_raw, dict) or not payer_raw.get("email"):
            raise DomainValidationError("Campo 'payer.email' é obrigatório.")

        transactions_raw = data.get("transactions")
        if not isinstance(transactions_raw, dict):
            raise DomainValidationError(
                "Campo 'transactions' é obrigatório e deve ser um objeto."
            )

        payments_raw = transactions_raw.get("payments")
        if not isinstance(payments_raw, list) or len(payments_raw) == 0:
            raise DomainValidationError(
                "Campo 'transactions.payments' é obrigatório e deve conter ao menos um item."
            )

        payments = [PaymentRequest.from_dict(p) for p in payments_raw]

        return OrderRequest(
            type=data["type"],
            processing_mode=data["processing_mode"],
            external_reference=data["external_reference"],
            total_amount=_to_decimal(data["total_amount"], "total_amount"),
            description=data["description"],
            payer=Payer(email=payer_raw["email"]),
            payments=payments,
        )

    def to_mercado_pago_payload(self) -> dict:
        """Serializa de volta para o formato exato aceito por POST /v1/orders."""
        return {
            "type": self.type,
            "processing_mode": self.processing_mode,
            "external_reference": self.external_reference,
            "total_amount": str(self.total_amount),
            "description": self.description,
            "payer": {"email": self.payer.email},
            "transactions": {
                "payments": [
                    {
                        "amount": str(p.amount),
                        "payment_method": {
                            "type": p.payment_method.type,
                            "id": p.payment_method.id,
                        },
                    }
                    for p in self.payments
                ]
            },
        }


# ---------------------------------------------------------------------------
# Objetos de saída (o que o Mercado Pago devolve, seja na criação ou no GET)
# ---------------------------------------------------------------------------

@dataclass
class PaymentResult:
    id: Optional[str] = None
    amount: Optional[str] = None
    status: Optional[str] = None
    status_detail: Optional[str] = None
    date_of_expiration: Optional[str] = None
    reference_id: Optional[str] = None
    payment_method_id: Optional[str] = None
    payment_method_type: Optional[str] = None
    ticket_url: Optional[str] = None
    qr_code: Optional[str] = None
    qr_code_base64: Optional[str] = None

    @staticmethod
    def from_dict(data: dict) -> "PaymentResult":
        pm = data.get("payment_method", {}) or {}
        return PaymentResult(
            id=data.get("id"),
            amount=data.get("amount"),
            status=data.get("status"),
            status_detail=data.get("status_detail"),
            date_of_expiration=data.get("date_of_expiration"),
            reference_id=data.get("reference_id"),
            payment_method_id=pm.get("id"),
            payment_method_type=pm.get("type"),
            ticket_url=pm.get("ticket_url"),
            qr_code=pm.get("qr_code"),
            qr_code_base64=pm.get("qr_code_base64"),
        )


@dataclass
class Order:
    """Representa uma Order do Mercado Pago (após criada ou consultada)."""
    id: str
    type: Optional[str] = None
    processing_mode: Optional[str] = None
    external_reference: Optional[str] = None
    description: Optional[str] = None
    total_amount: Optional[str] = None
    status: Optional[str] = None
    status_detail: Optional[str] = None
    total_paid_amount: Optional[str] = None
    country_code: Optional[str] = None
    user_id: Optional[str] = None
    capture_mode: Optional[str] = None
    currency: Optional[str] = None
    created_date: Optional[str] = None
    last_updated_date: Optional[str] = None
    payments: List[PaymentResult] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict) -> "Order":
        transactions = data.get("transactions", {}) or {}
        payments_raw = transactions.get("payments", []) or []
        return Order(
            id=data.get("id"),
            type=data.get("type"),
            processing_mode=data.get("processing_mode"),
            external_reference=data.get("external_reference"),
            description=data.get("description"),
            total_amount=data.get("total_amount"),
            status=data.get("status"),
            status_detail=data.get("status_detail"),
            total_paid_amount=data.get("total_paid_amount"),
            country_code=data.get("country_code"),
            user_id=data.get("user_id"),
            capture_mode=data.get("capture_mode"),
            currency=data.get("currency"),
            created_date=data.get("created_date"),
            last_updated_date=data.get("last_updated_date"),
            payments=[PaymentResult.from_dict(p) for p in payments_raw],
            raw=data,
        )
