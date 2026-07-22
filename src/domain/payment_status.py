"""
Status internos usados na comunicação com o restante do seu sistema através
das filas 'sqs-pagamento-efetuado' e 'sqs-pagamento-recusado'.

Importante: não confundir com os status nativos do Mercado Pago
(Order.status / Order.status_detail, ex.: "action_required", "processed",
"accredited"). Esses continuam disponíveis nas mensagens publicadas, para
quem quiser tratá-los com mais granularidade — os valores abaixo são só o
"resumo" que o requisito de negócio pediu.
"""


class PaymentStatus:
    EFETUADO = "efetuado"
    RECUSADO = "recusado"
    PAGO = "pago"


class MercadoPagoOrderStatus:
    """
    Valores nativos de Order.status retornados pela Orders API do Mercado
    Pago (bem diferentes dos valores de PaymentStatus acima). Usado pelo
    polling para decidir se uma order já chegou a um estado terminal.
    """
    PROCESSED = "processed"
