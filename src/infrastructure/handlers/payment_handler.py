from src.infrastructure.handlers.polling_handler import lambda_handler as _polling_lambda_handler
from src.infrastructure.handlers.sqs_handler import lambda_handler as _sqs_lambda_handler


def lambda_handler(event, context):
    """
    Entry point único da PagamentoFunction (terraform/), com dois
    gatilhos possíveis: a fila SQS 'sqs-pagamento-solicitar' e o
    EventBridge que aciona o polling periódico de status na Orders API do
    Mercado Pago.

    Eventos de fila SQS sempre trazem a chave 'Records'; eventos do
    EventBridge (schedule) nunca trazem essa chave — critério simples e
    suficiente para despachar para o handler correto.
    """
    if "Records" in event:
        return _sqs_lambda_handler(event, context)
    return _polling_lambda_handler(event, context)
